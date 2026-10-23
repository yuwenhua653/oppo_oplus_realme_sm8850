#!/usr/bin/env python3
"""Reparse real R87 KOs against the healthy R84 Image and 251 retained KOs.

All R87 CI/contract/ZIP pins are required. The result is a hypothetical static
247+47=294 ELF closure, never module loading or image/flash authorization.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

from audit_identity import WORKSPACE, add_identity_arguments, audit_identity, need, pin, read, safe

IMAGE_SHA = '2fa774b4ffdd75064fb733bb2cad071b02b1813ad5cd54bae32bda2247ef18a7'
SYMVERS_SHA = '9d69a48179b0288dbd452dffc061f7754fba09d507fba3086161dfb019c496e3'
CONFIG_SHA = '1694fba9900e978fb9494250fb5be8515d022b8b52062721b1a2d267f92490c0'
CONTRACT_SHA = 'e68871a2a6654a0c1bd3d0630474e5b79c60281791aeec5f63c1e9d37dbe691e'
PARSER_SHA = '3ff542a4e55571b6d4af428cf3388973a36f313704b6848e0aab47d4ddea7c46'
VENDOR_PIN = {'bytes': 100663296, 'sha256': 'ade202a830574da27af940c06c828dc1e9b279749b96b524468f24423745cae8'}
VERMAGIC = ['6.12.81-android16-6-maybe-dirty-4k SMP preempt mod_unload modversions aarch64']
GPL_LICENSES = {'GPL', 'GPL v2', 'GPL and additional rights', 'Dual BSD/GPL', 'Dual MIT/GPL', 'Dual MPL/GPL'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_record(path):
    return {'path': str(path.resolve()), **pin(path)}


def norm(name):
    return name.replace('-', '_')


def topological(checks, selected):
    pending = {name: set(checks[name]['providers']) & selected for name in selected}
    ordered = []
    while pending:
        ready = sorted(name for name, deps in pending.items() if not deps)
        if not ready:
            break
        ordered.extend(ready)
        for name in ready:
            del pending[name]
        for deps in pending.values():
            deps.difference_update(ready)
    return ordered, {name: sorted(deps) for name, deps in pending.items()}


def audit_closure(args):
    # Re-audit all exact source/action/config/ZIP inputs, independently of any
    # existing ARTIFACT-IDENTITY.json report. Nothing is written on this path.
    identity = audit_identity(args)
    ci = args.candidate.resolve()
    reference = args.reference_dir.resolve()
    runtime = reference / 'runtime-reference'
    baseline_dir = args.baseline_dir.resolve()
    parser_path = args.elf_parser.resolve()
    need(pin(parser_path)['sha256'] == PARSER_SHA, 'unchanged independently reviewed ELF parser')
    spec = importlib.util.spec_from_file_location('r87_frozen_elf_review', parser_path)
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)

    def review(path):
        elf = parser.Elf(path)
        result = elf.review()
        result['signature_marker'] = elf.data.endswith(b'~Module signature appended~\n')
        return result

    need(pin(args.retained_vendor_boot) == VENDOR_PIN, 'actual healthy R84 vendor_boot bytes')
    image_path = runtime / 'Image'
    image = image_path.read_bytes()
    need(sha(image) == IMAGE_SHA, 'actual retained R84 Image, never newly built CI Image')
    need(pin(runtime / 'vmlinux.symvers')['sha256'] == SYMVERS_SHA, 'actual retained symvers')
    need(pin(runtime / 'kernel_aarch64_dot_config')['sha256'] == CONFIG_SHA, 'actual retained kernel config')

    def string(offset):
        need(0 <= offset < len(image), 'Image string bounds')
        end = image.index(b'\0', offset)
        need(end - offset < 512, 'Image string length')
        return image[offset:end].decode('ascii')

    core = {}
    for line in (runtime / 'vmlinux.symvers').read_text().splitlines():
        row = line.split('\t')
        need(row[1] not in core, 'unique retained symvers symbol')
        core[row[1]] = {'crc': row[0], 'provider': row[2], 'type': row[3],
                        'namespace': row[4] if len(row) > 4 else ''}
    actual = {}
    export_policy_path = reference / 'output-review/RUNTIME-KERNEL-POLICY.json'
    for kind, table in read(export_policy_path)['actual_exports']['tables'].items():
        names = []
        for index in range(table['count']):
            offset = table['ksymtab_offset'] + index * 12
            _, name, namespace = struct.unpack_from('<iii', image, offset)
            symbol = string(offset + 4 + name)
            namespace = string(offset + 8 + namespace)
            names.append(symbol)
            need(symbol not in actual, 'unique actual Image export')
            actual[symbol] = {
                'crc': f'0x{struct.unpack_from("<I", image, table["crc_offset"] + 4 * index)[0]:08x}',
                'provider': 'vmlinux', 'type': kind, 'namespace': namespace,
            }
        need(names == sorted(names), 'actual Image sorted export table')
    need(actual == core and len(actual) == 10226, 'actual Image exports equal actual retained symvers')
    policy_path = reference / 'gauge-review/RUNTIME-POLICY-TABLES.json'
    policy = read(policy_path)
    policy_names = {}
    virtual_base = int(policy['virtual_to_file_base'], 16)
    need(policy['source_Image']['sha256'] == sha(image), 'unsigned policy belongs to retained Image')
    for key, table in policy['tables'].items():
        raw = image[table['pointer_table_offset']:table['pointer_table_offset'] + 8 * table['count']]
        need(sha(raw) == table['pointer_bytes_sha256'], 'actual unsigned policy pointers')
        names = [string(struct.unpack_from('<Q', raw, index * 8)[0] - virtual_base)
                 for index in range(table['count'])]
        need(names == table['names'] and names == sorted(set(names)), 'actual unsigned policy names')
        need(sha(('\n'.join(names) + '\n').encode()) == table['sorted_names_newline_sha256'],
             'actual unsigned policy names digest')
        policy_names[key] = set(names)
    need(set(policy_names) == {'protected_exports', 'permitted_imports'} and
         len(policy_names['protected_exports']) == 626 and len(policy_names['permitted_imports']) == 10447,
         'complete retained unsigned export/import policy')
    complete = read(ci / 'validation-complete.json')
    lock = read(ci / 'artifact-lock.json')
    inventory = read(ci / 'module-inventory.json')
    mca = {}
    for row in inventory['modules']:
        result = review(safe(ci, row['file']))
        name = result['modinfo']['name'][0]
        need(name == row['name'] and result['sha256'] == row['sha256'] and
             result['bytes'] == row['bytes'] and name not in mca, 'actual inventoried ELF: ' + name)
        mca[name] = result
    need(set(mca) == set(inventory['required_module_names']) and len(mca) == 47, 'exact actual47 ELF set')
    contract_path = baseline_dir / 'runtime-contract.json'
    need(pin(contract_path)['sha256'] == CONTRACT_SHA, 'exact healthy R84 runtime contract')
    contract = read(contract_path)
    need(contract['build_id'] == 'R84-THERMAL-FG-QUERY-20261021-01', 'healthy R84 baseline identity')
    expected = dict(contract['module_files'])
    need(len(expected) == 249, 'exact baseline normal249')
    for name in ('myron_bq_readonly', 'myron_mca_readonly'):
        path = '/vendor_dlkm/r32/' + name + '.ko'
        need(path not in expected, 'readonly owner not in normal249')
        expected[path] = contract['runtime_files'][path]
    need(len(expected) == 251, 'exact normal249 plus readonly2 files')
    base = {}
    for path, row in expected.items():
        need(path.startswith(('/vendor_dlkm/', '/system_dlkm/')),
             'baseline module inside vendor_dlkm or system_dlkm')
        result = review(safe(baseline_dir, path.removeprefix('/')))
        name = result['modinfo']['name'][0]
        need(result['sha256'] == row['sha256'] and result['bytes'] == row['bytes'] and name not in base,
             'actual baseline ELF: ' + name)
        base[name] = result
    need(len(base) == 251 and {'qcom_spmi_adc5_gen3', 'qcom_vadc_common'} <= set(base),
         'retain real qualified ADC/VADC thermal providers')
    removed = {'myron_bq_readonly', 'myron_mca_readonly', 'hwid', 'miev'}
    need(removed <= set(base), 'all four static-set deduplication exclusions present')
    retained = {name: result for name, result in base.items() if name not in removed}
    need(len(retained) == 247 and not retained.keys() & mca.keys(), 'exact distinct retained247')
    reused = {name: {'sha256': mca[name]['sha256'], 'bytes': mca[name]['bytes'],
                     'byte_identical': base[name]['sha256'] == mca[name]['sha256'] and
                                       base[name]['bytes'] == mca[name]['bytes']}
              for name in ('hwid', 'miev')}
    need(all(row['byte_identical'] for row in reused.values()), 'hwid/miev may remain loaded unchanged')
    candidate = {**retained, **mca}
    need(len(candidate) == 294 and len({norm(n) for n in candidate}) == 294, 'exact normalized hypothetical294')
    providers = dict(actual)
    issues = []
    for name, result in candidate.items():
        for symbol, export in result['exports'].items():
            if symbol in providers:
                issues.append({'module': name, 'kind': 'duplicate_export', 'symbol': symbol,
                               'other': providers[symbol]['provider']})
                continue
            providers[symbol] = {'provider': name, 'crc': export['crc'], 'namespace': export['namespace'],
                                 'type': 'EXPORT_SYMBOL_GPL' if export['gpl'] else 'EXPORT_SYMBOL',
                                 'signed': result['signature_marker']}
    checks, bindings = {}, {}
    all_names = {norm(n) for n in candidate}
    for name, result in candidate.items():
        bad, links, used = [], [], set()
        info = result['modinfo']
        namespaces = set(info.get('import_ns', []))
        license_names = info.get('license', [])
        if info.get('vermagic') != VERMAGIC:
            bad.append({'kind': 'vermagic'})
        if result['machine'] != 183:
            bad.append({'kind': 'machine'})
        unversioned = sorted(n for n, binding in result['undefined'].items() if binding == 1 and n not in result['imports'])
        if unversioned:
            bad.append({'kind': 'unversioned_strong_imports', 'symbols': unversioned})
        dependencies = {norm(n) for value in info.get('depends', []) for n in value.split(',') if n}
        if dependencies - all_names:
            bad.append({'kind': 'missing_dependencies', 'names': sorted(dependencies - all_names)})
        for symbol, crc in result['imports'].items():
            provider = providers.get(symbol)
            if not provider:
                bad.append({'kind': 'missing_provider', 'symbol': symbol})
                continue
            permitted = (result['signature_marker'] or
                         (provider['provider'] != 'vmlinux' and not provider.get('signed')) or
                         symbol in policy_names['permitted_imports'])
            if crc != provider['crc']:
                bad.append({'kind': 'crc_mismatch', 'symbol': symbol, 'expected': crc, 'actual': provider['crc']})
            if provider['namespace'] and provider['namespace'] not in namespaces:
                bad.append({'kind': 'namespace_missing', 'symbol': symbol, 'namespace': provider['namespace']})
            if provider['type'] == 'EXPORT_SYMBOL_GPL' and (not license_names or any(n not in GPL_LICENSES for n in license_names)):
                bad.append({'kind': 'gpl', 'symbol': symbol})
            if not permitted:
                bad.append({'kind': 'unsigned_import_not_permitted', 'symbol': symbol})
            if provider['provider'] != 'vmlinux':
                used.add(norm(provider['provider']))
            links.append({'symbol': symbol, 'import_crc': crc, **provider, 'permitted': permitted})
        protected = sorted(result['exports'].keys() & policy_names['protected_exports'])
        if protected and not result['signature_marker']:
            bad.append({'kind': 'unsigned_protected_exports', 'symbols': protected})
        if used - dependencies:
            bad.append({'kind': 'provider_not_declared_dependency', 'names': sorted(used - dependencies)})
        checks[name] = {
            'imports': len(result['imports']), 'exports': len(result['exports']),
            'core_imports': sum(r['provider'] == 'vmlinux' for r in links),
            'module_imports': sum(r['provider'] != 'vmlinux' for r in links),
            'providers': sorted(used), 'depends': sorted(dependencies), 'issues': bad,
        }
        bindings[name] = links
        issues.extend({'module': name, **row} for row in bad)
    all_order, all_cycles = topological(checks, set(candidate))
    order, cycles = topological(checks, set(mca))
    external = sorted({p for n in mca for p in checks[n]['providers'] if p not in mca})
    adc_api = {'get_adc_tm_gen3', 'adc_tm5_gen3_channel_measure', 'adc_tm5_gen3_disable_chan_meas', 'adc_tm5_gen3_get_temp'}
    adc_imports = {n: [s for s in r['imports'] if s in adc_api or 'adc_tm' in s] for n, r in mca.items()}
    adc_imports = {n: values for n, values in adc_imports.items() if values}
    retained_adc = {n: [s for s in r['imports'] if 'adc_tm' in s] for n, r in retained.items()}
    retained_adc = {n: values for n, values in retained_adc.items() if values}
    report = {
        'schema': 1, 'status': 'PASS_STATIC_INACTIVE_FULL_MCA_CLOSURE' if not issues and not cycles and not all_cycles else 'BLOCKED',
        'activation_allowed': False, 'hardware_tested': False, 'flashable': False,
        'scope': 'Hypothetical static exact-ELF set: retained247 R84 plus coherent47 R87. Runtime implementation can retain normal249 including byte-identical hwid/miev, omit both readonly owner loads and add45. No baseline files, images or device state are changed by this audit.',
        'limits': ['Static ELF provider/CRC/namespace/GPL/unsigned-policy/dependency checks only.',
                   'No semantic source review, CFI callsite type proof, actual DT probe/binding, owner handover, authentication, thermal/power behavior, fast charging or flash readiness assertion.'],
        'issues': issues, 'dependency_cycle': cycles, 'all294_dependency_cycle': all_cycles,
        'documentation_only_topological_order': order,
        'mca_module_count': len(mca), 'retained_module_count': len(retained), 'hypothetical_module_count': len(candidate),
        'mca_imports': sum(checks[n]['imports'] for n in mca), 'mca_exports': sum(checks[n]['exports'] for n in mca),
        'all_imports': sum(r['imports'] for r in checks.values()),
        'mca_core_imports': sum(checks[n]['core_imports'] for n in mca),
        'mca_module_imports': sum(checks[n]['module_imports'] for n in mca),
        'external_providers': {n: {k: retained[n][k] for k in ('path', 'bytes', 'sha256', 'modinfo')} for n in external},
        'excluded_readonly_owners': ['myron_bq_readonly', 'myron_mca_readonly'],
        'byte_identical_reused_modules': reused, 'provider_set_deduplicates': ['hwid', 'miev'],
        'raw_adc_tm_imports': adc_imports, 'retained_raw_adc_tm_imports': retained_adc,
        'all_MCA_modules_unsigned': all(not r['signature_marker'] for r in mca.values()),
        'retained_vendor_boot': file_record(args.retained_vendor_boot),
        'retained_runtime_contract': file_record(contract_path), 'retained_image': file_record(image_path),
        'retained_symvers': file_record(runtime / 'vmlinux.symvers'),
        'retained_kernel_config': file_record(runtime / 'kernel_aarch64_dot_config'),
        'retained_policy_inputs': [file_record(export_policy_path), file_record(policy_path)],
        'image_export_count': len(actual), 'image_policy': {k: len(v) for k, v in policy_names.items()},
        'artifact_lock_verified_members': len(lock['files']), 'ci': identity['ci'],
        'source_contract_sha256': complete['source_contract_sha256'],
        'build_contract_sha256': complete['build_contract_sha256'],
        'artifact_identity': {'status': identity['status'], 'artifact_lock': identity['artifact_lock'],
                              'source_contract': identity['source_contract'], 'build_contract': identity['build_contract'],
                              'artifact_zips': identity['artifact_zips'], 'identity_reviewer': identity['reviewer']},
        'mca_checks': {n: checks[n] for n in sorted(mca)},
        'reviewer': file_record(Path(__file__)), 'parser': file_record(parser_path),
    }
    documentation = {
        'activation_allowed': False, 'flashable': False, 'hardware_tested': False,
        'module_count': len(all_order), 'dependencies_only_not_probe_order': True,
        'excluded_readonly_owners': ['myron_bq_readonly', 'myron_mca_readonly'],
        'order': all_order, 'dependency_cycle': all_cycles,
        'modules': {n: {'file': candidate[n]['path'], 'bytes': candidate[n]['bytes'],
                        'sha256': candidate[n]['sha256'], 'providers': checks[n]['providers'],
                        'depends': checks[n]['depends']} for n in sorted(candidate)},
    }
    return report, {
        'ARTIFACT-IDENTITY.json': identity,
        'DOCUMENTATION-ONLY-MODULE-ORDER-294.json': documentation,
        'INACTIVE-FULL-MCA-CLOSURE.json': report,
        'BASELINE-ELF-REVIEWS.json': base,
        'FULL-MCA-ELF-REVIEWS.json': mca,
        'FULL-MCA-BINDINGS.json': {n: bindings[n] for n in mca},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_identity_arguments(parser)
    parser.add_argument('--baseline-dir', type=Path, default=WORKSPACE / 'r85-success/abi-audit/baseline-r84')
    parser.add_argument('--reference-dir', type=Path, default=WORKSPACE / 'r85-success/reference-download/reference/myron-r67-ci-review')
    parser.add_argument('--elf-parser', type=Path, default=WORKSPACE / 'recovery-r85/r84-test/review/r84-runtime-abi/elf_review.py')
    parser.add_argument('--retained-vendor-boot', type=Path, default=WORKSPACE / 'r85-success/vendor_boot_r84-reference.img')
    args = parser.parse_args()
    report, outputs = audit_closure(args)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, value in outputs.items():
        (args.out / name).write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('status', 'issues', 'dependency_cycle', 'all294_dependency_cycle',
                                           'mca_module_count', 'retained_module_count', 'hypothetical_module_count',
                                           'mca_imports', 'mca_exports', 'mca_core_imports', 'mca_module_imports')}, indent=2))
    return 0 if report['status'] == 'PASS_STATIC_INACTIVE_FULL_MCA_CLOSURE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
