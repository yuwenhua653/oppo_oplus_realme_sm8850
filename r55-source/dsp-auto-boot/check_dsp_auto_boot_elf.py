#!/usr/bin/env python3
"""R55 exact-source and compiled PAS descriptor gate.

Supersedes the R18 ADSP/CDSP-false scope guard using stock OEM ELF evidence.
Validates all four Canoe descriptors against the exact R18 baseline, allowing
only the two reviewed auto_boot bytes. No binaries or input files are changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / 'source-lock.json').read_text())

def compact(text):
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
    return re.sub(r"\s+", "", text)


def require(condition, message):
    if not condition:
        raise ValueError(message)


class ELF:
    def __init__(self, data, expected_machine=183):
        self.data = data
        require(data[:6] == b"\x7fELF\x02\x01", "Expected ELF64 little-endian")
        require(struct.unpack_from("<HH", data, 16) == (1, expected_machine),
                f"Expected ET_REL object/module for ELF machine {expected_machine}")
        off = struct.unpack_from("<Q", data, 40)[0]
        entry_size, count, _ = struct.unpack_from("<HHH", data, 58)
        require(entry_size == 64 and count > 0 and off + count * entry_size <= len(data), "Invalid section table")
        self.sections = [struct.unpack_from("<IIQQQQIIQQ", data, off + i * entry_size) for i in range(count)]
        self.symbols = []
        for i, h in enumerate(self.sections):
            if h[1] != 2:
                continue
            require(h[9] == 24, "Unexpected symbol entry size")
            strings = self.section(h[6])
            raw = self.section(i)
            require(len(raw) % 24 == 0, "Truncated symbol table")
            for j in range(0, len(raw), 24):
                name, info, other, sec, value, size = struct.unpack_from("<IBBHQQ", raw, j)
                require(name < len(strings), "Invalid symbol name offset")
                end = strings.find(b"\0", name)
                require(end >= 0, "Unterminated symbol name")
                self.symbols.append({"name": strings[name:end].decode(), "type": info & 15,
                                     "section": sec, "value": value, "size": size})

    def section(self, index):
        require(0 <= index < len(self.sections), "Invalid section index")
        h = self.sections[index]
        require(h[1] != 8, "No file data in NOBITS section")
        require(h[4] + h[5] <= len(self.data), "Truncated section")
        return self.data[h[4]:h[4] + h[5]]

    def symbol(self, name, symbol_type):
        candidates = [s for s in self.symbols if s["name"] == name and s["section"] != 0]
        require(len(candidates) == 1, f"Expected one defined {name}")
        s = candidates[0]
        require(s["type"] == symbol_type, f"Unexpected ELF symbol type for {name}")
        sec = self.section(s["section"])
        require(s["value"] + s["size"] <= len(sec), f"Out-of-range symbol {name}")
        return s, sec[s["value"]:s["value"] + s["size"]]


def probe_evidence(elf):
    symbol, code = elf.symbol("adsp_probe", 2)
    require(len(code) % 4 == 0, "adsp_probe size is not instruction-aligned")
    matches = []
    for offset in range(0, len(code) - 4, 4):
        load, store = struct.unpack_from("<II", code, offset)
        # A64 unsigned-immediate byte load/store. Register allocation and
        # function-relative location may vary; semantics/field offsets may not.
        if ((load & 0xffc00000) == 0x39400000 and (store & 0xffc00000) == 0x39000000
                and ((load >> 10) & 4095) == 54 and ((store >> 10) & 4095) == 1249
                and (load & 31) == (store & 31) and (load & 31) != 31):
            matches.append({"function_offset": offset, "load_word_hex": f"{load:08x}",
                            "store_word_hex": f"{store:08x}", "value_register": load & 31,
                            "descriptor_base_register": (load >> 5) & 31,
                            "rproc_base_register": (store >> 5) & 31,
                            "descriptor_offset": 54, "rproc_offset": 1249})
    require(len(matches) == 1, "Expected one adjacent desc+54 LDRB -> rproc+1249 STRB in adsp_probe; review changed compiler layout if absent")
    return {"symbol": symbol, "matches": matches,
            "note": "Semantic instruction scan; function offsets and registers are not hardcoded. A changed instruction sequence requires review, not a bypass."}


def relocations(elf):
    """Index ET_REL relocations by relocated section and offset."""
    symtabs = [i for i, h in enumerate(elf.sections) if h[1] == 2]
    require(len(symtabs) == 1, 'Expected exactly one ELF symbol table')
    result = {}
    for i, h in enumerate(elf.sections):
        if h[1] not in (4, 9):
            continue
        require(h[1] == 4, 'Unsupported implicit-addend relocation table')
        require(h[6] == symtabs[0] and h[9] == 24,
                'Unexpected relocation symbol table or entry size')
        raw = elf.section(i)
        require(len(raw) % 24 == 0, 'Truncated relocation table')
        for off in range(0, len(raw), 24):
            location, info, addend = struct.unpack_from('<QQq', raw, off)
            index, kind = info >> 32, info & 0xffffffff
            require(index < len(elf.symbols), 'Invalid relocation symbol index')
            key = (h[7], location)
            require(key not in result, 'Duplicate relocation location')
            result[key] = {'type': kind, 'symbol': elf.symbols[index], 'addend': addend}
    return result


def pointer_target(elf, relocation):
    require(relocation['type'] == 257, 'Expected R_AARCH64_ABS64 data pointer relocation')
    symbol = relocation['symbol']
    require(0 < symbol['section'] < len(elf.sections), 'Pointer target must be defined in this ELF')
    offset = symbol['value'] + relocation['addend']
    require(0 <= offset < len(elf.section(symbol['section'])), 'Pointer target outside section')
    return symbol['section'], offset


def normalized_binding_contract(elf):
    """Resolve strings and OF links without pinning compiler section offsets."""
    rels = relocations(elf)
    descriptors = {}
    targets = {}
    string_fields = {8: 'firmware_name', 16: 'dtb_firmware_name',
                     64: 'load_state', 72: 'ssr_name', 80: 'sysmon_name'}
    pointer_fields = {8, 16, 24, 56, 64, 72, 80}
    for name in LOCK['baseline_module']['descriptors']:
        symbol, raw = elf.symbol(name, 1)
        require(len(raw) == 120, name + ': unexpected descriptor size')
        targets[(symbol['section'], symbol['value'])] = name
        normalized = {}
        for (section, offset), relocation in rels.items():
            if section != symbol['section'] or not symbol['value'] <= offset < symbol['value'] + len(raw):
                continue
            relative = offset - symbol['value']
            require(relative in pointer_fields, name + ': relocation outside known pointer fields')
            require(relative in string_fields, name + ': unexpected non-string pointer target')
            target_section, target_offset = pointer_target(elf, relocation)
            section_bytes = elf.section(target_section)
            end = section_bytes.find(b'\0', target_offset)
            require(end >= 0, name + ': unterminated pointer string')
            value = section_bytes[target_offset:end].decode('ascii')
            require(value and all(32 <= ord(c) < 127 for c in value), name + ': invalid pointer string')
            normalized[string_fields[relative]] = {'offset': relative, 'relocation': 'R_AARCH64_ABS64', 'string': value}
        # The remaining known pointer fields must stay genuinely NULL.
        for offset in pointer_fields:
            if (symbol['section'], symbol['value'] + offset) not in rels:
                require(raw[offset:offset + 8] == b'\0' * 8, name + ': unrelocated non-NULL pointer')
        descriptors[name] = normalized
    table_symbol, table = elf.symbol('__mod_of__adsp_of_match_device_table', 1)
    require(len(table) % 200 == 0, 'Unexpected struct of_device_id table size')
    mappings = {}
    for off in range(0, len(table), 200):
        compatible = table[off + 64:off + 192].split(b'\0', 1)[0].decode('ascii')
        if not compatible.startswith('qcom,canoe-'):
            continue
        require(not any(table[off:off + 64]), 'Unexpected Canoe OF name/type restriction')
        require(compatible not in mappings, 'Duplicate Canoe compatible in OF table')
        key = (table_symbol['section'], table_symbol['value'] + off + 192)
        require(key in rels, 'Canoe OF entry is missing its data relocation')
        target = pointer_target(elf, rels[key])
        require(target in targets, 'Canoe OF entry targets a different descriptor')
        mappings[compatible] = targets[target]
    require(set(mappings.values()) == set(descriptors) and len(mappings) == 4,
            'Expected exactly four distinct Canoe OF descriptor mappings')
    return {'descriptor_pointer_targets': descriptors, 'canoe_of_mappings': mappings}


def inspect(module, source, baseline_module=None):
    source_bytes = source.read_bytes()
    source_info = {'bytes': len(source_bytes), 'sha256': hashlib.sha256(source_bytes).hexdigest()}
    require(source_info == LOCK['r55_output'], 'Compiled source must match exact locked R55 source bytes')
    data = module.read_bytes()
    elf = ELF(data)
    binding_contract = normalized_binding_contract(elf)
    require(binding_contract == LOCK['baseline_module']['normalized_binding_contract'],
            'Descriptor pointer relocations or Canoe OF mappings differ from exact R18 baseline')
    resources = {}
    baseline = None
    if baseline_module:
        baseline_bytes = baseline_module.read_bytes()
        require(hashlib.sha256(baseline_bytes).hexdigest() == LOCK['baseline_module']['sha256'],
                'Unexpected R18 reference module hash')
        baseline = ELF(baseline_bytes)
        require(normalized_binding_contract(baseline) == binding_contract,
                'R18 reference pointer/OF bindings differ from candidate')
    for name, reference in LOCK['baseline_module']['descriptors'].items():
        symbol, raw = elf.symbol(name, 1)
        require(len(raw) == 120, name + ': unexpected descriptor size')
        old = bytes.fromhex(reference['raw_hex'])
        if baseline:
            _, reference_raw = baseline.symbol(name, 1)
            require(reference_raw == old, name + ': reference descriptor differs from lock')
        expected = bytearray(old)
        if name in ('canoe_adsp_resource', 'canoe_cdsp_resource'):
            expected[54] = 1
        require(raw == bytes(expected), name + ': compiled descriptor differs beyond reviewed auto_boot delta')
        resources[name] = {'symbol': symbol, 'auto_boot': raw[54], 'early_boot': raw[118],
                           'raw_sha256': hashlib.sha256(raw).hexdigest(),
                           'changed_offsets_from_r18': [i for i, (a, b) in enumerate(zip(old, raw)) if a != b]}
    probe = probe_evidence(elf)
    return {'path': str(module), 'sha256': hashlib.sha256(data).hexdigest(),
            'source': {'path': str(source), **source_info},
            'resources': resources, 'probe': probe,
            'normalized_binding_contract': binding_contract,
            'descriptor_pointer_relocations_and_canoe_of_mappings_match_r18': True,
            'baseline_descriptor_match_except_two_auto_boot_bytes': True,
            'supersedes_r18_false_guard_based_on_oem': LOCK['oem_evidence']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--baseline-module', type=Path)
    parser.add_argument('--report', '--output', type=Path)
    args = parser.parse_args()
    report = {'schema': 1, 'passed': False, 'hardware_tested': False,
              'scope': 'Exact source bytes, four Canoe descriptor bytes and pointer relocation targets, Canoe OF mappings and semantic auto_boot assignment; ABI/runtime separately required'}
    try:
        report['module'] = inspect(args.module, args.source, args.baseline_module)
        report['passed'] = True
    except (OSError, ValueError, struct.error, UnicodeError) as exc:
        report['error'] = str(exc)
    encoded = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded)
    print(encoded, end='')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
