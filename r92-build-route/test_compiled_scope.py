#!/usr/bin/env python3
"""Synthetic ELF fixtures exercise the real collector then the R92 wiring gate."""
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import types
from contract import MODULE, parents, pin, require
from build_pd_provider import load_elf_parser, verify_compiled_scope, write


def elf_fixture(name, release, imports=(), exports=(), dependencies=()):
    # These are deterministic host test fixtures, never compiler evidence.
    strings = bytearray(b'\0')
    def string(text):
        offset = len(strings)
        strings.extend(text.encode() + b'\0')
        return offset
    symbols = bytearray(bytes(24))
    for symbol in imports:
        symbols.extend(struct.pack('<IBBHQQ', string(symbol), 0x10, 0, 0, 0, 0))
    for symbol in exports:
        symbols.extend(struct.pack('<IBBHQQ', string('__ksymtab_' + symbol), 0x11, 0, 4, 0, 0))
        symbols.extend(struct.pack('<IBBHQQ', string('__crc_' + symbol), 0x11, 0, 0xfff1, 0x12345678, 0))
    versions = b''.join(struct.pack('<Q', 0x12345678) + s.encode().ljust(56, b'\0')
                        for s in ['module_layout', *imports])
    info = f'name={name}\0vermagic={release} SMP modversions aarch64\0depends={",".join(dependencies)}\0'.encode()
    definitions = [('', 0, b'', 0, 0), ('.shstrtab', 3, b'', 0, 0),
                   ('.strtab', 3, bytes(strings), 0, 0), ('.symtab', 2, bytes(symbols), 2, 24),
                   ('.modinfo', 1, info, 0, 0), ('__versions', 1, versions, 0, 0)]
    names = b'\0' + b''.join(d[0].encode() + b'\0' for d in definitions[1:])
    definitions[1] = ('.shstrtab', 3, names, 0, 0)
    result = bytearray(bytes(64))
    headers = []
    for section, kind, data, link, entry in definitions:
        offset = len(result)
        result.extend(data)
        headers.append(struct.pack('<IIQQQQIIQQ', names.index(section.encode() + b'\0'),
            kind, 0, 0, offset, len(data), link, 0, 1, entry))
    section_offset = len(result)
    result.extend(b''.join(headers))
    result[:16] = b'\x7fELF\x02\x01\x01' + bytes(9)
    struct.pack_into('<HHIQQQIHHHHHH', result, 16, 1, 183, 1, 0, 0,
                     section_offset, 0, 64, 0, 0, 64, len(headers), 1)
    return bytes(result)


