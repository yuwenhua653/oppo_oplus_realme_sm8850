#!/usr/bin/env python3
"""Run complete gauge with the exact locked core thermal bridge functions."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
REL = Path('drivers/power/supply/myron_bq_readonly.c')

BRIDGE_STUBS = r'''
#define CONFIG_POWER_SUPPLY_HWMON 1
#define IS_ENABLED(value) (value)
#define IS_ERR_OR_NULL(value) (!(value) || IS_ERR(value))
#define WARN_ON(condition) assert(!(condition))
struct thermal_zone_device;
struct thermal_zone_device_ops { int (*get_temp)(struct thermal_zone_device *, int *); };
struct thermal_zone_params { bool no_hwmon; };
struct thermal_zone_device { struct power_supply *psy; const struct thermal_zone_device_ops *ops; bool live; };
static struct thermal_zone_device zone;
static int zone_register_calls, zone_enable_calls, zone_unregister_calls;
static int zone_register_error, zone_enable_error;
static bool psy_has_property(const struct power_supply_desc *desc, int property)
{
    for (size_t i = 0; i < desc->num_properties; i++)
        if (desc->properties[i] == property) return true;
    return false;
}
static void *thermal_zone_device_priv(struct thermal_zone_device *z) { return z->psy; }
static struct thermal_zone_device *thermal_tripless_zone_device_register(
    const char *name, void *private, const struct thermal_zone_device_ops *ops,
    const struct thermal_zone_params *params)
{
    assert(!strcmp(name, "battery"));
    assert(private == active_psy && params->no_hwmon);
    zone_register_calls++;
    if (zone_register_error) return ERR_PTR(zone_register_error);
    zone = (struct thermal_zone_device){ private, ops, true };
    return &zone;
}
static int thermal_zone_device_enable(struct thermal_zone_device *z)
{
    assert(z == &zone && z->live); zone_enable_calls++; return zone_enable_error;
}
static void thermal_zone_device_unregister(struct thermal_zone_device *z)
{
    assert(z == &zone && z->live); zone_unregister_calls++; z->live = false;
}
static void assert_no_gauge_lock(void) { }
'''

MAIN = r'''
static int checks;
#define CHECK(expr, msg) do { if (!(expr)) { fprintf(stderr, "FAIL %s\n", msg); return 1; } checks++; } while (0)
static void reset_zone(void)
{
    zone_register_calls = zone_enable_calls = zone_unregister_calls = 0;
    zone_register_error = zone_enable_error = 0;
    zone.live = false;
    reads = fail_at = 0;
    values[0] = 50; values[1] = 4000; values[2] = 2982;
    read_error = -EREMOTEIO;
}
int main(void)
{
    compatible = capable = true;
    enable_readonly = true;
    for (int mode = 0; mode < 3; mode++) {
        reset_zone();
        enable_extended_readonly = mode >= 1;
        enable_status_readonly = mode == 2;
        CHECK(myron_readonly_probe(&client) == 0, "gauge probe");
        CHECK(psy_register_thermal(active_psy) == 0, "core registration return");
        CHECK(zone_register_calls == 1 && zone_enable_calls == 1 && zone.live,
              "real battery thermal zone must be registered in every selected descriptor");
        int out = 1234567;
        reads = 0;
        CHECK(zone.ops->get_temp(&zone, &out) == 0 && out == 25100 && reads == 3,
              "deci-C to milli-C from current hardware sample");
        values[2] = 2731; reads = 0;
        CHECK(zone.ops->get_temp(&zone, &out) == 0 && out == -100, "negative Celsius conversion");
        values[2] = 2732; reads = 0;
        CHECK(zone.ops->get_temp(&zone, &out) == 0 && out == 100, "positive Celsius conversion");
        values[2] = 4012; reads = 0; out = 1234567;
        CHECK(zone.ops->get_temp(&zone, &out) == -ERANGE && out == 1234567,
              "out-of-range sensor remains an error without fabricated temperature");
        values[2] = 2982;
        for (int failure = 1; failure <= 3; failure++) {
            reads = 0; fail_at = failure; out = 1234567;
            CHECK(zone.ops->get_temp(&zone, &out) == -EREMOTEIO && out == 1234567,
                  "each sensor transfer failure is preserved by the core");
        }
        fail_at = 0;
        psy_unregister_thermal(active_psy);
        CHECK(zone_unregister_calls == 1 && !zone.live, "core unregister releases thermal zone");
        release_all();
        release_count = 0;
    }
    reset_zone();
    CHECK(myron_readonly_probe(&client) == 0, "error path gauge probe");
    zone_register_error = -ENOMEM;
    CHECK(psy_register_thermal(active_psy) == -ENOMEM && !zone_enable_calls,
          "thermal allocation failure preserved");
    psy_unregister_thermal(active_psy);
    CHECK(!zone_unregister_calls, "error pointer must not be unregistered");
    reset_zone(); zone_enable_error = -EIO;
    CHECK(psy_register_thermal(active_psy) == -EIO && zone_unregister_calls == 1 && !zone.live,
          "thermal enable failure unwinds registration");
    active_psy->tzd = NULL;
    psy_unregister_thermal(active_psy);
    CHECK(zone_unregister_calls == 1, "null zone requires no unregister");
    release_all();
    printf("PASS %d exact core/gauge bridge checks; tripless temperature registration only\n", checks);
    return 0;
}
'''


def main():
    contract = json.loads((ROOT / 'BATTERY-THERMAL-CONTRACT.json').read_text())
    core = (ROOT / 'upstream/power_supply_core.c').read_bytes()
    assert hashlib.sha256(core).hexdigest() == contract['core_source']['sha256']
    core_text = core.decode()
    start = core_text.index('static int power_supply_read_temp(')
    end = core_text.index('\n#else', start)
    bridge = core_text[start:end]
    # Retain a complete production gauge translation unit. Extend only the host
    # API stub structure and dispatch to accommodate the real core functions.
    fake = (ROOT / 'tests/gauge/fake_kernel.h').read_text()
    fake = fake.replace('const struct attribute_group **groups;bool removing; };',
                        'const struct attribute_group **groups;bool removing;struct thermal_zone_device *tzd; };')
    needle = 'static int power_supply_get_property(struct power_supply *p,enum power_supply_property prop,union power_supply_propval *v){\n'
    assert fake.count(needle) == 1
    fake = fake.replace(needle, needle + ' if(p!=&usb_psy)return p->desc->get_property(p,prop,v);\n')
    results = {}
    with tempfile.TemporaryDirectory(prefix='thermal-bridge-', dir=ROOT) as tmp:
        work = Path(tmp)
        (work / 'fake_kernel.h').write_text(fake)
        for variant, key in [('preimage', 'before_sha256'), ('payload', 'after_sha256')]:
            source = (ROOT / variant / REL).read_bytes()
            assert hashlib.sha256(source).hexdigest() == contract[key]
            headers = re.findall(r'^#include <([^>]+)>', source.decode(), re.M)
            for header in headers:
                p = work / header
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('#include "fake_kernel.h"\n')
            (work / 'gauge.c').write_bytes(source)
            cfile = work / (variant + '.c')
            cfile.write_text('#include "gauge.c"\n' + BRIDGE_STUBS + bridge + MAIN)
            binary = work / variant
            argv = ['cc', '-std=gnu11', '-g', '-O1', '-pthread', '-Wall', '-Wextra',
                    '-Werror', '-Wno-unused-parameter', '-Wno-unused-function',
                    '-Wno-misleading-indentation', '-Wno-sign-compare',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    '-I' + str(work), str(cfile), '-o', str(binary)]
            build = subprocess.run(argv, capture_output=True, text=True, timeout=30)
            if build.returncode:
                raise RuntimeError(build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True, timeout=15,
                                 env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',
                                          UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'))
            results[variant] = {'sha256': hashlib.sha256(source).hexdigest(),
                                'exit_code': run.returncode, 'stdout': run.stdout.strip(),
                                'stderr': run.stderr.strip()}
    passed = results['preimage']['exit_code'] == 1 and results['payload']['exit_code'] == 0
    report = {'pass': passed, 'core_sha256': hashlib.sha256(core).hexdigest(),
              'exact_core_functions_sha256': hashlib.sha256(bridge.encode()).hexdigest(),
              'sanitizers': ['address', 'undefined'], 'results': results,
              'scope': 'Complete production gauge plus exact locked core thermal functions; thermal framework and I2C are mocks.',
              'limits': ['Not a device run or full-kernel build', 'No SKIN calibration or fast-charge success claim',
                         'Full power_supply registration/unregister orchestration is inspected in locked source, not executed by this fixture']}
    (ROOT / 'BATTERY-THERMAL-TESTS.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
