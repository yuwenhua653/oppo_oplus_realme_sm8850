#!/usr/bin/env python3
"""Keep inactive fuel-gauge and ADC compile proof separate from runtime candidates."""
import json
from pathlib import Path
import subprocess
from apply_power import checked_path, pin, require

PREFIX = '//vendor/qcom/sm8850:canoe_perf/'
SOURCES = 'vendor/qcom/sm8850/'
BQ = 'drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561'
MODULES = [
    {'target': PREFIX + BQ, 'module_name': 'bq27z561', 'output_basename': 'bq27z561.ko', 'expected_sources': [SOURCES + BQ + '.c'], 'role': 'validation_only'},
    {'target': PREFIX + 'drivers/iio/adc/qcom-spmi-adc5-gen3', 'module_name': 'qcom_spmi_adc5_gen3', 'output_basename': 'qcom-spmi-adc5-gen3.ko', 'expected_sources': [SOURCES + 'drivers/iio/adc/qcom-spmi-adc5-gen3.c'], 'role': 'validation_only'},
    {'target': PREFIX + 'drivers/iio/adc/qcom-vadc-common', 'module_name': 'qcom_vadc_common', 'output_basename': 'qcom-vadc-common.ko', 'expected_sources': [SOURCES + 'drivers/iio/adc/qcom-vadc-common.c'], 'role': 'validation_only'},
]


def check_contract(route, contract):
    require(contract.get('validation_only_modules') == MODULES, 'Inactive validation target scope changed')
    source = json.loads((route / 'VALIDATION-SOURCE-CONTRACT.json').read_text())
    require(source.get('schema') == 1 and source.get('activation_allowed') is False and
            source.get('runtime_candidate_module_names') == [], 'Validation contract must never authorize runtime selection')
    require(source.get('source_commit') == '45405ec4b75ac71c60f3178d1be24db312fae3ff', 'Wrong validation base')
    require(len(source['writes']) == 1 and source['writes'][0]['path'] == SOURCES + BQ + '.c', 'Only inactive BQ may be patched')
    expected = {m['expected_sources'][0] for m in MODULES}
    seen = {r['path'] for r in source['writes'] + source['read_only_guards']}
    require(expected <= seen, 'Validation source action inputs lack byte guards')
    return source


def prepare(workspace, route, verify=False):
    workspace, route = Path(workspace).resolve(), Path(route).resolve()
    contract = json.loads((route / 'power-contract.json').read_text())
    source = check_contract(route, contract)
    for row in source['read_only_guards']:
        require(pin(checked_path(workspace, row['path']).read_bytes()) == row['expected'], 'Changed validation source guard: ' + row['path'])
    for row in source['writes']:
        require(pin(checked_path(workspace, row['path']).read_bytes()) == row['after' if verify else 'before'], 'Wrong validation source ' + ('postimage' if verify else 'preimage') + ': ' + row['path'])
    patch_row = source['patch']
    patch = checked_path(route, patch_row['path'])
    require(pin(patch.read_bytes()) == {key: patch_row[key] for key in ('bytes', 'sha256')}, 'Validation patch changed')
    if not verify:
        command = ['patch', '--batch', '--fuzz=0', '--forward', '-p1', '-i', str(patch)]
        cwd = checked_path(workspace, source['patch_working_directory'])
        subprocess.run(command + ['--dry-run'], cwd=cwd, check=True, text=True, capture_output=True)
        subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)
        prepare(workspace, route, verify=True)
    return {'schema': 1, 'status': 'PASS_VALIDATION_POSTIMAGES' if verify else 'PASS_VALIDATION_EXACT_PATCH',
            'role': 'validation_only', 'activation_allowed': False, 'runtime_candidate_module_names': [],
            'source_contract': source}


def resolve(graph, contract, resolver):
    selected = []
    for module in contract['validation_only_modules']:
        # Bazel output uses hyphens; Linux ELF module identity uses underscores.
        request = dict(module, module_name=module['output_basename'][:-3])
        actual = resolver.resolve(graph, request)
        selected.append(dict(actual, module_name=module['module_name']))
    return selected


