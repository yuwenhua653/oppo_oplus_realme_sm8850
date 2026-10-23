#!/usr/bin/env python3
"""Prepare a locally reviewed R88 vendor_boot candidate from exact R88 inputs.

No device access, flashing, network access, or module execution occurs here.
Missing R88 CI/native/ABI proofs stop before an output image is created.
"""
import argparse
import copy
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
WORK = Path.cwd().resolve()
ROUTE = Path(__file__).resolve().parent.parent / 'r88-build-route'
BASE = IMAGE = CONTRACT = FOUNDATION = PID1_SOURCE = TOOLCHAIN = REPRODUCTION = ELF_PARSER = None
ELF_PARSER_SHA = '3ff542a4e55571b6d4af428cf3388973a36f313704b6848e0aab47d4ddea7c46'
IMAGE_PIN = {'bytes': 100663296, 'sha256': 'ade202a830574da27af940c06c828dc1e9b279749b96b524468f24423745cae8'}
PID1_SOURCE_PINS = {
    "pmsg_stages.h": {
        "bytes": 6253,
        "sha256": "1fe57a50e6397db61be4085b8a280e2bf36056f288df427f0181a6952c35e2b6"
    },
    "pstore_snapshot.h": {
        "bytes": 9080,
        "sha256": "a62d41debe6bad9e7bbf8d7a16d6db8254dff229256f42071f205a383d14bc65"
    },
    "r36_contract.h": {
        "bytes": 847,
        "sha256": "58b72bd75ab66749dd7f377fbdaff9880f7fe214e2b79d04787552913fa67920"
    },
    "r36_init.c": {
        "bytes": 30874,
        "sha256": "7771c5f395bac7c8786498a3263feed612149afcecbf818b76777f3cfbf3519e"
    },
    "report_reanchor.h": {
        "bytes": 5757,
        "sha256": "bb297def4f7ea5a50f3919a5c36768a4335981d419e61b199e41346712b5f0b8"
    }
}
R84_NATIVE_PINS = {
    "r36-init": {
        "bytes": 679832,
        "sha256": "138d25ef7c0919b182de061f2ff6b144d50bed6d139301f0812a1d24a797af94"
    },
    "r70-gauge-load": {
        "bytes": 728888,
        "sha256": "97b418a8fd42e1ab346bc49ee0fdcf30dc296cf12de132287f17bfece6433c9e"
    },
    "r75-mca-start": {
        "bytes": 663352,
        "sha256": "f660fec36b68049895f7b8e9f64baf7fff7bfc1e83acb4ecb30b340b10cc3e11"
    }
}
CONTRACT_SHA = 'e68871a2a6654a0c1bd3d0630474e5b79c60281791aeec5f63c1e9d37dbe691e'
KERNEL_SHA = '2fa774b4ffdd75064fb733bb2cad071b02b1813ad5cd54bae32bda2247ef18a7'
PARENT_R87 = 'b25d73a0dc1f606e51c21214b0beafaa5dae4496'
OLD_R87_CI = 'ae4bf5b38ae1771e0f440b8b26b02cd66a008231'
MODULE_DIRECTORY = '/vendor_dlkm/r32/r88-mca'
HELPER_PATH = '/vendor_dlkm/r32/r88-mca-start'
PAYLOAD_BYTES = 83886080
STAMP = 1792713600
COMMANDS = []
BAD = ('File not found', 'not found by ext2_lookup', 'Unknown request', 'Could not allocate', 'Usage:')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def read(path):
    return json.loads(Path(path).read_text())


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        need(stream.write(data) == len(data), 'Short output write: ' + str(path))


