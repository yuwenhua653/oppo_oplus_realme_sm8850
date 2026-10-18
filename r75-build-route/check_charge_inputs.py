#!/usr/bin/env python3
"""Fail-closed R75 overlay/source readiness; no compilation or device actions."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re

BASE_CONTRACT = 'r61-build-route/battery-contract.json'
BASE_SHA256 = 'f78f8e0bdaf21461235d41c554fdda9fb60d2e59afdaecefd0dfce73ac8982ba'
BASE_IMAGE = '2fa774b4ffdd75064fb733bb2cad071b02b1813ad5cd54bae32bda2247ef18a7'
BASE_RELEASE = '6.12.81-android16-6-maybe-dirty-4k'
MODULE_STEMS = {
    'qti_pmic_glink': 'drivers/soc/qcom/qti_pmic_glink',
    'myron_mca_readonly': 'drivers/power/supply/myron_mca_readonly/myron_mca_readonly',
    'myron_bq_readonly': 'drivers/power/supply/myron_bq_readonly',
}
NAMES = set(MODULE_STEMS)
GIT_HEADS = {
    'common': '41a2024a9e2eb66ab0643a865d74943b4ee3cff8',
    'vendor/qcom/sm8850': '557159b6a0d06f1c6f07ec4c1f22bc9309a113e4',
    'vendor/qcom/sm8850-modules': 'f2ecb6a09ea56bd8ec9a0bfd2e97f45e200ab322',
    'build/kernel': 'e114b907efb6c8ef513617cc13fdc0f87c46abde',
    'prebuilts/clang/host/linux-x86': '77c95e8253c2c82ffd4fee92c0ad9f5ac1e8ca04',
}
VENDOR = 'vendor/qcom/sm8850/'
WRITE_PATHS = {
    VENDOR + 'drivers/soc/qcom/qti_pmic_glink.c',
    VENDOR + 'include/linux/soc/qcom/qti_pmic_glink.h',
    VENDOR + 'drivers/power/supply/myron_mca_readonly/myron_mca_readonly.c',
    VENDOR + 'drivers/power/supply/myron_bq_readonly.c',
    VENDOR + 'drivers/xiaomi/myron/modules.bzl',
    VENDOR + 'drivers/xiaomi/myron/Kconfig',
    VENDOR + 'configs/canoe_perf.bzl',
}

OWN_INPUTS = {
    'r75-build-route/' + name for name in (
        'README.md', 'apply_charge.py', 'build_charge.py', 'check_charge_inputs.py',
        'run_host_tests.py', 'test_integration.py', 'fragments/Kconfig',
        'fragments/canoe_perf.bzl', 'fragments/modules.bzl',
        'payload/drivers/soc/qcom/qti_pmic_glink.c',
        'payload/include/linux/soc/qcom/qti_pmic_glink.h',
        'payload/drivers/power/supply/myron_mca_readonly/myron_mca_readonly.c',
        'payload/drivers/power/supply/myron_bq_readonly.c',
        'reference/qti_pmic_glink.h',
        'tests/transport/run_tests.py', 'tests/transport/fake_kernel.h', 'tests/transport/test_transport.c',
        'tests/client/run_tests.py', 'tests/client/fake_kernel.h', 'tests/client/test_client.c', 'tests/client/test_extra_diagnostics.inc', 'tests/client/qti_pmic_glink.h',
        'tests/gauge/run_tests.py', 'tests/gauge/fake_kernel.h', 'tests/gauge/test_gauge.c',
    )
}
BASE_INPUTS = {
    BASE_CONTRACT, 'r61-build-route/check_battery_inputs.py', 'r61-build-route/apply_battery.py',
    'r61-build-route/targeted_battery_build.py', 'r61-build-route/action_chain.py', 'r61-build-route/sync_with_retry.py',
    'r60-build-route/hardware-contract.json', 'r60-build-route/check_hardware_inputs.py',
    'r55-source/ci/extract_inputs.py', 'r55-source/ci/prepare_legacy.py', 'r55-source/ci/legacy-preparation-lock.json',
    'r61-build-route/payload/drivers/xiaomi/myron/modules.bzl',
    'r61-build-route/payload/drivers/power/supply/myron_bq_readonly.c',
    'r61-build-route/payload/drivers/xiaomi/myron/Kconfig', 'r61-build-route/payload/configs/canoe_perf.bzl',
}

EXPECTED_REPORTING_POLICY = {'reporting_interval_ms': 2000,
 'diagnostic_interval_ms': 5000,
 'notification_fixed_delay_ms': 0,
 'cache_freshness_ms': 15000,
 'diagnostic_round_limit': 60,
 'diagnostic_request_limit': 360,
 'consecutive_timeout_stop': 3,
 'core_snapshot_lines': 7,
 'core_power_supply_properties_unchanged': True,
 'extra_diagnostics': {'module_parameter': 'enable_extra_diagnostics',
                       'default_enabled': False,
                       'requires': ['enable_readonly', 'enable_power_supply'],
                       'trigger': {'fresh_core_online': 1, 'raw_usb_real_type': 11},
                       'runs_per_module_lifetime': 1,
                       'max_total_get_attempts': 5,
                       'max_get_attempts_after_core_publication': 1,
                       'fixed_property_value_bytes': 4,
                       'stop_without_retry_on': ['any_failure', 'core_context_change'],
                       'independent_cache_and_request_count': True,
                       'fixed_properties': [{'name': 'CHG_TYPE', 'id': '0x2002'},
                                            {'name': 'AICL_STATUS', 'id': '0x2029'},
                                            {'name': 'PPS_MAX_CUR', 'id': '0x21013'},
                                            {'name': 'PPS_APDO_MAX', 'id': '0x21014'},
                                            {'name': 'PPS_STATUS', 'id': '0x21019'}],
                       'attribute': 'myron_mca_readonly/diagnostics',
                       'snapshot_lines': 6,
                       'historical': True,
                       'atomic': False},
 'reporting_interval_reference': 'after core and optional single diagnostic work',
 'expiry_watchdog_interval_ms': 1000}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe(root, relative, exists=True):
    p = PurePosixPath(relative)
    require(isinstance(relative, str) and relative and not p.is_absolute() and '..' not in p.parts,
            'Unsafe path: ' + str(relative))
    path = root / p
    require(not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),
            'Redirected path: ' + relative)
    require(not exists or path.is_file(), 'Missing input: ' + relative)
    return path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def overlay_bytes(root, row):
    """Derive an exact postimage from an immutable payload or reviewed append."""
    data = safe(root, row['source']).read_bytes()
    if row['mode'] == 'replace':
        result = data
    elif row['mode'] == 'append':
        before = safe(root, row['preimage']).read_bytes()
        require(sha(before) == row['before_sha256'], 'Append preimage mismatch')
        result = before + data
    else:
        raise ValueError('Unsupported overlay operation')
    require(sha(result) == row['after_sha256'] and len(result) == row['bytes'],
            'Overlay postimage mismatch: ' + row['destination'])
    return result


def header_tokens(data):
    text = data.decode('utf-8')
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    return re.sub(r'\s+', '', text)


def check_client_parameters(data):
    tokens = header_tokens(data)
    names = {'enable_readonly', 'enable_power_supply', 'enable_extra_diagnostics'}
    parameters = re.findall(r'module_param\(([^,]+),([^,]+),([^\)]+)\);', tokens)
    require(len(parameters) == 3 and set(parameters) == {(name, 'bool', '0444') for name in names},
            'Client must expose exactly three read-only boolean parameters')
    for name in names:
        require(len(re.findall(r'staticbool' + name + r'(?:=false)?;', tokens)) == 1,
                'Client boolean opt-ins must default to false: ' + name)


def check_overlay(root, contract):
    require(contract.get('schema') == 1 and contract.get('source_review') == 'PASS',
            'R75 review incomplete; no placeholder hashes accepted')
    require(contract.get('base_commit') == '193c958344ac109faae973a9c6464d1cc7885bfe',
            'Remote source base commit changed')
    require(contract.get('compile_only') is True and contract.get('flashable') is False,
            'R75 must remain compile-only')
    require(contract.get('baseline_image_sha256') == BASE_IMAGE and
            contract.get('baseline_kernel_release') == BASE_RELEASE, 'Baseline identity mismatch')
    require(contract.get('base_contract') == BASE_CONTRACT and
            contract.get('base_contract_sha256') == BASE_SHA256, 'Parent contract changed')
    require(contract.get('sources_lock_sha256') == 'ef3d806f679ac8e0bf1371e6ab6dfc173118a32e3a66f44f684116bc0b52e756',
            'Source/toolchain lock changed')
    require(contract.get('git_heads') == GIT_HEADS, 'Source/toolchain Git HEAD pins changed')
    require(contract.get('runtime_reporting_policy') == EXPECTED_REPORTING_POLICY,
            'R75 reporting/optional GET scope changed')
    rows = contract.get('locked_files', [])
    require(rows, 'Missing R75 source lock')
    locked = {}
    for row in rows:
        require(row['path'] not in locked, 'Duplicate locked path')
        data = safe(root, row['path']).read_bytes()
        require(len(data) == row['bytes'] and sha(data) == row['sha256'],
                'Input bytes/SHA mismatch: ' + row['path'])
        locked[row['path']] = row
    require(set(locked) == OWN_INPUTS | BASE_INPUTS, 'Source lock omits or adds unreviewed inputs')
    actual_files = {str(p.relative_to(root)) for p in (root / 'r75-build-route').rglob('*')
                    if p.is_file() and p.name != 'charge-contract.json' and '__pycache__' not in p.parts}
    require(actual_files == OWN_INPUTS, 'R75 source directory inventory differs from reviewed upload scope')
    require(BASE_CONTRACT in locked and locked[BASE_CONTRACT]['sha256'] == BASE_SHA256,
            'Parent contract must be an exact locked input')
    writes = contract.get('writes', [])
    require({r['destination'] for r in writes} == WRITE_PATHS and len(writes) == len(WRITE_PATHS),
            'R75 write scope differs from approved seven destinations')
    for row in writes:
        require(row['source'] in locked, 'Unlocked overlay input')
        require(row['mode'] in {'replace', 'append'}, 'Unsupported overlay operation')
        require(re.fullmatch('[0-9a-f]{64}', row['after_sha256']), 'Invalid postimage hash')
        require(row['before_sha256'] is None or re.fullmatch('[0-9a-f]{64}', row['before_sha256']),
                'Invalid preimage hash')
        if row['destination'].endswith('/drivers/soc/qcom/qti_pmic_glink.c'):
            require(row['before_sha256'] == 'ec6c7a174c6ab5ed32e39968bb3fdd0c254c5428349411b1630a86bb84ec7e46',
                    'QTI transport preimage changed')
            require(row['after_sha256'] == 'e766099f52c4905cef5b79e9b8203afbd33aaf303f60c6856d75fb9fb3299999',
                    'R75 must retain the reviewed QTI transport')
        elif row['destination'].endswith('/include/linux/soc/qcom/qti_pmic_glink.h'):
            require(row['before_sha256'] == 'a1d6a70007391059ed6c9f42c9279256d1dfadb36ab807715a72393d00dd13a9',
                    'QTI header preimage changed')
            require(row['after_sha256'] == 'b12e923464df2b0f46a872d7be168856adaac0e00b2d7c83c123fc18f5418baa',
                    'R75 must retain the reviewed QTI public header')
        elif row['destination'].endswith('/myron_mca_readonly.c'):
            require(row['before_sha256'] is None, 'New client unexpectedly replaces a source')
        elif row['destination'].endswith('/myron_bq_readonly.c'):
            require(row['before_sha256'] == '6b546907c6d24f164519b14e5e22ccfa78a7ff704c4cb969656b6ef42590b1f9',
                    'Independent gauge preimage changed')
            require(row['after_sha256'] == '92a90ae384cdd48410e5e48d4cef09731252b54e121a57b4bc892b13bd97bae1',
                    'R75 must retain the reviewed R74 independent gauge')
        if row['mode'] == 'append':
            require(row['preimage'] in locked and
                    locked[row['preimage']]['sha256'] == row['before_sha256'], 'Unpinned append preimage')
        overlay_bytes(root, row)
    reference = 'r75-build-route/reference/qti_pmic_glink.h'
    require(reference in locked and locked[reference]['sha256'] ==
            'a1d6a70007391059ed6c9f42c9279256d1dfadb36ab807715a72393d00dd13a9',
            'QTI original public API reference changed')
    public_header = next(r for r in writes if r['destination'] == VENDOR + 'include/linux/soc/qcom/qti_pmic_glink.h')
    public_tokens = header_tokens(overlay_bytes(root, public_header))
    new_decl = 'intpmic_glink_unregister_client_sync(structpmic_glink_client*client);'
    new_stub = 'staticinlineintpmic_glink_unregister_client_sync(structpmic_glink_client*client){return-ENODEV;}'
    require(public_tokens.count(new_decl) == 1 and public_tokens.count(new_stub) == 1,
            'Missing or duplicated synchronous unregister API/stub')
    public_tokens = public_tokens.replace(new_decl, '').replace(new_stub, '')
    require(header_tokens(safe(root, reference).read_bytes()) == public_tokens,
            'Existing QTI public API/layout changed beyond the new paired symbol')
    modules = contract.get('modules', [])
    require({r['module_name'] for r in modules} == NAMES and len(modules) == 3,
            'Only QTI transport, independent read-only client and independent gauge are reviewed')
    require(len({r['target'] for r in modules}) == len(modules), 'Duplicate target')
    by_dest = {r['destination']: r for r in writes}
    expected_sources = {
        'qti_pmic_glink': [VENDOR + 'drivers/soc/qcom/qti_pmic_glink.c',
                           VENDOR + 'include/linux/soc/qcom/qti_pmic_glink.h'],
        'myron_mca_readonly': [VENDOR + 'drivers/power/supply/myron_mca_readonly/myron_mca_readonly.c',
                               VENDOR + 'include/linux/soc/qcom/qti_pmic_glink.h'],
        'myron_bq_readonly': [VENDOR + 'drivers/power/supply/myron_bq_readonly.c'],
    }
    for row in modules:
        require(row['stem'] == MODULE_STEMS[row['module_name']], 'Module stem differs from approved target')
        require(row['target'] == '//vendor/qcom/sm8850:canoe_perf/' + row['stem'], 'Target stem mismatch')
        expected_prefix = 'bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf/' + row['stem'] + '/'
        require(row['output'] == expected_prefix + row['module_name'] + '.ko', 'Unexpected KO output')
        require(row['symvers'] == expected_prefix + 'canoe_perf/' + row['stem'] + '_Module.symvers',
                'Unexpected symvers output')
        require(row['expected_sources'] == expected_sources[row['module_name']], 'Unpinned target sources')
    require(contract.get('core_targets') == ['//common:kernel_aarch64', '//myron_artifact_metadata:kernel_release'],
            'Required core metadata targets changed')
    require(len(contract.get('host_tests', [])) == 3 and
            {r['name'] for r in contract['host_tests']} == {'transport', 'client', 'gauge'},
            'Three production source host-test suites are mandatory')
    for row in contract['host_tests']:
        require(row['script'] in locked and row['source'] in locked, 'Unpinned host test/source')
        require(row['script'] == 'r75-build-route/tests/' + row['name'] + '/run_tests.py' and
                row['result_file'] == 'RESULT.json', 'Host-test path/result changed')
        expected_source = VENDOR + {
            'transport': 'drivers/soc/qcom/qti_pmic_glink.c',
            'client': 'drivers/power/supply/myron_mca_readonly/myron_mca_readonly.c',
            'gauge': 'drivers/power/supply/myron_bq_readonly.c',
        }[row['name']]
        require(row['source'] == by_dest[expected_source]['source'], 'Host test source differs from compiled source')
        require(row.get('header') == (None if row['name'] == 'gauge' else public_header['source']),
                'Production test public-header scope changed')
        if row.get('header'):
            require(row['header'] in locked, 'Unpinned tested public header')
    check_client_parameters(safe(root, 'r75-build-route/payload/drivers/power/supply/myron_mca_readonly/myron_mca_readonly.c').read_bytes())
    fixture = safe(root, 'r75-build-route/tests/client/fake_kernel.h').read_text()
    runner = safe(root, 'r75-build-route/tests/client/run_tests.py').read_text()
    require('#define current get_current()' in fixture and '-Wstrict-prototypes' in runner,
            'Kernel current macro and strict prototypes regression guards required')
    return {'schema': 1, 'status': 'PASS', 'compile_only': True, 'flashable': False,
            'modules': sorted(NAMES), 'locked_files': len(locked), 'writes': len(writes)}


def check(root, contract):
    result = check_overlay(root, contract)
    prior = json.loads(safe(root, BASE_CONTRACT).read_text())
    require(sha(safe(root, BASE_CONTRACT).read_bytes()) == BASE_SHA256, 'Parent bytes mismatch')
    inherited = load('r75_parent_checker', safe(root, 'r61-build-route/check_battery_inputs.py'))
    inherited.check(root, prior)
    hardware_path = safe(root, prior['prerequisite_contract'])
    hardware = json.loads(hardware_path.read_text())
    load('r75_hardware_checker', hardware_path.parent / 'check_hardware_inputs.py').check(root, hardware)
    result['inherited_R60_R61_inputs_verified'] = True
    result['runtime_abi_compatible'] = 'NOT_YET_VALIDATED'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    print(json.dumps(check(root, json.loads((root / 'r75-build-route/charge-contract.json').read_text())), indent=2))
