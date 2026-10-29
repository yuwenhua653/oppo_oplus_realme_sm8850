#!/usr/bin/env python3
"""Record an actual compiler output, without labelling it flash-qualified."""
import hashlib, json, os, pathlib, shutil, struct, subprocess

temp = pathlib.Path(os.environ['RUNNER_TEMP'])
product = temp / 'r97-aosp/out/target/product/sm8850'
image = product / 'recovery.img'
b = image.read_bytes()
if len(b) != 104857600 or b[:8] != b'ANDROID!':
    raise ValueError('Unexpected recovery image geometry or magic')
kernel_size, ramdisk_size = struct.unpack_from('<II', b, 8)
header_version = struct.unpack_from('<I', b, 40)[0]
if header_version != 4 or kernel_size != 0 or ramdisk_size == 0:
    raise ValueError('Expected kernel-less header-v4 recovery')
if b[-64:-60] != b'AVBf':
    raise ValueError('Missing AVB footer')
dest = temp / 'r97-deliver'
dest.mkdir()
shutil.copy2(image, dest / 'recovery-candidate-r97.img')
subprocess.run(['tar', '--zstd', '--numeric-owner', '-cf',
                str(dest / 'recovery-root.tar.zst'), '-C',
                str(product / 'recovery/root'), '.'], check=True)
pins = {}
for rel in ['system/bin/init', 'system/bin/recovery', 'system/etc/init/hw/init.rc']:
    path = product / 'recovery/root' / rel
    data = path.read_bytes()
    pins[rel] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
report = {
    'status': 'COMPILE_ONLY_RUNTIME_AND_PAIRING_REQUIRED',
    'flash_qualified': False, 'device_tested': False,
    'private_runtime_included': False,
    'adaptation_commit': os.environ['GITHUB_SHA'],
    'run_id': os.environ['GITHUB_RUN_ID'],
    'image': {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()},
    'header_version': header_version, 'kernel_size': kernel_size,
    'ramdisk_size': ramdisk_size, 'build_tree_pins': pins,
    'next_gate': 'Independently unpack image, inject the exact private R96 runtime locally, remove compile-only marker, compile paired PID1 preserving R96 normal Android pins, rebuild both images, verify both images.'
}
(dest / 'BUILD-RESULT.json').write_text(json.dumps(report, indent=2) + '\n')
(dest / 'NOT-A-FLASH-PACKAGE.txt').write_text(
    'COMPILE-ONLY-NOT-FLASHABLE: private runtime modules are deliberately absent.\n'
    'Requires local runtime injection, matching PID1/vendor_boot and independent image validation.\n')
shutil.copy2(temp / 'r97-evidence/resolved-manifest.xml', dest)
print(json.dumps(report, indent=2))
