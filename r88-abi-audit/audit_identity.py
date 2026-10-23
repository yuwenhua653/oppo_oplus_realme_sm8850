#!/usr/bin/env python3
"""Audit real R88 artifact bytes and compilation provenance; never run CI commands.

All changing identities are explicit required CLI inputs. No earlier CI identity is a
default or accepted as an R88 route. This only produces a local audit report.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

PREFIX = 'vendor/qcom/sm8850/'
MCA = PREFIX + 'drivers/power/supply/mca/'
CP = MCA + 'mca_hardware_ic/charge_pump_ic/sc8581/sc8581.c'
BQ = MCA + 'mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561.c'
BQ_HEADER = MCA + 'mca_hardware_ic/fuelgauge_ic/bq27z561/inc/bq27z561.h'
QUICKCHG = MCA + 'mca_strategy/strategy_charger/mca_strategy_quickchg.c'
FG = MCA + 'mca_strategy/strategy_fg/mca_strategy_fg.c'
FG_HEADER = MCA + 'mca_strategy/strategy_fg/inc/strategy_fg.h'
SOC = MCA + 'mca_strategy/strategy_fg/mca_soc_smooth.c'
CONFIG_SOURCE = PREFIX + 'configs/canoe_perf.bzl'
REQUIRED_WRITES = {FG, FG_HEADER, SOC}
REQUIRED_GUARDS = {
    BQ, BQ_HEADER, CP, QUICKCHG, CONFIG_SOURCE,
    MCA + 'mca_shared_memory/charger_partition.c',
    MCA + 'include/mca/platform/platform_fg_ic_ops.h',
    MCA + 'mca_business/business_charger/mca_charger_usb_psy.c',
    MCA + 'mca_common/mca_adsp_glink.c',
    MCA + 'mca_qcom_subpmic_proxy/mca_qcom_subpmic_proxy.c',
}
FALSE_FLAGS = ('activation_allowed', 'flashable', 'full_charging_control_enabled')


def need(value, message):
    if not value:
        raise RuntimeError(message)


def read(path):
    return json.loads(path.read_text())


def pin(path):
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
            size += len(chunk)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def safe(root, name):
    need(isinstance(name, str) and name and '\\' not in name, 'nonempty POSIX member')
    parts = PurePosixPath(name)
    need(not parts.is_absolute() and '..' not in parts.parts and str(parts) == name,
         'canonical relative member: ' + name)
    path = root.joinpath(*parts.parts)
    need(path.resolve().is_relative_to(root.resolve()), 'no escaping member: ' + name)
    need(all(not root.joinpath(*parts.parts[:i]).is_symlink()
             for i in range(1, len(parts.parts) + 1)), 'no member symlink: ' + name)
    return path


def match(path, row):
    need(path.is_file() and pin(path) == {k: row[k] for k in ('bytes', 'sha256')},
         'wrong member bytes: ' + str(path))


def unique(rows, key, scope):
    names = [row[key] for row in rows]
    need(len(names) == len(set(names)), 'unique ' + scope)
    return names


def inactive(record, scope, has_flashable=True):
    for flag in FALSE_FLAGS if has_flashable else ('activation_allowed', 'full_charging_control_enabled'):
        need(record.get(flag) is False, scope + ' stays inactive: ' + flag)
    need(record.get('compile_only') is True, scope + ' compile-only')
    if 'runtime_candidate_module_names' in record:
        need(record['runtime_candidate_module_names'] == [], scope + ' has no runtime candidates')


def add_identity_arguments(parser):
    parser.add_argument('--candidate', type=Path, required=True, help='Extracted real R88 validation artifact root')
    parser.add_argument('--ci-head', required=True)
    parser.add_argument('--ci-run', required=True)
    parser.add_argument('--ci-attempt', type=int, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--build-sha256', required=True)
    parser.add_argument('--validation-zip', type=Path, required=True)
    parser.add_argument('--validation-zip-sha256', required=True)
    parser.add_argument('--reports-zip', type=Path, required=True)
    parser.add_argument('--reports-zip-sha256', required=True)
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parent)


class Graph:
    """Reconstruct actual source -> compile -> staging -> copied KO paths."""
    def __init__(self, document):
        self.fragments = {str(r['id']): r for r in document.get('pathFragments', [])}
        self.path_cache = {}
        self.artifacts = {str(r['id']): r.get('execPath') or self.fragment(r['pathFragmentId'])
                          for r in document.get('artifacts', [])}
        self.sets = {str(r['id']): r for r in document.get('depSetOfFiles', [])}
        self.input_cache = {}
        self.declared_cache = {}
        self.labels = {str(r['id']): r['label'] for r in document.get('targets', [])}
        self.actions = document.get('actions', [])
        self.rows = []
        self.producers = {}
        for action in self.actions:
            row = {'action': action, 'outputs': {self.artifacts[str(k)] for k in action.get('outputIds', [])}}
            self.rows.append(row)
            for output in row['outputs']:
                self.producers.setdefault(output, []).append(row)

    def fragment(self, key, seen=None):
        key = str(key)
        if key in self.path_cache:
            return self.path_cache[key]
        seen = set() if seen is None else seen
        need(key in self.fragments and key not in seen, 'acyclic path fragment')
        seen.add(key)
        row = self.fragments[key]
        parent = str(row.get('parentId', '0'))
        value = (self.fragment(parent, seen) + '/' if parent not in ('0', '') else '') + row['label']
        seen.remove(key)
        self.path_cache[key] = value
        return value

    def inputs(self, key, seen=None):
        key = str(key)
        if key in self.input_cache:
            return self.input_cache[key]
        seen = set() if seen is None else seen
        need(key in self.sets and key not in seen, 'acyclic input depset')
        seen.add(key)
        row = self.sets[key]
        result = {self.artifacts[str(k)] for k in row.get('directArtifactIds', [])}
        for child in row.get('transitiveDepSetIds', []):
            result.update(self.inputs(child, seen))
        seen.remove(key)
        self.input_cache[key] = result
        return result

    def declared(self, action):
        key = id(action)
        if key not in self.declared_cache:
            self.declared_cache[key] = set().union(*(self.inputs(k) for k in action.get('inputDepSetIds', [])))
        return self.declared_cache[key]

    def chain(self, sources, output):
        final = self.producers.get(output, [])
        need(len(final) == 1, 'one final KO action: ' + output)
        final = final[0]
        required = set(sources)
        need(required, 'nonempty actual source action inputs')
        final_inputs = self.declared(final['action'])
        candidates = []
        for row in self.rows:
            action = row['action']
            if action.get('mnemonic') != 'KernelModule' or not required <= self.declared(action):
                continue
            if row is final:
                candidates.append((row, 'direct', [output]))
            elif final['action'].get('mnemonic') == 'KernelModuleCpOutputs':
                staging = sorted(p for p in row['outputs'] & final_inputs if p.endswith('/staging'))
                if len(staging) == 1:
                    candidates.append((row, 'staging-copy', staging))
        need(len(candidates) == 1, 'one source-bound compiler-to-KO chain: ' + output)
        row, kind, intermediates = candidates[0]
        action = row['action']
        return {
            'schema': 1, 'status': 'PASS', 'kind': kind, 'required_sources': sorted(required),
            'output': output, 'intermediate_artifacts': intermediates,
            'compile_mnemonic': action.get('mnemonic'), 'compile_action_key': action.get('actionKey'),
            'final_mnemonic': final['action'].get('mnemonic'),
            'final_action_key': final['action'].get('actionKey'),
            'compile_declared_input_count': len(self.declared(action)),
            'limits': 'Graph provenance only; hash locked sources, ELF ABI and hardware behavior require separate gates.',
        }, action


def zip_inventory(path, expected_sha):
    record = pin(path)
    need(record['sha256'] == expected_sha, 'downloaded ZIP pin: ' + str(path))
    archive = zipfile.ZipFile(path)
    members = {}
    for row in archive.infolist():
        if row.is_dir():
            continue
        name = row.filename
        safe(Path('/unused-artifact-root'), name)
        need(name not in members, 'unique ZIP member: ' + name)
        mode = row.external_attr >> 16
        need(not stat.S_ISLNK(mode), 'no ZIP symlink: ' + name)
        members[name] = row
    return archive, members, dict(file=str(path.resolve()), member_count=len(members), **record)


def zip_pin(archive, member):
    digest = hashlib.sha256()
    size = 0
    with archive.open(member) as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
            size += len(chunk)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def workflow_report_selected(relative):
    """Exact diagnostic upload scope, relative to integration-reports/."""
    parts = PurePosixPath(relative)
    supported = parts.suffix in ('.json', '.log', '.txt')
    return supported and ((len(parts.parts) == 1 and parts.name.startswith('r88-')) or
                          (len(parts.parts) > 1 and parts.parts[0] == 'r88-host'))


def audit_identity(args):
    need(re.fullmatch(r'[0-9a-f]{40}', args.ci_head), 'explicit 40-digit CI head')
    need(args.ci_head not in ('b25d73a0dc1f606e51c21214b0beafaa5dae4496',
         'ae4bf5b38ae1771e0f440b8b26b02cd66a008231'), 'actual new R88 CI head required')
    need(re.fullmatch(r'[1-9][0-9]*', args.ci_run) and args.ci_attempt > 0, 'real CI run and attempt')
    for field in ('source_sha256', 'build_sha256', 'validation_zip_sha256', 'reports_zip_sha256'):
        need(re.fullmatch(r'[0-9a-f]{64}', getattr(args, field)), 'explicit SHA256: ' + field)
    ci = args.candidate.resolve()
    need(ci.is_dir() and not args.candidate.is_symlink(), 'candidate directory, not symlink')
    complete = read(safe(ci, 'validation-complete.json'))
    lock_path = safe(ci, 'artifact-lock.json')
    lock = read(lock_path)
    need(complete['artifact_lock_sha256'] == pin(lock_path)['sha256'], 'completion lock identity')
    need(complete['build_contract_sha256'] == args.build_sha256, 'expected R88 build contract')
    need(complete['source_contract_sha256'] == args.source_sha256, 'expected R88 source contract')
    names = unique(lock['files'], 'file', 'artifact lock members')
    for row in lock['files']:
        match(safe(ci, row['file']), row)
    actual = set()
    for path in ci.rglob('*'):
        need(not path.is_symlink(), 'no artifact symlink: ' + str(path))
        if path.is_file():
            actual.add(str(path.relative_to(ci)))
    need(actual == set(names) | {'artifact-lock.json', 'validation-complete.json'}, 'complete lock inventory')
    need(complete['full_validation_success'] is True and complete['required_module_count'] == 47,
         'successful complete47 compile')
    for label, record in (('completion', complete), ('artifact lock', lock)):
        inactive(record, label)
    status_path = safe(ci, 'reports/r88-status.json')
    need(status_path.is_file(), 'actual R88 CI status required; older artifacts do not qualify')
    status = read(status_path)
    identity = {'GITHUB_SHA': args.ci_head, 'GITHUB_RUN_ID': args.ci_run,
                'GITHUB_RUN_ATTEMPT': str(args.ci_attempt)}
    need(status['github'] == identity and status['success'] is True and status['validation_compiled'] is True,
         'successful exact R88 run')
    need(status['source_contract_sha256'] == args.source_sha256 and
         status['build_contract_sha256'] == args.build_sha256, 'status contract identities')
    inactive(status, 'CI status')
    route = safe(ci, 'source/r88-build-route')
    build_path = safe(ci, 'build-contract.json')
    source_path = safe(ci, 'source/r88-build-route/SOURCE-CONTRACT.json')
    need(pin(build_path)['sha256'] == args.build_sha256 and pin(source_path)['sha256'] == args.source_sha256,
         'copied contracts match reviewed pins')
    need(safe(route, 'build-contract.json').read_bytes() == build_path.read_bytes(), 'route/root build copies equal')
    build, source = read(build_path), read(source_path)
    need(build['source_contract'] == pin(source_path), 'build contract binds exact source contract')
    for label, record in (('build contract', build), ('source contract', source)):
        need(record.get('schema') == 1 and record.get('review_status') == 'FROZEN_REVIEWED_SOURCE',
             'frozen reviewed ' + label)
        inactive(record, label, has_flashable=label != 'source contract')
    need(build.get('modules') == [] and build['parent_contract'] == 'r87-build-route/build-contract.json',
         'R88 overlay ancestry and inactive candidate role')
    need(source.get('source_commit') == build.get('base_commit') ==
         'b25d73a0dc1f606e51c21214b0beafaa5dae4496' and
         source.get('preparation_parent_contract_sha256') == build.get('parent_contract_sha256') ==
         'ec8e557f2486a97a6fd2577b82e10727a2b9a8e73c7ea0efc62bb580b36eecbe' and
         source.get('parent_source_contract_sha256') ==
         '4a4be491f873447a5249f175b3f2e1254b529d7abf4258400c06bdc5d618cad7',
         'exact frozen R87 preparation ancestry')
    locked = unique(build['locked_files'], 'path', 'route inputs')
    need(locked and all(name.startswith('r88-build-route/') for name in locked), 'only exact R88 route inputs')
    route_files = {str(p.relative_to(ci / 'source')) for p in route.rglob('*')
                   if p.is_file() and p.name != 'build-contract.json'}
    need(route_files == set(locked), 'complete exact frozen source route inventory')
    for row in build['locked_files']:
        match(safe(ci / 'source', row['path']), row)
    writes = unique(source['writes'], 'path', 'source writes')
    guards = unique(source['read_only_guards'], 'path', 'source guards')
    need(set(writes) == REQUIRED_WRITES, 'R88 exact FG, private header and SOC write scope')
    need(set(guards) == REQUIRED_GUARDS and not set(writes) & set(guards), 'complete disjoint R88 guard scope')
    expected = {row['path']: (row['after'], 'changed') for row in source['writes']}
    expected.update({row['path']: (row['expected'], 'unchanged_guard') for row in source['read_only_guards']})
    snapshots = unique(complete['compiled_sources'], 'file', 'compiled snapshots')
    need(set(snapshots) == {'compiled-source/' + name for name in expected}, 'all and only writes+guards snapshots')
    for row in complete['compiled_sources']:
        name = row['file'].removeprefix('compiled-source/')
        record, role = expected[name]
        need({k: row[k] for k in ('bytes', 'sha256')} == record and row.get('role') == role,
             'compiled write/guard contract identity: ' + name)
        match(safe(ci, row['file']), row)
    need({str(p.relative_to(ci / 'compiled-source')) for p in (ci / 'compiled-source').rglob('*') if p.is_file()}
         == set(expected), 'no unlisted compiled source files')
    inventory = read(safe(ci, 'module-inventory.json'))
    modules = unique(inventory['modules'], 'name', 'module names')
    need(inventory['module_count'] == len(modules) == 47 and
         len(inventory['required_module_names']) == len(set(inventory['required_module_names'])) == 47 and
         set(modules) == set(inventory['required_module_names']), 'exact required47 inventory')
    inactive(inventory, 'module inventory')
    need(inventory['runtime_candidate_module_names'] == [], 'no active module candidates')
    for row in inventory['modules']:
        match(safe(ci, row['file']), row)
    selected = build['validation_only_modules']
    need(len(unique(selected, 'module_name', 'selected build modules')) == 47 and
         {row['module_name'] for row in selected} == set(modules), 'selected targets match exact47')
    config_path = safe(ci, 'module-config/canoe_perf.config')
    config = config_path.read_text()
    assignments = re.findall(r'^CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING=(.*)$', config, re.M)
    need(all(value == 'n' for value in assignments), 'IC firmware programming disabled')
    effective = read(safe(ci, 'reports/r88-effective-bq-config.json'))
    postbuild = read(safe(ci, 'reports/r88-bq-config-postbuild.json'))
    need(pin(config_path) == {k: effective[k] for k in ('bytes', 'sha256')} ==
         {k: postbuild[k] for k in ('bytes', 'sha256')}, 'emitted config matches before/after build')
    graph_path = safe(ci, 'reports/r88-aquery.json')
    graph = Graph(read(graph_path))
    config_actions = [a for a in graph.actions if a.get('mnemonic') == 'DdkConfig' and
                      graph.labels.get(str(a.get('targetId'))) == '//vendor/qcom/sm8850:canoe_perf_config']
    need(len(config_actions) == 1, 'one actual external config generator')
    config_action = config_actions[0]
    tree = 'bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf_config/out_dir'
    need(tree in {graph.artifacts[str(k)] for k in config_action['outputIds']}, 'config action owns output tree')
    need(effective['config_path'] == tree + '/.config' == postbuild['config_path'] and
         effective['config_path'] in '\n'.join(config_action['arguments']), 'reviewed .config actually generated')
    action_results, coverage, unsnapshotted = {}, {name: [] for name in expected}, {}
    for row in selected:
        module = row['module_name']
        report = read(safe(ci, 'reports/r88-action-' + module + '.json'))
        required = list(row['expected_sources'])
        if module == 'bq27z561':
            required.append(BQ_HEADER)
        if module == 'mca_strategy_fg_comp':
            required.append(FG_HEADER)
        need(len(required) == len(set(required)) and set(report['required_sources']) == set(required),
             'complete contract-derived action sources: ' + module)
        need(report['output'].endswith('/' + module + '.ko') and
             next(r['file'] for r in inventory['modules'] if r['name'] == module) == 'objects/' + report['output'],
             'action output is the inventoried KO: ' + module)
        calculated, action = graph.chain(required, report['output'])
        need(calculated == {k: report[k] for k in calculated}, 'independent real action chain: ' + module)
        declared = graph.declared(action)
        target = graph.labels[str(action['targetId'])]
        need(target == row['target'] and tree in declared, 'selected target consumes actual config: ' + module)
        own_config = [a for a in graph.actions if graph.labels.get(str(a.get('targetId'))) == target + '_config']
        need(not any(a.get('mnemonic') == 'DdkConfig' for a in own_config), 'no target config override: ' + module)
        setups = [graph.artifacts[str(k)] for a in own_config for k in a.get('outputIds', [])
                  if graph.artifacts[str(k)].endswith('_config_setup.sh')]
        need(len(setups) == 1 and setups[0] in declared and setups[0] in '\n'.join(action['arguments']),
             'target-owned setup consumed by actual compiler: ' + module)
        need(set(report['workspace_source_pins']) == set(required), 'complete workspace action source pins: ' + module)
        for original, record in report['workspace_source_pins'].items():
            if original in expected:
                need(record == expected[original][0], 'action source matches guarded/changed snapshot: ' + original)
            else:
                need(record.get('bytes', 0) > 0 and re.fullmatch(r'[0-9a-f]{64}', record.get('sha256', '')),
                     'well-formed action-only source pin')
                unsnapshotted[original] = record
        for original in set(expected) & declared:
            coverage[original].append(module)
        action_results[module] = dict(calculated, target=target, config_tree_input=tree,
                                      target_owned_setup=setups[0], workspace_source_pins=report['workspace_source_pins'])
    # Bazel .bzl files are analysis inputs and need not appear as execution
    # action inputs. Their frozen source snapshot and actual emitted .config
    # are checked separately; do not invent a direct DdkConfig input edge.
    config_source_declared = CONFIG_SOURCE in graph.declared(config_action)
    if config_source_declared:
        coverage[CONFIG_SOURCE].append('//vendor/qcom/sm8850:canoe_perf_config')
    need(all(consumers for name, consumers in coverage.items() if name != CONFIG_SOURCE),
         'each guarded/changed C or header is declared by a selected real compiler')
    for module, must_have in {'sc8581': {CP}, 'mca_strategy_quickchg': {QUICKCHG},
                              'bq27z561': {BQ, BQ_HEADER}, 'mca_strategy_fg_comp': {FG, FG_HEADER, SOC}}.items():
        need(must_have <= set(action_results[module]['required_sources']), 'mandatory CP/quickchg/BQ/FG provenance')
    archives = []
    archive, members, record = zip_inventory(args.validation_zip, args.validation_zip_sha256)
    try:
        need(set(members) == actual, 'validation ZIP and extracted inventory identical')
        for name in members:
            need(zip_pin(archive, members[name]) == pin(safe(ci, name)), 'ZIP/extracted bytes: ' + name)
    finally:
        archive.close()
    archives.append(record)
    archive, members, record = zip_inventory(args.reports_zip, args.reports_zip_sha256)
    copied_reports = [name for name in actual if name.startswith('reports/')]
    selected_reports = [name for name in copied_reports if workflow_report_selected(name.removeprefix('reports/'))]
    validation_only_reports = []
    try:
        original_selected = set()
        for member in members:
            if '/integration-reports/' in member:
                relative = member.split('/integration-reports/', 1)[1]
                if workflow_report_selected(relative):
                    original_selected.add('reports/' + relative)
        need(original_selected == set(selected_reports), 'complete workflow-selected original/copied reports inventory')
        for name in sorted(selected_reports):
            suffix = '/integration-reports/' + name.removeprefix('reports/')
            matches = [member for member in members if member.endswith(suffix)]
            need(len(matches) == 1, 'one original reports ZIP member: ' + name)
            need(zip_pin(archive, members[matches[0]]) == pin(safe(ci, name)), 'original/copied report bytes: ' + name)
        for name in sorted(set(copied_reports) - set(selected_reports)):
            parts = PurePosixPath(name)
            need(len(parts.parts) > 2 and parts.parts[1] in ('r88-parent-r85-host', 'r88-parent-r86-host', 'r88-parent-r87-host') and
                 parts.suffix in ('.json', '.log', '.txt'), 'explicit validation-only report duplicate scope: ' + name)
            suffix = '/integration-reports/' + name.removeprefix('reports/')
            matches = [member for member in members if member.endswith(suffix)]
            need(len(matches) <= 1, 'unique optional original duplicate: ' + name)
            if matches:
                need(zip_pin(archive, members[matches[0]]) == pin(safe(ci, name)), 'optional original duplicate bytes: ' + name)
            validation_only_reports.append({
                'file': name, **pin(safe(ci, name)), 'expected_in_reports_zip': False,
                'present_in_reports_zip': bool(matches),
                'verification': 'Validation artifact lock and validation ZIP verified; validation-only report duplicate not expected by diagnostic upload globs.',
            })
    finally:
        archive.close()
    record['copied_reports_verified'] = len(selected_reports)
    record['validation_only_report_duplicates'] = validation_only_reports
    archives.append(record)
    return {
        'schema': 1, 'status': 'PASS_R88_EXACT_ARTIFACT_IDENTITY', 'ci': identity,
        'activation_allowed': False, 'flashable': False, 'hardware_tested': False,
        'full_charging_control_enabled': False, 'candidate': str(ci), 'artifact_zips': archives,
        'artifact_lock': pin(lock_path), 'verified_lock_members': len(names),
        'verified_build_locked_files': len(locked), 'completion': pin(ci / 'validation-complete.json'),
        'source_contract': pin(source_path), 'build_contract': pin(build_path),
        'compiled_sources': complete['compiled_sources'], 'compiled_changed_count': len(writes),
        'compiled_guard_count': len(guards), 'compiled_snapshot_action_coverage': coverage,
        'configuration_source_guard': {
            'source': CONFIG_SOURCE, **expected[CONFIG_SOURCE][0],
            'declared_DdkConfig_execution_input': config_source_declared,
            'scope': 'Frozen Starlark source snapshot plus separately verified actual emitted config; no direct execution-input edge is inferred.',
        },
        'module_count': 47, 'module_files_verified': 47, 'required_module_names': sorted(modules),
        'actual_effective_config': dict(file=str(config_path), **pin(config_path),
            symbol='CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING', raw_assignments=assignments,
            disabled=True, interpretation='No y/m/1 definition; unset symbol is false for IS_ENABLED.'),
        'aquery': pin(graph_path), 'actual_module_actions': action_results,
        'action_source_pins_without_independent_snapshots': unsnapshotted,
        'limits': [
            'Identity, byte inventory, source snapshots and declared action/config provenance only; no semantic source review assertion.',
            'Unchanged action inputs outside writes/guards have CI-recorded pins, not independent compiled-source snapshots.',
            'Parent R85/R86/R87 host report duplicates are verified by the validation artifact lock and ZIP; diagnostics upload globs include only top-level r88-* reports and nested r88-host reports.',
            'Retained-kernel ABI/CFI, exclusive runtime ownership, authentication, thermal behavior, fast charging and flash readiness require separate gates.',
        ], 'reviewer': pin(Path(__file__).resolve()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_identity_arguments(parser)
    args = parser.parse_args()
    result = audit_identity(args)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'ARTIFACT-IDENTITY.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'verified_lock_members', 'verified_build_locked_files',
                                           'compiled_changed_count', 'compiled_guard_count', 'module_count')}))


if __name__ == '__main__':
    main()
