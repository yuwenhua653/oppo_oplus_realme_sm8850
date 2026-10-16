#!/usr/bin/env python3
"""Host-test the actual MCA HWID branches; does not load a kernel module.

Place beside payload/ and hwid_compat_reference/ in the build route, or run:
  python3 test_hwid_compat.py --root /path/to/r61-build-route
The reference files are pinned source, not generated replacement HWID headers.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


PINNED = {
    "donor-hwid.h": "eae4df4b800b1540f4c71731f03730bedb25251657e818fbcd5660756a4eda5b",
    "myron-hwid.h": "28a90e94c08854b74fa577e252be741ec49f166d571dba456c4d5994e5675fa8",
    "myron-hwid.c": "bf9da3e02041599782c8c930e7b4b98f908c6736e86ac90cdacf94b97a86836d",
    "mca_hwid.h": "07e0c73bfa4421a18311c15ff752742a8492fa5d3bfcdce718643e0d292129ef",
    "mca_hwid.c": "505b5d47fc5d2980d694ad0fa186132649cea63eaf64846398c27adaae77e269",
}
SOURCES = {
    "smart": "payload/drivers/power/supply/mca/mca_smart_charge/mca_smart_charge.c",
    "basic": "payload/drivers/power/supply/mca/mca_strategy/strategy_wireless/mca_basic_wireless.c",
    "quick": "payload/drivers/power/supply/mca/mca_strategy/strategy_wireless/mca_quick_wireless.c",
    "charge": "payload/drivers/power/supply/mca/mca_strategy/strategy_charger/mca_strategy_quickchg.c",
}


def mask_comments(source):
    token = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)
    return token.sub(lambda m: re.sub(r"[^\n]", " ", m[0])
                     if m[0].startswith(("//", "/*")) else m[0], source)


def matching(source, opening, left, right):
    """Find the matching delimiter while ignoring literals and comments."""
    text = mask_comments(source)
    depth, quote, escaped = 0, None, False
    for index in range(opening, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char == left:
            depth += 1
        elif char == right:
            depth -= 1
            if depth == 0:
                return index
    raise AssertionError(f"Unmatched {left} at {opening}")


def function_body(source, name):
    text = mask_comments(source)
    found = list(re.finditer(r"\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{", text))
    assert len(found) == 1, f"Expected one definition of {name}, got {len(found)}"
    opening = text.index("{", found[0].start())
    return source[opening:matching(source, opening, "{", "}") + 1]


def named_condition(source, function, product):
    body = function_body(source, function)
    text = mask_comments(body)
    candidates = []
    for match in re.finditer(r"\bif\s*\(", text):
        opening = text.index("(", match.start())
        closing = matching(text, opening, "(", ")")
        expression = body[opening + 1:closing]
        if f'"{product}"' in expression:
            candidates.append(expression)
    assert len(candidates) == 1, f"Expected one {product} condition in {function}"
    return candidates[0]


def without_kernel_include(source):
    return re.sub(r"^\s*#include <linux/types.h>\s*$", "", source, flags=re.M)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--reference", type=Path,
                        default=Path(__file__).resolve().parent / "hwid_compat_reference")
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    args = parser.parse_args()
    assert shutil.which(args.cc), f"Host C compiler unavailable: {args.cc}"
    reference = {}
    for name, expected in PINNED.items():
        data = (args.reference / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected, f"Reference changed: {name}"
        reference[name] = data.decode()

    # These constants are donor-local IDs, NOT aliases valid in the SoC 660 header.
    for enum, number, name in [("O1", 4, "xuanyuan"), ("O8", 5, "bixi"), ("O9", 8, "luming")]:
        assert re.search(r"#define\s+HARDWARE_PROJECT_" + enum + r"\s+" + str(number) +
                         r"\s*//\s*" + name + r"\b", reference["donor-hwid.h"])
    initializer = mask_comments(reference["mca_hwid.c"])
    assignment = re.search(r"info->product_name\s*=\s*product_name_get\(\)\s*;", initializer)
    publication = re.search(r"phwid\s*=\s*info\s*;", initializer)
    assert assignment and publication and assignment.start() < publication.start()

    actual = {key: (args.root / rel).read_text() for key, rel in SOURCES.items()}
    for key, source in actual.items():
        assert not re.search(r"\bHARDWARE_PROJECT_O(?:1|8|9)\b", mask_comments(source)), \
            f"Unported donor-local enum remains in {SOURCES[key]}"
        assert re.search(r"#include\s+<linux/string.h>", source), \
            f"strcmp needs its direct header in {SOURCES[key]}"

    smart = function_body(actual["smart"], "smart_charge_handle_mishow_config")
    basic = named_condition(actual["basic"], "strategy_wireless_monitor_work", "bixi")
    quick = named_condition(actual["quick"], "mca_wireless_quick_change_bridge", "bixi")
    charge = named_condition(actual["charge"], "mca_quick_charge_can_tbat_do_charge", "xuanyuan")
    product = function_body(reference["myron-hwid.c"], "product_name_get")

    harness = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
''' + without_kernel_include(reference["myron-hwid.h"]) + "\n" + without_kernel_include(reference["mca_hwid.h"]) + r'''
static unsigned int project, test_soc;
static unsigned int socinfo_get_id(void) { return test_soc; }
const char *product_name_get(void)
''' + product + r'''
static const struct mca_hwid *selected_hwid;
const struct mca_hwid *mca_get_hwid_info(void) { return selected_hwid; }
static int boot_mode, partition_reads, algorithm_calls;
static bool partition_mishow;
struct smart_charge_info { bool mishow_config; };
static int mca_log_get_charge_boot_mode(void) { return boot_mode; }
static int charger_partition_get_mishow(bool *value)
{ ++partition_reads; *value = partition_mishow; return 0; }
static void smartcharging_handle_algorithm_conflict(struct smart_charge_info *info)
{ (void)info; ++algorithm_calls; }
#define mca_log_info(...) ((void)0)
static void smart_charge_handle_mishow_config(struct smart_charge_info *info)
''' + smart + r'''
static bool basic_condition(const struct mca_hwid *hwid) { return (
''' + basic + r'''); }
static bool quick_reject_condition(const struct mca_hwid *hwid) { return (
''' + quick + r'''); }
static bool charge_condition(const struct mca_hwid *hwid) { return (
''' + charge + r'''); }
static unsigned checks;
#define CHECK(expr, label) do { ++checks; if (!(expr)) { \
  fprintf(stderr, "FAILED: %s at line %d: %s\n", label, __LINE__, #expr); \
  return 1; } } while (0)
int main(void)
{
    const struct scenario {
        const char *label, *product;
        unsigned int id, country;
        bool null_hwid, smart_allowed, basic, quick_reject, charge;
    } cases[] = {
        {"NULL hwid", NULL, 0, CountryCN, true, false, false, true, false},
        {"NULL name", NULL, 4, CountryGlobal, false, false, false, true, false},
        {"empty name", "", 5, CountryGlobal, false, false, false, true, false},
        {"unknown name", "unknown", 4, CountryGlobal, false, false, false, true, false},
        {"myron ID4 global", "myron", 4, CountryGlobal, false, false, false, true, false},
        {"myron ID4 CN kept", "myron", 4, CountryCN, false, false, false, true, true},
        {"nezha ID5 global", "nezha", 5, CountryGlobal, false, false, false, true, false},
        {"nezha ID5 CN kept", "nezha", 5, CountryCN, false, false, false, true, true},
        {"bixi donor", "bixi", 5, CountryGlobal, false, true, true, false, false},
        {"bixi name independent of ID", "bixi", 0, CountryGlobal, false, true, true, false, false},
        {"luming donor", "luming", 8, CountryGlobal, false, true, false, true, false},
        {"luming name independent of ID", "luming", 0, CountryGlobal, false, true, false, true, false},
        {"xuanyuan donor", "xuanyuan", 4, CountryGlobal, false, false, false, true, true},
        {"xuanyuan name independent of ID", "xuanyuan", 0, CountryGlobal, false, false, false, true, true},
        {"case sensitive", "Bixi", 5, CountryGlobal, false, false, false, true, false},
        {"prefix is not exact name", "bixi-extra", 5, CountryGlobal, false, false, false, true, false},
        {"legacy11 NULL name retained", NULL, 11, CountryGlobal, false, false, false, true, true},
        {"CN NULL name retained", NULL, 0, CountryCN, false, false, false, true, true},
        {"legacy11 unknown name retained", "unknown", 11, CountryGlobal, false, false, false, true, true},
        {"legacy3 unknown mapping unchanged", "unknown", 3, CountryGlobal, false, false, false, true, false},
    };
    const char *const names[] = {"unknown", "popsicle", "pudding", "pandora", "myron", "nezha", "pecan", "pixiu", "unknown"};
    test_soc = HWID_SOC_ID_660;
    for (project = 0; project < sizeof(names) / sizeof(names[0]); ++project)
        CHECK(!strcmp(product_name_get(), names[project]), "actual SoC660 product table");
    test_soc = 0;
    project = HARDWARE_PROJECT_660_MYRON;
    CHECK(!strcmp(product_name_get(), "unknown"), "other SoC must not become myron");
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        const struct scenario *item = &cases[i];
        struct mca_hwid hwid = {.platform_version = item->id,
            .country_version = item->country, .product_name = item->product};
        selected_hwid = item->null_hwid ? NULL : &hwid;
        CHECK(basic_condition(selected_hwid) == item->basic, item->label);
        CHECK(quick_reject_condition(selected_hwid) == item->quick_reject, item->label);
        CHECK(charge_condition(selected_hwid) == item->charge, item->label);
        for (boot_mode = 0; boot_mode <= 1; ++boot_mode) {
            for (int value = 0; value <= 1; ++value) {
                struct smart_charge_info info = {.mishow_config = true};
                const bool allowed = item->smart_allowed && boot_mode != 0;
                partition_reads = algorithm_calls = 0;
                partition_mishow = value;
                smart_charge_handle_mishow_config(&info);
                CHECK(partition_reads == (allowed ? 1 : 0), item->label);
                CHECK(algorithm_calls == (allowed && value ? 1 : 0), item->label);
                CHECK(info.mishow_config == (allowed ? (bool)value : true), item->label);
            }
        }
    }
    printf("{\"host_assertions\":%u,\"scenarios\":%zu}\n", checks, sizeof(cases) / sizeof(cases[0]));
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="r61-hwid-") as temp:
        cfile, binary = Path(temp) / "hwid_test.c", Path(temp) / "hwid_test"
        cfile.write_text(harness)
        subprocess.run([args.cc, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                        str(cfile), "-o", str(binary)], check=True)
        result = json.loads(subprocess.check_output([str(binary)], text=True))
    result.update({"status": "PASS", "root": str(args.root.resolve()),
                   "source_sha256": {SOURCES[key]: hashlib.sha256(source.encode()).hexdigest()
                                     for key, source in actual.items()},
                   "reference_sha256": PINNED,
                   "scope": "actual four MCA HWID branches and pinned current product-name function; host-only"})
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