def finalize(output, contract, selected, build_status):
    inventory_path = output / 'module-inventory.json'
    inventory = json.loads(inventory_path.read_text())
    names = sorted(module['module_name'] for module in MODULES)
    require(inventory['required_module_names'] == names and inventory['module_count'] == len(names), 'Wrong validation-only ELF inventory')
    require(sorted(row['name'] for row in inventory['modules']) == names, 'Validation module identity mismatch')
    policy = {'role': 'validation_only', 'activation_allowed': False, 'runtime_candidate_module_names': [],
              'runtime_abi_compatible': 'NOT_YET_VALIDATED',
              'limitation': 'These KOs are inactive source-validation outputs. Full BQ has a known stock/source FG buffer-layout difference. ADC/VADC require separate retained-kernel/provider ABI, exact DT and runtime load review. No full MCA, firmware update or high-voltage control is authorized.'}
    for filename in ('module-inventory.json', 'module-identity.json', 'artifact-manifest.json'):
        path = output / filename
        data = json.loads(path.read_text())
        data.update(policy)
        path.write_text(json.dumps(data, indent=2) + '\n')
    from elf_contract import parse_elf
    evidence = []
    for row in inventory['modules']:
        elf = parse_elf((output / row['file']).read_bytes())
        evidence.append({'module': elf['name'], 'file': row['file'], 'sha256': row['sha256'],
                         'imports': sorted(elf['imports']), 'import_crcs': {k: hex(v) for k, v in sorted(elf['versions'].items())},
                         'exports': sorted(elf['exports']), 'export_crcs': {k: hex(v) for k, v in sorted(elf['export_crcs'].items())},
                         'depends': elf['depends'], 'modinfo': elf['info']})
    report = {'schema': 1, 'status': 'PASS_INACTIVE_COMPILE_OUTPUTS', **policy, **build_status,
              'selected_targets': selected, 'module_abi_evidence': evidence}
    (output / 'validation-only-policy.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def verify_effective_config(root, graph):
    config_target = '//vendor/qcom/sm8850:canoe_perf_config'
    targets = {str(r['id']): r['label'] for r in graph.get('targets', [])}
    fragments = {str(r['id']): r for r in graph.get('pathFragments', [])}
    def fragment_path(key, seen=None):
        key = str(key)
        seen = set() if seen is None else seen
        require(key in fragments and key not in seen, 'Invalid config artifact path')
        seen.add(key)
        row = fragments[key]
        parent = str(row.get('parentId', '0'))
        result = (fragment_path(parent, seen) + '/' if parent not in ('', '0') else '') + row['label']
        seen.remove(key)
        return result
    artifacts = {str(r['id']): r.get('execPath') or fragment_path(r['pathFragmentId']) for r in graph.get('artifacts', [])}
    dep_sets = {str(r['id']): r for r in graph.get('depSetOfFiles', [])}
    def input_artifacts(keys, seen=None):
        seen = set() if seen is None else seen
        found = set()
        for key in keys:
            key = str(key)
            require(key in dep_sets and key not in seen, 'Invalid config input depset')
            seen.add(key)
            row = dep_sets[key]
            found.update(str(x) for x in row.get('directArtifactIds', []))
            found.update(input_artifacts(row.get('transitiveDepSetIds', []), seen))
            seen.remove(key)
        return found
    actions = [a for a in graph.get('actions', []) if targets.get(str(a.get('targetId'))) == config_target and a.get('mnemonic') == 'DdkConfig']
    require(len(actions) == 1, 'Missing actual external module config action')
    tree_path = 'bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf_config/out_dir'
    trees = [str(i) for i in actions[0].get('outputIds', []) if artifacts[str(i)] == tree_path]
    require(len(trees) == 1, 'Actual config action must own reviewed config tree')
    adc_target = MODULES[1]['target']
    adc_actions = [a for a in graph.get('actions', []) if targets.get(str(a.get('targetId'))) == adc_target and a.get('mnemonic') == 'KernelModule']
    require(len(adc_actions) == 1, 'Missing actual ADC KernelModule action')
    adc_action = adc_actions[0]
    consumed = input_artifacts(adc_action.get('inputDepSetIds', []))
    require(trees[0] in consumed, 'ADC action does not consume reviewed config tree')
    own_actions = [a for a in graph.get('actions', []) if targets.get(str(a.get('targetId'))) == adc_target + '_config']
    require(not any(a.get('mnemonic') == 'DdkConfig' for a in own_actions), 'Unexpected ADC per-module config override requires review')
    setup = [str(i) for a in own_actions for i in a.get('outputIds', []) if artifacts[str(i)].endswith('_config_setup.sh')]
    require(len(setup) == 1 and setup[0] in consumed and artifacts[setup[0]] in '\n'.join(adc_action.get('arguments', [])), 'Actual ADC config setup must be target-owned and consumed by compile command')
    relative = tree_path + '/.config'
    require(relative in '\n'.join(actions[0].get('arguments', [])), 'Actual config action must materialize .config')
    data = (root / relative).read_bytes()
    settings = dict(line.split('=', 1) for line in data.decode().splitlines() if line.startswith('CONFIG_') and '=' in line)
    require(settings.get('CONFIG_QCOM_SPMI_ADC5_GEN3') == 'm' and settings.get('CONFIG_QCOM_VADC_COMMON') == 'm', 'Expected ADC modules are not enabled in actual external config')
    require(settings.get('CONFIG_QCOM_SPMI_ADC5_GEN3_DEBUG_LOGGING', 'n') == 'n', 'ADC panic-on-debug fault option must stay disabled')
    return {'schema': 1, 'status': 'PASS_ACTUAL_ADC_CONFIG', 'config_path': relative, **pin(data),
            'target_owned_setup': artifacts[setup[0]], 'config_tree_consumed_by_actual_adc_action': True,
            'settings': {k: settings.get(k, 'n') for k in ('CONFIG_QCOM_SPMI_ADC5_GEN3', 'CONFIG_QCOM_VADC_COMMON', 'CONFIG_QCOM_SPMI_ADC5_GEN3_DEBUG_LOGGING')},
            'activation_allowed': False}