def main():
    repo = Path(__file__).resolve().parent.parent
    parent, _ = parents(repo)
    names = [r['module_name'] for r in parent['validation_only_modules']] + [MODULE['module_name']]
    dependencies = {
        'mca_protocol_pd_class': ['protocol_class_pd_register_ops', 'protocol_class_pd_unregister_ops'],
        'mca_adsp_glink': ['mca_adsp_glink_read_prop', 'mca_adsp_glink_write_prop'],
        'mca_event': ['mca_event_block_notify_register', 'mca_event_block_notify_unregister'],
        'mca_log': ['mca_log_printk']}
    imports = [s for symbols in dependencies.values() for s in symbols]
    saved_module = sys.modules.pop('elf_contract', None)
    saved_path = list(sys.path)
    try:
        with tempfile.TemporaryDirectory(prefix='r92-elf-guards-') as temporary:
            root = Path(temporary)
            fixture = root / 'fixture'
            route = fixture / 'r92-build-route/reference'
            route.mkdir(parents=True)
            parser = repo / 'r92-build-route/reference/r18_elf_parser.py'
            shutil.copy2(parser, route / parser.name)
            r18 = root / 'r18/stage-builder'
            r18.mkdir(parents=True)
            shutil.copy2(parser, r18 / 'elf_contract.py')
            sys.path.insert(0, str(repo / 'r61-build-route'))
            spec = importlib.util.spec_from_file_location('r92_real_r61_collector', repo / 'r61-build-route/targeted_battery_build.py')
            collector = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(collector)
            release = 'R92_SYNTHETIC_HOST_FIXTURE'
            rows, pins, candidates = [], {}, []
            for name in names:
                is_provider = name == MODULE['module_name']
                data = elf_fixture(name, release, imports if is_provider else (),
                                   dependencies.get(name, []), dependencies if is_provider else ())
                namepath = f'bazel-out/aarch64-fastbuild/bin/fixture/{name}.ko'
                path = root / namepath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                symvers = namepath + '.symvers'
                (root / symvers).write_bytes(b'host fixture\n')
                rows.append({'module_name': name, 'output': namepath, 'symvers': symvers})
                candidates += [namepath, symvers]
                if not is_provider:
                    pins[name] = pin(data)
            for name in collector.CORE_REQUIRED:
                path = root / collector.CORE / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((release + '\n').encode() if name == 'include/config/kernel.release' else b'synthetic fixture')
                candidates.append(collector.CORE + name)
            write(route / 'r90-module-pins.json', {'modules': pins, 'github_run_id': 'SYNTHETIC_TEST_ONLY'})
            output = root / 'collected'
            collector.collect_outputs(root, output, {'baseline_image_sha256': 'host-fixture',
                'baseline_kernel_release': release}, rows, candidates, r18.parent)
            require('elf_contract' in sys.modules, 'Real collector did not exercise its parser import')
            # Poison the generic name after real collection: R92 must still use
            # its exact private parser, not another module cached by the engine.
            poisoned = types.ModuleType('elf_contract')
            poisoned.parse_elf = lambda data: (_ for _ in ()).throw(AssertionError('wrong cached parser'))
            sys.modules['elf_contract'] = poisoned
            record = verify_compiled_scope(output, fixture)
            require(len(record['MCA_import_bindings']) == 7, 'Real ELF CRC bindings were not exercised')
            checks = ['real_collect_outputs_then_R92_wiring_gate_same_process',
                      'generic_elf_contract_cache_cannot_override_private_parser']
            inventory_path = output / 'module-inventory.json'
            exact = inventory_path.read_bytes()
            inventory = json.loads(exact)
            provider = next(r for r in inventory['modules'] if r['name'] == MODULE['module_name'])
            provider_path = output / provider['file']
            provider_bytes = provider_path.read_bytes()
            def reject(label, data=None, inventory_change=None):
                changed = json.loads(exact)
                if data is not None:
                    provider_path.write_bytes(data)
                    next(r for r in changed['modules'] if r['name'] == MODULE['module_name']).update(pin(data))
                if inventory_change:
                    inventory_change(changed)
                write(inventory_path, changed)
                try:
                    verify_compiled_scope(output, fixture)
                except (ValueError, KeyError):
                    checks.append(label)
                else:
                    raise AssertionError('Invalid synthetic input passed: ' + label)
                finally:
                    provider_path.write_bytes(provider_bytes)
                    inventory_path.write_bytes(exact)
            reject('missing_registration_import_rejected', elf_fixture(MODULE['module_name'], release,
                imports[1:], (), dependencies))
            reject('wrong_provider_dependencies_rejected', elf_fixture(MODULE['module_name'], release,
                imports, (), ['mca_adsp_glink']))
            reject('provider_CRC_mismatch_rejected', provider_bytes.replace(
                struct.pack('<Q', 0x12345678), struct.pack('<Q', 0x12345679)))
            reject('incomplete_48_collection_rejected', inventory_change=lambda v: v.update(module_count=47))
            reject('missing_provider_row_rejected', inventory_change=lambda v: v.update(
                modules=[r for r in v['modules'] if r['name'] != MODULE['module_name']]))
            reject('extra_module_identity_rejected', inventory_change=lambda v: v['modules'].append(
                dict(v['modules'][0], name='unreviewed_module')))
            reject('duplicate_module_identity_rejected', inventory_change=lambda v: v['modules'].append(v['modules'][0]))
            old = output / inventory['modules'][0]['file']
            old.write_bytes(old.read_bytes() + b'changed')
            reject('changed_original_R90_binary_rejected')
            print(json.dumps({'schema': 1, 'status': 'PASS_R92_SYNTHETIC_ELF_GUARDS',
                'count': len(checks), 'checks': checks, 'fixtures_are_compiler_evidence': False,
                'hardware_tested': False}))
    finally:
        sys.path[:] = saved_path
        if saved_module is None:
            sys.modules.pop('elf_contract', None)
        else:
            sys.modules['elf_contract'] = saved_module


if __name__ == '__main__':
    main()