def dump(path, value):
    put(path, (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())


def safe(root, relative):
    root = Path(root).resolve()
    name = PurePosixPath(relative)
    need(relative and not name.is_absolute() and '..' not in name.parts, 'Unsafe artifact relative path')
    path = root / relative
    need(path.resolve().is_relative_to(root), 'Escaping artifact path')
    need(all(not (root / Path(*name.parts[:i])).is_symlink() for i in range(1, len(name.parts) + 1)),
         'Symlink artifact path')
    return path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(argv, *, env=None, binary=False):
    argv = list(map(str, argv))
    p = subprocess.run(argv, capture_output=True, env=env, timeout=180)
    COMMANDS.append({'argv': argv, 'returncode': p.returncode,
                     'stdout': pin(p.stdout) if binary else p.stdout.decode(errors='replace'),
                     'stderr': p.stderr.decode(errors='replace')})
    need(p.returncode == 0, 'Command failed: ' + str(argv) + '\n' + p.stderr.decode(errors='replace'))
    return p.stdout


def debug(image, command):
    result = run(['debugfs', '-R', command, image], binary=command.startswith('cat '))
    need(not any(x in COMMANDS[-1]['stderr'] for x in BAD), 'debugfs rejected: ' + command)
    return result


def exact_replace(data, before, after, message):
    need(data.count(before) == 1, message)
    return data.replace(before, after, 1)


def loader_overlay(original):
    start = original.find(b'    # R70: independent readonly telemetry attempt.')
    end = original.find(b'    setprop vendor.all.modules.ready 1', start)
    need(start >= 0 and end > start, 'Exact R84 synchronous owner blocks required')
    old = original[start:end]
    need(old.count(b'/vendor_dlkm/r32/r70-gauge-load') == 1 and
         old.count(b'/vendor_dlkm/r32/r75-mca-start') == 1, 'Exactly two old helper invocations')
    replacement = b'''    # R88: one boot-only exclusive full-MCA owner attempt after normal249.
    # This helper never unloads modules or falls back to the old readonly owners.
    say 'R88_MCA_BEGIN; exact normal249 plus45 coherent full-MCA modules'
    if /vendor_dlkm/r32/r88-mca-start; then
        say 'R88_MCA_RETURNED; inspect same-boot binding/authentication status'
    else
        say 'R88_MCA_FAILED; no hot retry or old-owner fallback; inspect native status'
    fi
'''
    result = original[:start] + replacement + original[end:]
    need(result[:start] == original[:start] and result[start + len(replacement):] == original[end:],
         'Normal249, TFA, ready and later DSP sections must be unchanged')
    need(b'/vendor_dlkm/r32/r70-gauge-load' not in result and
         b'/vendor_dlkm/r32/r75-mca-start' not in result, 'Old owners must not be invoked')
    need(result.count(b'/vendor_dlkm/r32/r88-mca-start') == 1, 'Exactly one new owner helper')
    return result, old, replacement


def verify_pid1_sources(directory):
    selected = {p.name for p in directory.iterdir() if p.suffix in ('.c', '.h')}
    need(selected == set(PID1_SOURCE_PINS), 'Exact healthy R84 PID1 source inventory required')
    for name, expected in PID1_SOURCE_PINS.items():
        path = directory / name
        need(path.is_file() and not path.is_symlink() and pin(path.read_bytes()) == expected,
             'Exact healthy R84 PID1 source required: ' + name)


def verify_prepared_sources(prepared, native, native_raw, prep):
    source = ROUTE.parent / 'r88-handover/native'
    names = ('mca_start.c', 'sha256_fixed.h', 'test_mca_start.c')
    expected = {name: pin((source / name).read_bytes()) for name in names}
    need(prep.get('native_sources') == expected, 'Native preparation must bind the current R88 source set')
    for name in names:
        path = prepared / name
        need(path.is_file() and not path.is_symlink() and pin(path.read_bytes()) == expected[name],
             'Prepared source must equal current reviewed R88 source: ' + name)
    generator = load('r88_assembly_contract_header', ROUTE.parent / 'r88-handover/generate_contract.py')
    expected_header = generator.make_header(native, pin(native_raw)['sha256']).encode()
    need((prepared / 'mca_contract.h').read_bytes() == expected_header,
         'Prepared header must be generated from the exact native module contract')
    need(prep.get('toolchain_manifest') == pin(TOOLCHAIN.read_bytes()),
         'Native preparation and PID1 build must use the exact same verified toolchain manifest')


def verify_inputs(args):
    need(args.vendor_payload_bytes == PAYLOAD_BYTES, 'Only explicit 80MiB RAM vendor payload growth is reviewed')
    need(re.fullmatch(r'R88-[A-Z0-9-]+', args.build_id) is not None, 'Explicit R88 build identity required')
    need(re.fullmatch(r'[0-9a-f]{40}', args.ci_head) is not None and args.ci_head not in (PARENT_R87, OLD_R87_CI),
         'Actual new R88 commit required; R87 artifacts are not an R88 release')
    need(args.ci_run > 0 and args.ci_attempt > 0, 'Exact successful R88 run ID and attempt required')
    original = IMAGE.read_bytes()
    need(pin(original) == IMAGE_PIN, 'Exact healthy R84 vendor_boot required')
    raw_contract = CONTRACT.read_bytes()
    need(pin(raw_contract)['sha256'] == CONTRACT_SHA, 'Exact healthy R84 runtime contract required')
    contract = json.loads(raw_contract)
    need(contract['build_id'] == 'R84-THERMAL-FG-QUERY-20261021-01' and len(contract['module_files']) == 249,
         'Exact normal249 baseline required')
    ci = args.ci.resolve()
    complete = read(ci / 'validation-complete.json')
    status = read(ci / 'reports/r88-status.json')
    identity = {'GITHUB_SHA': args.ci_head, 'GITHUB_RUN_ID': str(args.ci_run),
                'GITHUB_RUN_ATTEMPT': str(args.ci_attempt)}
    need(status.get('success') is True and status.get('validation_compiled') is True and
         status.get('github') == identity, 'Successful exact R88 CI identity required')
    need(complete.get('full_validation_success') is True and complete.get('required_module_count') == 47,
         'All coherent full47 targets must compile')
    need(complete.get('compile_only') is True and complete.get('activation_allowed') is False and
         complete.get('runtime_candidate_module_names') == [], 'Input CI artifacts retain inactive provenance')
    route = ROUTE
    frozen_build = (route / 'build-contract.json').read_bytes()
    frozen_source = (route / 'SOURCE-CONTRACT.json').read_bytes()
    need(complete['build_contract_sha256'] == pin(frozen_build)['sha256'] == status['build_contract_sha256'] and
         complete['source_contract_sha256'] == pin(frozen_source)['sha256'] == status['source_contract_sha256'],
         'R88 completion must bind exact frozen local source/build contracts')
    source = json.loads(frozen_source)
    need(source.get('source_commit') == PARENT_R87, 'R88 source must extend exact reviewed R87 ancestry')
    fg_prefix = 'vendor/qcom/sm8850/drivers/power/supply/mca/mca_strategy/strategy_fg/'
    need({x['path'] for x in source['writes']} == {fg_prefix + 'mca_strategy_fg.c',
         fg_prefix + 'inc/strategy_fg.h', fg_prefix + 'mca_soc_smooth.c'},
         'R88 must contain exactly the reviewed FG policy separation')
    lockraw = (ci / 'artifact-lock.json').read_bytes()
    need(pin(lockraw)['sha256'] == complete['artifact_lock_sha256'], 'Completion must bind artifact lock')
    for row in json.loads(lockraw)['files']:
        path = safe(ci, row['file'])
        need(path.is_file() and pin(path.read_bytes()) == {k: row[k] for k in ('bytes', 'sha256')},
             'Locked CI artifact changed: ' + row['file'])
    expected_source_pins = {row['path']: row['after'] for row in source['writes']}
    expected_source_pins.update({row['path']: row['expected'] for row in source.get('read_only_guards', [])})
    captured_sources = set()
    for row in complete['compiled_sources']:
        path = safe(ci, row['file'])
        need(row['file'].startswith('compiled-source/'), 'Fixed compiled-source snapshot directory')
        relative = row['file'].removeprefix('compiled-source/')
        need(relative in expected_source_pins and relative not in captured_sources and
             pin(path.read_bytes()) == {k: row[k] for k in ('bytes', 'sha256')} == expected_source_pins[relative],
             'Compiled source snapshot differs from frozen source contract')
        captured_sources.add(relative)
    need({row['path'] for row in source['writes']} <= captured_sources, 'Every changed R88 source must have an actual compiled snapshot')
    configuration = (ci / 'module-config/canoe_perf.config').read_text()
    need(not re.search(r'^CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING=(?:y|m|1)$', configuration, re.M),
         'IC firmware programming must remain disabled')
    inventory = read(ci / 'module-inventory.json')
    need(inventory['module_count'] == 47 and len(inventory['modules']) == 47 and
         inventory.get('activation_allowed') is False, 'Exact inactive47 module inventory')
    need(pin(ELF_PARSER.read_bytes())['sha256'] == ELF_PARSER_SHA, 'Exact reviewed ELF parser required')
    Elf = load('r88_assembly_elf', ELF_PARSER).Elf
    modules = {}
    for row in inventory['modules']:
        path = safe(ci, row['file'])
        data = path.read_bytes()
        need(pin(data) == {k: row[k] for k in ('bytes', 'sha256')}, 'Actual selected KO changed')
        info = Elf(path).review()
        name = info['modinfo']['name'][0]
        need(name == row['name'] and name not in modules and re.fullmatch(r'[A-Za-z0-9_]+', name),
             'Exact unique module name')
        modules[name] = {'source': path, 'pin': pin(data), 'review': info}
    need(set(modules) == set(inventory['required_module_names']), 'Required47 names differ')
    abi_raw = args.abi.read_bytes()
    abi = json.loads(abi_raw)
    need(abi.get('status') == 'PASS_STATIC_INACTIVE_FULL_MCA_CLOSURE' and
         abi.get('artifact_identity', {}).get('status') == 'PASS_R88_EXACT_ARTIFACT_IDENTITY' and not abi.get('issues') and
         not abi.get('dependency_cycle') and abi.get('hypothetical_module_count') == 294 and
         abi.get('mca_module_count') == 47 and abi.get('ci') == identity and
         abi.get('source_contract_sha256') == complete['source_contract_sha256'],
         'Actual R88 artifacts require complete static294 ABI closure')
    need(abi['retained_image']['sha256'] == KERNEL_SHA and
         abi['retained_runtime_contract']['sha256'] == CONTRACT_SHA and
         {k: abi['retained_vendor_boot'][k] for k in IMAGE_PIN} == IMAGE_PIN,
         'ABI must use retained healthy R84 kernel and actual baseline')
    elf_reviews = read(args.abi.parent / 'FULL-MCA-ELF-REVIEWS.json')
    need(set(elf_reviews) == set(modules) and all(elf_reviews[n]['sha256'] == m['pin']['sha256']
         for n, m in modules.items()), 'ABI report must bind exact selected KO files')
    normal = contract['module_files']
    normal_names = {}
    for path, row in normal.items():
        data = safe(BASE, path.lstrip('/')).read_bytes()
        need(pin(data) == row, 'Retained normal module changed: ' + path)
        name = Elf(BASE / path.lstrip('/')).modinfo()['name'][0]
        need(name not in normal_names, 'Unique normal module names')
        normal_names[name] = path
    need(set(normal_names) & set(modules) == {'hwid', 'miev'}, 'Only hwid/miev may be reused')
    for name in ('hwid', 'miev'):
        need(modules[name]['pin'] == normal[normal_names[name]], 'Reused baseline module must be byte identical')
    additions = {name: module for name, module in modules.items() if name not in normal_names}
    need(len(additions) == 45, 'Exactly45 new full-MCA modules')
    native_raw = args.native_contract.read_bytes()
    native = json.loads(native_raw)
    review_raw = args.native_review.read_bytes()
    prep = json.loads(review_raw)
    baseline_rows = native.get('baseline', [])
    native_normal = {row['path']: {k: row[k] for k in ('bytes', 'sha256')} for row in baseline_rows}
    need(native.get('build_id') == args.build_id and native.get('normal_module_count') == 249 and
         native.get('total_module_count') == 294 and len(baseline_rows) == 249 and native_normal == normal and
         {row['name'] for row in baseline_rows} == set(normal_names) and
         all(normal_names[row['name']] == row['path'] for row in baseline_rows) and
         native.get('kernel') == contract['expected_kernel'] and
         native.get('baseline_runtime_contract_sha256') == CONTRACT_SHA and
         native.get('baseline_vendor_boot') == IMAGE_PIN,
         'New native guard must bind exact normal249')
    native_ci = {'head_sha': args.ci_head, 'run_id': str(args.ci_run),
                 'source_contract_sha256': complete['source_contract_sha256'],
                 'build_contract_sha256': complete['build_contract_sha256']}
    declared_ci = dict(native.get('source_ci', {}))
    declared_ci['run_id'] = str(declared_ci.get('run_id', ''))
    need(declared_ci == native_ci and native.get('abi_review') == pin(abi_raw),
         'Native contract must bind exact new R88 CI/ABI')
    need(native.get('review_status') == 'FROZEN_REVIEWED_R88_RUNTIME_CANDIDATE' and
         native.get('activation_allowed') is True and native.get('runtime_frozen') is True,
         'A draft or unfrozen native contract cannot create an activated candidate')
    planned = native.get('additions', [])
    need(len(planned) == 45 and {r['name'] for r in planned} == set(additions), 'New helper must select exact45')
    available = set(normal_names)
    for row in planned:
        need(row['path'] == MODULE_DIRECTORY + '/' + row['name'] + '.ko' and row.get('load_arguments', '') == '' and
             {k: row[k] for k in ('bytes', 'sha256')} == additions[row['name']]['pin'],
             'Fixed module path, parameters and exact bytes required')
        dependencies = {name.replace('-', '_') for item in additions[row['name']]['review']['modinfo'].get('depends', [])
                        for name in item.split(',') if name}
        need(dependencies <= available, 'New native module order lacks an already loaded declared dependency')
        available.add(row['name'])
    helper = args.native_helper.read_bytes()
    prep_ci = dict(prep.get('source_ci', {}))
    prep_ci['run_id'] = str(prep_ci.get('run_id', ''))
    need(prep.get('status') == 'PASS_R88_NATIVE_PREPARATION_NOT_RUNTIME_APPROVAL' and
         prep.get('build_id') == args.build_id and prep.get('module_set') == pin(native_raw) and
         prep.get('helper') == pin(helper) and prep.get('baseline_image') == IMAGE_PIN and
         prep.get('baseline_contract') == pin(raw_contract) and prep_ci == native_ci and
         prep.get('abi_review') == pin(abi_raw) and prep.get('host_tests_passed') is True and
         prep.get('ASan_UBSan_Werror') is True and prep.get('double_build_byte_identical') is True and
         prep.get('runtime_frozen') is True and prep.get('activation_allowed') is True,
         'Qualified new native preparation and exact helper bytes required')
    prepared = args.native_review.resolve().parent
    need(pin((prepared / 'mca_start.c').read_bytes()) == prep.get('helper_source') and
         pin((prepared / 'mca_contract.h').read_bytes()) == prep.get('generated_header') and
         (prepared / 'module-set.json').read_bytes() == native_raw and
         (prepared / 'r88-mca-start-reproduction').read_bytes() == helper,
         'Actual prepared native source/header/contract and reproduced helper required')
    verify_prepared_sources(prepared, native, native_raw, prep)
    verify_pid1_sources(PID1_SOURCE)
    reproduction = read(REPRODUCTION)
    need(reproduction.get('status') == 'PASS_EXACT_R84_NATIVE_REPRODUCTION' and
         all(r.get('byte_identical') is True for r in reproduction['results']) and len(reproduction['results']) == 3,
         'Actual R84 PID1/gauge/MCA binaries must have been reproduced')
    reproduced = {r['name']: r for r in reproduction['results']}
    need(set(reproduced) == set(R84_NATIVE_PINS) and
         all(reproduced[name].get('compiled') == expected == reproduced[name].get('actual_R84')
             for name, expected in R84_NATIVE_PINS.items()),
         'Reproduction must bind the three exact healthy R84 native binaries')
    return original, raw_contract, contract, complete, modules, normal_names, additions, native_raw, native, review_raw, prep, helper


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace-root', type=Path, default=Path.cwd())
    for name in ('baseline-dir', 'retained-vendor-boot', 'runtime-contract', 'foundation',
                 'pid1-source', 'toolchain', 'reproduction', 'elf-parser'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--ci', required=True, type=Path)
    parser.add_argument('--ci-head', required=True)
    parser.add_argument('--ci-run', required=True, type=int)
    parser.add_argument('--ci-attempt', default=1, type=int)
    parser.add_argument('--abi', required=True, type=Path)
    parser.add_argument('--native-contract', required=True, type=Path)
    parser.add_argument('--native-review', required=True, type=Path)
    parser.add_argument('--native-helper', required=True, type=Path)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--vendor-payload-bytes', required=True, type=int)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--check-inputs', action='store_true')
    args = parser.parse_args()
    global WORK, BASE, IMAGE, CONTRACT, FOUNDATION, PID1_SOURCE, TOOLCHAIN, REPRODUCTION, ELF_PARSER
    WORK = args.workspace_root.resolve()
    BASE, IMAGE, CONTRACT, FOUNDATION, PID1_SOURCE, TOOLCHAIN, REPRODUCTION, ELF_PARSER = [
        getattr(args, name).resolve() for name in ('baseline_dir', 'retained_vendor_boot',
        'runtime_contract', 'foundation', 'pid1_source', 'toolchain', 'reproduction', 'elf_parser')]
    out = args.out.resolve()
    need(out.is_relative_to(WORK) and not out.exists() and not out.is_symlink(), 'Fresh workspace output required')
    need(not re.search(r'[\s\x00\x22\x27\\]', str(out)), 'Output path must be safe for debugfs command files')
    (original, contract_raw, contract, complete, modules, normal_names, additions,
     native_raw, native, prep_raw, prep, helper) = verify_inputs(args)
    if args.check_inputs:
        print(json.dumps({'status': 'PASS_R88_ASSEMBLY_INPUTS', 'image_created': False, 'normal_modules': 249,
                          'new_modules': 45, 'total_modules': 294, 'explicit_RAM_payload_bytes': PAYLOAD_BYTES}))
        return
    sys.path.insert(0, str(FOUNDATION / 'image'))
    import build_images as im
    common = load('r88_fs_inventory', FOUNDATION / 'r43-build-reference.py')
    common.elf_check(helper)
    sections, _ = im.vendor_sections(original)
    codec = im.LegacyLz4()
    cpio_old = codec.decompress(sections['ramdisk'])
    entries = im.parse_cpio(cpio_old)
    bodies = {row['name']: row['data'] for row in entries}
    for kind in ('system_dlkm', 'vendor_dlkm'):
        data = (BASE / (kind + '.img')).read_bytes()
        need(data == bodies['r32-payload/' + kind + '.img'] and pin(data) ==
             {k: contract['payloads'][kind][k] for k in ('bytes', 'sha256')}, 'Pinned actual baseline payload')
    need(len(bodies['r32-payload/vendor_dlkm.img']) == 75497472 and PAYLOAD_BYTES < 128 * 1024 * 1024,
         'Reviewed single-blockgroup 72→80MiB RAM payload growth')
    sourcefs = BASE / 'vendor_dlkm.img'
    raw = sourcefs.read_bytes()
    before = common.inventory(sourcefs)
    loader = debug(sourcefs, 'cat /r32/load-modules.sh')
    need(pin(loader) == {k: contract['runtime_files']['/vendor_dlkm/r32/load-modules.sh'][k]
                        for k in ('bytes', 'sha256')}, 'Exact healthy R84 loader')
    new_loader, old_owner_block, new_owner_block = loader_overlay(loader)
    for kind in ('load', 'order', 'dep', 'alias', 'softdep'):
        data = debug(sourcefs, 'cat /lib/modules/modules.' + kind)
        need(not any(x in data for x in (b'myron_bq_readonly', b'myron_mca_readonly', b'bq27z561', b'sc8581', b'sc8585', b'mca_')),
             'Normal autoload metadata must not select either old or new charging owners')
    files = {'/r32/load-modules.sh': new_loader, '/r32/r88-mca-start': helper}
    final_modules = copy.deepcopy(contract['module_files'])
    for row in native['additions']:
        name = row['name']
        full = row['path']
        files[full.removeprefix('/vendor_dlkm')] = additions[name]['source'].read_bytes()
        final_modules[full] = additions[name]['pin']
    files['/r32/r88-mca/module-set.json'] = native_raw
    need(len(final_modules) == 294 and len(files) == 48, 'Exact final294 and48 changed/added files')
    need(set(files) & set(before) == {'/r32/load-modules.sh'}, 'Only the old loader file is replaced')
    need('/r32/r88-mca' not in before, 'Fresh fixed MCA directory required')
    tc = read(TOOLCHAIN)
    for row in tc['packages']:
        need(pin(Path(row['path']).read_bytes()) == {k: row[k] for k in ('bytes', 'sha256')}, 'Pinned native compiler package')
    env = {**os.environ, **tc['env_overrides']}
    out.mkdir(parents=True)
    dump(out / 'input-proofs.json', {'baseline_image': IMAGE_PIN, 'baseline_contract': pin(contract_raw),
        'source_ci': native['source_ci'], 'source_contract_sha256': complete['source_contract_sha256'],
        'native_contract': pin(native_raw), 'native_preparation': pin(prep_raw), 'new_helper': pin(helper),
        'explicit_old_vendor_payload_bytes': len(raw), 'explicit_new_vendor_payload_bytes': PAYLOAD_BYTES})
    put(out / 'evidence/owner-loader.patch', ''.join(difflib.unified_diff(loader.decode().splitlines(True),
        new_loader.decode().splitlines(True), fromfile='R84/load-modules.sh', tofile='R88/load-modules.sh')).encode())
    put(out / 'generated/r32/load-modules.sh', new_loader)
    run(['sh', '-n', out / 'generated/r32/load-modules.sh'])
    removal = ['set_current_time 0x%x' % STAMP, 'rm /r32/load-modules.sh']
    install = ['set_current_time 0x%x' % STAMP, 'mkdir /r32/r88-mca',
               'set_inode_field /r32/r88-mca mode 040755', 'set_inode_field /r32/r88-mca uid 0',
               'set_inode_field /r32/r88-mca gid 0']
    directory_label = out / 'labels/directory'
    put(directory_label, b'u:object_r:vendor_file:s0\0')
    install.append('ea_set -f ' + str(directory_label) + ' /r32/r88-mca security.selinux')
    for inner, data in sorted(files.items()):
        path = out / 'generated' / inner.lstrip('/')
        if inner != '/r32/load-modules.sh':
            put(path, data)
        label = out / 'labels' / inner.lstrip('/')
        mode = 0o100755 if inner in ('/r32/load-modules.sh', '/r32/r88-mca-start') else 0o100644
        if inner == '/r32/load-modules.sh':
            need(struct.unpack_from('<H', raw, common.inode_offset(raw, before[inner]['inode']) + 0x1a)[0] == 1,
                 'Only singly linked loader may be replaced')
            label.parent.mkdir(parents=True, exist_ok=True)
            debug(sourcefs, 'ea_get -f ' + str(label) + ' ' + inner + ' security.selinux')
            need(before[inner]['mode'] == oct(mode) and before[inner]['uid'] == before[inner]['gid'] == 0,
                 'Original loader ownership/mode')
        else:
            put(label, b'u:object_r:vendor_modinstall-sh_exec:s0\0' if inner.endswith('-start') else b'u:object_r:vendor_file:s0\0')
        install += ['write ' + str(path) + ' ' + inner, 'set_inode_field ' + inner + ' mode 0%o' % mode,
                    'set_inode_field ' + inner + ' uid 0', 'set_inode_field ' + inner + ' gid 0']
        install += ['set_inode_field ' + inner + ' ' + f + ' 0x%x' % STAMP for f in ('atime', 'mtime', 'ctime', 'crtime')]
        install += ['ea_set -f ' + str(label) + ' ' + inner + ' security.selinux']
    for inner in ('/r32', '/r32/r88-mca'):
        install += ['set_inode_field ' + inner + ' ' + f + ' 0x%x' % STAMP for f in ('atime', 'mtime', 'ctime', 'crtime')]
    removefile = out / 'evidence/remove.txt'
    installfile = out / 'evidence/install.txt'
    put(removefile, ('\n'.join(removal) + '\n').encode())
    put(installfile, ('\n'.join(install) + '\n').encode())
    fsenv = {**os.environ, 'E2FSPROGS_FAKE_TIME': str(STAMP)}
    required_blocks = sum((len(data) + 4095) // 4096 for data in files.values()) + 64
    required_inodes = len(files) + 1
    payloads = []
    for name in ('payload', 'reproduction'):
        path = out / name / 'vendor_dlkm.img'
        put(path, raw)
        with path.open('r+b') as stream:
            stream.truncate(PAYLOAD_BYTES)
        run(['resize2fs', '-f', path, str(PAYLOAD_BYTES // 4096)], env=fsenv)
        grown = path.read_bytes()
        need(len(grown) == PAYLOAD_BYTES and struct.unpack_from('<I', grown, 1024)[0] == 10240 and
             struct.unpack_from('<I', grown, 1024 + 0x20)[0] == 32768, 'Reviewed inode and single-group geometry')
        need(struct.unpack_from('<I', grown, 1036)[0] >= required_blocks and
             struct.unpack_from('<I', grown, 1040)[0] >= required_inodes, '80MiB payload space insufficient; no automatic further growth')
        run(['debugfs', '-w', '-f', removefile, path], env=fsenv)
        need(not any(x in COMMANDS[-1]['stderr'] for x in BAD), 'Remove old loader')
        run(['debugfs', '-w', '-f', installfile, path], env=fsenv)
        need(not any(x in COMMANDS[-1]['stderr'] for x in BAD), 'Install exact helper/modules')
        run(['e2fsck', '-fn', path], env=fsenv)
        payloads.append(path.read_bytes())
    need(payloads[0] == payloads[1], 'Double resize/install must be byte identical')
    fs = out / 'payload/vendor_dlkm.img'
    payload = payloads[0]
    after = common.inventory(fs)
    additions_fs = (set(files) - set(before)) | {'/r32/r88-mca'}
    need(set(after) == set(before) | additions_fs, 'No unrelated path changes')
    for path in set(before) - {'/r32/load-modules.sh', '/r32'}:
        need(before[path] == after[path], 'Unrelated inode/content changed: ' + path)
    need(debug(sourcefs, 'stat /') == debug(fs, 'stat /'), 'Root inode/metadata retained')
    for path in set(before) | {'/'}:
        need(debug(sourcefs, 'ea_list ' + path) == debug(fs, 'ea_list ' + path), 'Existing xattrs changed: ' + path)
    for inner, data in files.items():
        need(debug(fs, 'cat ' + inner) == data and after[inner]['uid'] == after[inner]['gid'] == 0,
             'Installed file bytes/owner: ' + inner)
        mode = '0o100755' if inner in ('/r32/load-modules.sh', '/r32/r88-mca-start') else '0o100644'
        need(after[inner]['mode'] == mode, 'Installed mode: ' + inner)
        label_readback = out / 'evidence/label-readbacks' / inner.lstrip('/')
        label_readback.parent.mkdir(parents=True, exist_ok=True)
        debug(fs, 'ea_get -f ' + str(label_readback) + ' ' + inner + ' security.selinux')
        need(label_readback.read_bytes() == (out / 'labels' / inner.lstrip('/')).read_bytes(),
             'Installed SELinux label differs: ' + inner)
    for path, row in final_modules.items():
        part, inner = path.lstrip('/').split('/', 1)
        backing = fs if part == 'vendor_dlkm' else BASE / 'system_dlkm.img'
        need(pin(debug(backing, 'cat /' + inner)) == row, 'Final294 actual selected module: ' + path)
    for kind in ('load', 'order', 'dep', 'alias', 'softdep'):
        path = '/lib/modules/modules.' + kind
        need(debug(sourcefs, 'cat ' + path) == debug(fs, 'cat ' + path), 'Normal module metadata retained')
    header = (PID1_SOURCE / 'r36_contract.h').read_bytes()
    header = exact_replace(header, contract['build_id'].encode(), args.build_id.encode(), 'Exactly one PID1 identity')
    header = exact_replace(header, contract['payloads']['vendor_dlkm']['sha256'].encode(), pin(payload)['sha256'].encode(),
                           'Exactly one vendor payload hash')
    header = exact_replace(header, b'#define R36_VENDOR_BYTES 75497472ULL',
                           b'#define R36_VENDOR_BYTES 83886080ULL', 'Exactly one vendor payload size')
    for path in PID1_SOURCE.iterdir():
        if path.suffix in ('.c', '.h'):
            put(out / 'native' / path.name, header if path.name == 'r36_contract.h' else path.read_bytes())
    for target in (out / 'native/r36-init', out / 'reproduction/r36-init'):
        run(tc['compile_argv'] + ['-o', str(target), str(out / 'native/r36_init.c')], env=env)
        run(tc['strip_argv'] + [str(target)], env=env)
    pid1 = (out / 'native/r36-init').read_bytes()
    need(pid1 == (out / 'reproduction/r36-init').read_bytes(), 'Deterministic PID1 build')
    common.elf_check(pid1)
    cpio, prior, final, changes = im.rebuild_cpio(cpio_old, lambda _: False,
        {'r36-init': pid1, 'r32-payload/vendor_dlkm.img': payload}, [])
    need({x['name'] for x in changes} == {'r36-init', 'r32-payload/vendor_dlkm.img'}, 'Only PID1 and vendor payload change in CPIO')
    need([x['name'] for x in prior] == [x['name'] for x in final], 'CPIO order retained')
    for old, new in zip(prior, final):
        fields = old['fields'][:]
        fields[6] = len(new['data'])
        need(fields == new['fields'], 'CPIO object metadata retained')
    compressed = codec.compress(cpio, 9)
    need(codec.decompress(compressed) == cpio, 'LZ4 roundtrip')
    image, avb = im.append_avb(im.vendor_payload(original, compressed, sections), original, 'vendor_boot', None)
    again, _ = im.append_avb(im.vendor_payload(original, codec.compress(cpio, 9), sections), original, 'vendor_boot', None)
    need(image == again and len(image) == IMAGE_PIN['bytes'], 'Deterministic outer96MiB vendor_boot geometry')
    final_sections, _ = im.vendor_sections(image)
    need(final_sections['dtb'] == sections['dtb'] and final_sections['bootconfig'] == sections['bootconfig'],
         'DTB and bootconfig retained')
    actual = {x['name']: x['data'] for x in im.parse_cpio(codec.decompress(final_sections['ramdisk']))}
    need(actual == {**bodies, 'r36-init': pid1, 'r32-payload/vendor_dlkm.img': payload}, 'Final CPIO byte readback')
    check_header = bytearray(image[:4096])
    check_header[24:28] = original[24:28]
    need(check_header == original[:4096] and final_sections['table'][4:] == sections['table'][4:], 'Header/table retention')
    put(out / 'review/vendor_boot.img', image)
    avb_check = run([sys.executable, '-B', FOUNDATION / 'image/avbtool.py', 'verify_image', '--image', out / 'review/vendor_boot.img'])
    updated = copy.deepcopy(contract)
    updated['build_id'] = args.build_id
    updated['payloads']['vendor_dlkm'].update(pin(payload))
    updated['normal_module_files'] = contract['module_files']
    updated['module_files'] = final_modules
    for inner, data in files.items():
        full = '/vendor_dlkm' + inner
        updated['runtime_files'][full] = {**updated['runtime_files'].get(full, {}), **pin(data),
            'selinux_context': 'u:object_r:vendor_modinstall-sh_exec:s0' if inner in ('/r32/load-modules.sh', '/r32/r88-mca-start') else 'u:object_r:vendor_file:s0'}
    updated['r88_full_mca_handover'] = {'normal_module_count': 249, 'new_module_count': 45, 'selected_module_count': 294,
        'native_helper': HELPER_PATH, 'native_contract': pin(native_raw), 'native_preparation': pin(prep_raw),
        'source_ci': native['source_ci'], 'actual_abi_review': pin(args.abi.read_bytes()),
        'boot_only_exclusive_owners': True, 'readonly_modules_on_disk_but_not_selected': ['myron_bq_readonly', 'myron_mca_readonly'],
        'full_MCA_drivers_selected': True, 'charging_policy_may_write': True,
        'authentication_bypass': False, 'IC_firmware_programming': False,
        'old_RAM_vendor_payload_bytes': len(raw), 'new_RAM_vendor_payload_bytes': PAYLOAD_BYTES,
        'physical_partition_geometry_changed': False, 'outer_vendor_boot_bytes': len(image),
        'hardware_tested': False, 'release_ready': False}
    for key in ('readonly_battery_r70', 'readonly_mca_r75'):
        if key in updated:
            updated[key]['runtime_selected'] = False
            updated[key]['retained_as_inactive_history'] = True
    dump(out / 'runtime-contract.json', updated)
    dump(out / 'evidence/EXT4-DELTA.json', {'before': before, 'after': after,
        'replaced_paths': ['/r32/load-modules.sh'], 'added_paths': sorted(additions_fs), 'removed_paths': [],
        'directory_inode_change_allowlist': ['/r32'], 'reserved_internal_resize_inode': 7})
    dump(out / 'evidence/COMMANDS.json', COMMANDS)
    report = {'schema': 1, 'status': 'PASS_LOCAL_ASSEMBLY_PENDING_INDEPENDENT_REVIEW', 'build_id': args.build_id,
        'image': pin(image), 'payload': pin(payload), 'pid1': pin(pid1), 'baseline_image': IMAGE_PIN,
        'retained_kernel_sha256': KERNEL_SHA, 'system_payload_retained': True, 'normal_modules_preserved': 249,
        'new_modules': 45, 'all_selected_module_pins_verified': 294, 'deterministic_resize_ext4_pid1_image': True,
        'all_unrelated_reachable_inodes_and_xattrs_unchanged': True, 'DTB_bootconfig_preserved': True,
        'normal_module_metadata_preserved': True, 'normal_loader_before_owner_point_and_ready_DSP_tail_preserved': True,
        'runtime_contract': pin((out / 'runtime-contract.json').read_bytes()), 'source_ci': native['source_ci'],
        'native_contract': pin(native_raw), 'native_preparation': pin(prep_raw), 'actual_abi_review': pin(args.abi.read_bytes()),
        'explicit_RAM_payload_growth': {'from': len(raw), 'to': PAYLOAD_BYTES},
        'avb': avb, 'official_avb_verification': avb_check.decode(), 'hardware_tested': False,
        'device_accessed': False, 'release_ready': False, 'flashable_release_claimed': False}
    dump(out / 'ASSEMBLY-REVIEW.json', report)
    print(json.dumps({k: report[k] for k in ('status', 'image', 'normal_modules_preserved', 'new_modules',
        'all_selected_module_pins_verified', 'explicit_RAM_payload_growth', 'release_ready')}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        print('R88_ASSEMBLY_STOP:', error, file=sys.stderr)
        sys.exit(2)
