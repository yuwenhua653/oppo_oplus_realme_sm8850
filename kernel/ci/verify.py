#!/usr/bin/env python3
"""Check CI outputs; never treat them as a phone-tested or signed ROM package."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

root = Path.cwd()
device = root / 'device/xiaomi/myron'
product = root / 'out/target/product/myron'
obj = product / 'obj'
kernel = obj / 'KERNEL_OBJ'
report = {'success': False, 'full_rom_compiled': False, 'device_tested': False,
          'flash_package': False, 'scope': 'stock Evolution kernel.mk CI fixture',
          'errors': []}
errors = report['errors']


def check(ok, message):
    if not ok:
        errors.append(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output(*args):
    return subprocess.check_output(args, text=True).strip()


try:
    pins = {
        'kernel/xiaomi/sm8850': '4f5a0cf774c7a109e8e4fa1269aeec91169ed267',
        'kernel/xiaomi/sm8850-modules': '4cf53542c7a90c5b285ec228c351ecbfa8e7218a',
        'kernel/xiaomi/sm8850-devicetrees': 'b84c303a85a8f8b73d7fa3d4df37b57a601dd5b1',
    }
    report['sources'] = {}
    for path, expected in pins.items():
        actual = output('git', '-C', path, 'rev-parse', 'HEAD')
        report['sources'][path] = actual
        check(actual == expected, 'Wrong source revision: ' + path)
        check(not output('git', '--no-optional-locks', '-C', path, 'status', '--porcelain'),
              'Build changed source tree: ' + path)
    report['device_commit'] = output('git', '-C', str(device), 'rev-parse', 'HEAD')
    report['compiler'] = output('toolchains/clang/bin/clang', '--version')
    config = (kernel / '.config').read_text()
    report['config_sha256'] = digest(kernel / '.config')
    report['config_features'] = {
        key: bool(re.search(r'^CONFIG_' + key + r'=y$', config, re.M))
        for key in ('RUST', 'DEBUG_INFO_BTF', 'MODVERSIONS', 'MODULE_SIG', 'EROFS_FS', 'EROFS_FS_ZIP')
    }
    check(report['config_features']['EROFS_FS'] and report['config_features']['EROFS_FS_ZIP'],
          'EROFS support missing')
    # Kernel modules installed by the actual upstream recipe, not a handpicked copy.
    installed = obj / 'PACKAGING/kernel_modules/lib/modules'
    modules = list(installed.rglob('*.ko'))
    names = [p.name for p in modules]
    check(len(names) == len(set(names)), 'Duplicate installed module basename')
    catalog = json.loads((device / 'kernel/modules.json').read_text())
    expected = {m['file'] for m in catalog['modules'].values()}
    check(not expected - set(names), 'Missing catalog modules: ' + str(sorted(expected - set(names))))
    report['installed_modules'] = len(names)
    report['catalog_modules'] = len(expected)
    report['partitions'] = {}
    lists = dict(re.findall(r'^(MYRON_[A-Z_]+) := (.*)$',
                           (device / 'kernel/modules.mk').read_text(), re.M))
    specs = [('system_dlkm', None), ('vendor_dlkm', 'MYRON_VENDOR_LOAD_MODULES'),
             ('vendor_ramdisk', 'MYRON_BOOT_LOAD_MODULES'), ('recovery/root', 'MYRON_RECOVERY_LOAD_MODULES')]
    for partition, key in specs:
        directory = product / partition / 'lib/modules'
        load = (directory / 'modules.load').read_text().splitlines()
        required = [Path(x).stem for x in lists[key].split()] if key else []
        check(load == required, 'Load order changed: ' + partition)
        for name in load:
            check((directory / (name + '.ko')).is_file(), 'Missing loaded module: ' + name)
        report['partitions'][partition] = {'modules': len(list(directory.glob('*.ko'))),
                                           'load_entries': len(load)}
    options = product / 'vendor_dlkm/lib/modules/modules.options'
    check(options.read_bytes() == (device / 'kernel/modules.options').read_bytes(), 'Audio options differ')
    check('options machine_dlkm myron_tfa_links=1' in options.read_text(), 'TFA audio links missing')
    check('kernel/modules.options:$(TARGET_COPY_OUT_VENDOR_DLKM)/lib/modules/modules.options'
          in (device / 'device.mk').read_text(), 'ROM module-options copy rule missing')
    for name in ('asm/signal.h', 'asm-generic/signal.h'):
        check((root / 'out/headers/include' / name).is_file(), 'Missing exported header: ' + name)
    dt = json.loads((obj / 'DTB_OBJ/myron-images/source-dt-report.json').read_text())
    check(dt['success'] and len(dt['variants']) == 8 and not dt['errors'], 'DT assembly failed')
    proofs = json.loads((obj / 'DTB_OBJ/myron-images/fastrpc-order-proof.json').read_text())
    check(len(proofs) == 8 and all(p['all_other_bytes_identical'] and p['all_properties_byte_identical']
                                  for p in proofs), 'FastRPC ordering proof failed')
    report['images'] = {}
    for name in ('kernel', 'dtb.img', 'dtbo.img'):
        p = product / name
        check(p.stat().st_size > 0, 'Empty output: ' + name)
        report['images'][name] = {'bytes': p.stat().st_size, 'sha256': digest(p)}
    estimate = root / 'out/vendor_dlkm.payload.erofs'
    if estimate.exists():
        report['vendor_dlkm_payload_estimate_bytes'] = estimate.stat().st_size
        report['vendor_dlkm_reported_slot_bytes'] = 53805056
        check(estimate.stat().st_size <= 53805056, 'EROFS payload exceeds reported slot size')
        report['vendor_dlkm_estimate_has_avb_selinux'] = False
except Exception as error:
    errors.append(str(error))
finally:
    report['success'] = not errors
    (root / 'out').mkdir(exist_ok=True)
    (root / 'out/native-ci-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as stream:
            stream.write('Native kernel integration: ' + ('PASS' if not errors else 'FAIL') + '\n\n')
            stream.write('Stock Evolution kernel.mk; Image, modules, DT, exported headers and partition module staging.\n\n')
            stream.write('See native-ci-report.json for Rust/BTF selection and counts. No full ROM, Soong sandbox, AVB images or phone runtime test.\n')
raise SystemExit(bool(errors))
