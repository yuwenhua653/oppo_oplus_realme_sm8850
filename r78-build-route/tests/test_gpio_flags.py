#!/usr/bin/env python3
"""Compile real TFA request blocks against pinned legacy GPIO declarations.

This focused host regression is not a full kernel/module build. Only public
GPIOF macros, the real gpio_is_valid body and the real request prototype are
extracted from the unchanged locked kernel header. Request execution is faked.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
ROUTE = HERE.parent
HEADER = HERE / "fixtures/common-gpio.h"
PROVENANCE = HERE / "fixtures/GPIO-PROVENANCE.json"
SOURCE = ROUTE / "audio/payload/drivers/xiaomi/myron_tfa98xx/src/tfa98xx.c"


def matching(pattern, text):
    result = re.search(pattern, text, re.MULTILINE)
    if result is None:
        raise RuntimeError(f"Locked source/header section missing: {pattern}")
    return result.group(0)


def production_sequence(source):
    start = source.index("\tif (gpio_is_valid(tfa98xx->reset_gpio)) {")
    end_marker = "\ttfa98xx_ext_reset(tfa98xx);"
    end = source.index(end_marker, start) + len(end_marker)
    sequence = source[start:end]
    if sequence.count("devm_gpio_request_one(") != 3:
        raise RuntimeError("Expected all three real production GPIO requests")
    if len(re.findall(r"\bGPIOF_IN\b", sequence)) != 1:
        raise RuntimeError("Production IRQ must use the legacy GPIOF_IN API flag")
    return sequence


FIXTURE = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stddef.h>
#include <string.h>
struct device { int unused; };
struct i2c_client { struct device dev; };
struct tfa98xx { int reset_gpio, irq_gpio, spk_sw_gpio; };
struct recorded_request { unsigned gpio; unsigned long flags; const char *label; };
static struct recorded_request calls[3];
static struct device *expected_device;
static unsigned call_count, power_up_calls;
static int fail_index, request_error;
'''


IMPLEMENTATION = r'''
int devm_gpio_request_one(struct device *dev, unsigned gpio,
                         unsigned long flags, const char *label)
{
    assert(dev == expected_device);
    assert(call_count < 3);
    unsigned index = call_count++;
    calls[index] = (struct recorded_request){gpio, flags, label};
    return (int)index == fail_index ? request_error : 0;
}
static void tfa98xx_ext_reset(struct tfa98xx *tfa98xx)
{
    (void)tfa98xx;
    ++power_up_calls;
}
'''


MAIN = r'''
static void check(unsigned mask, int failure_at, int error)
{
    struct i2c_client client = {0};
    /* GPIO zero is valid, while negative GPIO values are absent. */
    struct tfa98xx tfa = {
        mask & 1 ? 0 : -1,
        mask & 2 ? 14 : -517,
        mask & 4 ? 27 : -22
    };
    const unsigned pins[] = {0, 14, 27};
    const unsigned long flags[] = {GPIOF_OUT_INIT_LOW, GPIOF_IN, GPIOF_OUT_INIT_LOW};
    const char *labels[] = {"TFA98XX_RST", "TFA98XX_INT", "TFA98XX_SPK_SW"};
    unsigned wanted_calls = 0;
    for (unsigned i = 0; i < 3; ++i)
        if (mask & (1U << i)) ++wanted_calls;
    if (failure_at >= 0) wanted_calls = (unsigned)failure_at + 1;
    call_count = power_up_calls = 0;
    fail_index = failure_at;
    request_error = error;
    expected_device = &client.dev;
    int ret = production_gpio_probe(&client, &tfa);
    assert(ret == (failure_at >= 0 ? error : 0));
    assert(call_count == wanted_calls);
    assert(power_up_calls == (failure_at < 0 ? 1U : 0U));
    unsigned request = 0;
    for (unsigned i = 0; i < 3 && request < wanted_calls; ++i) {
        if (!(mask & (1U << i))) continue;
        assert(calls[request].gpio == pins[i]);
        assert(calls[request].flags == flags[i]);
        assert(strcmp(calls[request].label, labels[i]) == 0);
        ++request;
    }
    assert(request == wanted_calls);
}
int main(void)
{
    for (unsigned mask = 0; mask < 8; ++mask) {
        unsigned valid = 0;
        check(mask, -1, 0);
        for (unsigned i = 0; i < 3; ++i)
            if (mask & (1U << i)) ++valid;
        for (unsigned failure_at = 0; failure_at < valid; ++failure_at) {
            check(mask, (int)failure_at, -EIO);
            /* Linux EPROBE_DEFER, supplied only as a mock return value. */
            check(mask, (int)failure_at, -517);
        }
    }
    return 0;
}
'''


def main():
    provenance = json.loads(PROVENANCE.read_text())
    header_bytes = HEADER.read_bytes()
    digest = hashlib.sha256(header_bytes).hexdigest()
    if digest != provenance["sha256"]:
        raise RuntimeError("Locked common GPIO header checksum mismatch")
    header = header_bytes.decode()
    # Use actual macro definitions, not replacement definitions invented here.
    public_flags = "\n".join(re.findall(r"^#define GPIOF_[^\n]+", header, re.MULTILINE))
    if "GPIOF_DIR_IN" in public_flags:
        raise RuntimeError("Unexpected legacy direction macro in locked header")
    is_valid = matching(r"static inline bool gpio_is_valid\(int number\)\s*\{[^}]+\}", header)
    request_decl = matching(
        r"int devm_gpio_request_one\(struct device \*dev, unsigned gpio,\s*"
        r"unsigned long flags, const char \*label\);", header)
    sequence = production_sequence(SOURCE.read_text())
    unit = (FIXTURE + public_flags + "\n" + is_valid + "\n" + request_decl + "\n"
            + IMPLEMENTATION + "\nstatic int production_gpio_probe(struct i2c_client *i2c, "
            "struct tfa98xx *tfa98xx)\n{\nint ret;\n" + sequence + "\nreturn 0;\n}\n" + MAIN)
    compiler = shutil.which("cc")
    if compiler is None:
        raise RuntimeError("A host C compiler (cc) is required for this regression")
    options = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
               "-fsanitize=undefined", "-fno-sanitize-recover=all"]
    with tempfile.TemporaryDirectory(prefix="r78-gpio-test-") as temporary:
        directory = Path(temporary)
        current = directory / "current.c"
        current.write_text(unit)
        fixed = subprocess.run(options + [str(current), "-o", str(directory / "current")],
                               capture_output=True, text=True)
        if fixed.returncode:
            raise RuntimeError("Current GPIO probe compilation failed:\n" + fixed.stderr)
        subprocess.run([str(directory / "current")], check=True, capture_output=True, text=True)
        old = directory / "old.c"
        # Replace only the real production sequence; fixture/header stay unchanged.
        old_sequence = re.sub(r"\bGPIOF_IN\b", "GPIOF_DIR_IN", sequence)
        old.write_text(unit.replace(sequence, old_sequence, 1))
        old_result = subprocess.run(options + [str(old), "-o", str(directory / "old")],
                                    capture_output=True, text=True)
        if old_result.returncode == 0 or "GPIOF_DIR_IN" not in old_result.stderr:
            raise RuntimeError("Old unsupported GPIOF_DIR_IN regression was not reproduced")
    print(json.dumps({"passed": True, "fixture_sha256": digest,
                      "old_gpiof_dir_in_compile": "rejected",
                      "current_gpiof_in_compile": "passed",
                      "success_validity_cases": 8, "failure_propagation_cases": 24,
                      "scope": "focused host test, not full kernel compilation"}, indent=2))


if __name__ == "__main__":
    main()
