#!/usr/bin/env python3
"""Assemble source DT images only after explicit input/ID/provider checks pass."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fdt(data):
    require(len(data) >= 40, 'Truncated FDT header')
    h = struct.unpack_from('>10I', data)
    require(h[0] == 0xd00dfeed and 40 <= h[1] <= len(data), 'Invalid FDT header')
    require(h[2] + h[9] <= h[1] and h[3] + h[8] <= h[1], 'Invalid FDT bounds')
    pos, end = h[2], h[2] + h[9]
    strings = data[h[3]:h[3] + h[8]]
    nodes, stack = {}, []
    while pos + 4 <= end:
        token = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        if token == 1:
            stop = data.index(b'\0', pos, end)
            stack.append(data[pos:stop].decode())
            pos = (stop + 4) & ~3
            path = '/'.join(stack) or '/'
            require(path not in nodes, 'Duplicate FDT node')
            nodes[path] = {}
        elif token == 2:
            require(bool(stack), 'Unbalanced FDT')
            stack.pop()
        elif token == 3:
            require(bool(stack) and pos + 8 <= end, 'Invalid FDT property')
            length, offset = struct.unpack_from('>2I', data, pos)
            pos += 8
            require(pos + length <= end and offset < len(strings), 'FDT property out of bounds')
            name = strings[offset:strings.index(b'\0', offset)].decode()
            props = nodes['/'.join(stack) or '/']
            require(name not in props, 'Duplicate FDT property')
            props[name] = data[pos:pos + length]
            pos = (pos + length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            require(not stack and '/' in nodes, 'Incomplete FDT')
            return nodes
        else:
            raise ValueError('Unknown FDT token')
    raise ValueError('Missing FDT end token')


def cells(value):
    require(len(value) % 4 == 0, 'Misaligned FDT cells')
    return list(struct.unpack('>' + str(len(value) // 4) + 'I', value))


def pairs(value):
    values = cells(value)
    require(len(values) % 2 == 0, 'Expected ID pairs')
    return {tuple(values[i:i+2]) for i in range(0, len(values), 2)}


def catalog(full, profile, build_status=None):
    require(build_status is not None, '--full requires --build-status from the matching kernel build')
    require(build_status.is_file() and not build_status.is_symlink(), 'Missing/redirected kernel build status')
    provenance = json.loads(build_status.read_text())
    require(provenance.get('success') is True, 'Kernel build status is not successful')
    entry = json.loads((HERE / 'modules.json').read_text())['entry_commit']
    require(provenance.get('entry_commit') == entry, 'Full kernel entry mismatch')
    sources = provenance.get('sources')
    require(isinstance(sources, list) and all(isinstance(row, dict) for row in sources),
            'Missing/invalid kernel source provenance')
    dts = [row.get('commit') for row in sources if row.get('path') == 'vendor/qcom/sm8850-devicetrees']
    require(dts == [profile['dts_commit']], 'Full kernel DTS revision mismatch')
    status = json.loads((full / 'validation-status.json').read_text())
    require(status.get('verified') is True, 'Unverified compiler output')
    manifest = json.loads((full / 'artifact-manifest.json').read_text())
    for field in ('kernel_release', 'linux_banner'):
        value = provenance.get(field)
        require(isinstance(value, str) and bool(value) and status.get(field) == value and manifest.get(field) == value,
                'Full kernel ' + field + ' mismatch')
    wanted = {x['file'] for x in profile['bases']} | set(profile['board_overlays'])
    wanted |= {n for x in profile['bases'] for n in x['overlays']}
    files = {}
    for row in manifest['files']:
        name = Path(row['file']).name
        if name not in wanted:
            continue
        rel = Path(row['file'])
        require(not rel.is_absolute() and '..' not in rel.parts, 'Unsafe artifact path')
        path = full / rel
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(full.resolve()), 'Missing/redirected DT input')
        require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'DT hash mismatch: ' + name)
        require(name not in files, 'Ambiguous DT input: ' + name)
        files[name] = path
    return files, sorted(wanted - files.keys())


def compiled_catalog(compiled, profile):
    manifest = json.loads((compiled / 'dt-compile.json').read_text())
    require(manifest['kind'] == 'host-dtc-only', 'Unexpected compilation provenance')
    require(manifest['dts_commit'] == profile['dts_commit'], 'DTS revision mismatch')
    require(manifest['entry_commit'] == json.loads((HERE / 'modules.json').read_text())['entry_commit'], 'Kernel entry mismatch')
    files = {}
    for row in manifest['files']:
        name = row['file']
        require(Path(name).name == name and name not in files, 'Invalid DT filename')
        path = compiled / name
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(compiled.resolve()), 'Missing/redirected DT')
        require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'DT hash mismatch')
        files[name] = path
    wanted = {b['file'] for b in profile['bases']} | set(profile['board_overlays'])
    wanted |= {n for b in profile['bases'] for n in b['overlays']}
    return files, sorted(wanted - files.keys())


def reviewed_rules(profile):
    # Deliberately narrower than ABL's general foundry-zero fallback. Adding a
    # device/revision requires another source review, not an arbitrary mask.
    allowed = {((0x1010295, rev), (0x1000295, rev)) for rev in (0x10000, 0x20000)}
    rules = set()
    for rule in profile.get('reviewed_foundry_zero', []):
        pair = (tuple(rule['base_msm_id']), tuple(rule['overlay_msm_id']))
        require(pair in allowed and pair not in rules and rule.get('evidence') == 'DT-ID-MATCHING.md',
                'Unreviewed or duplicate foundry mapping')
        rules.add(pair)
    return rules


def overlay_match(base_id, overlay_ids, rules):
    identity = tuple(base_id)
    if identity in overlay_ids:
        return 'exact', identity
    for source, target in sorted(rules):
        if identity == source and target in overlay_ids:
            return 'reviewed_foundry_zero', target
    return None, None


def preflight(files, profile, missing, matches=None):
    rules = reviewed_rules(profile)
    trees = {n: fdt(p.read_bytes()) for n, p in files.items()}
    errors = [{'kind': 'missing_compiled_input', 'file': n} for n in missing]
    for base in profile['bases']:
        name = base['file']
        if name not in trees:
            continue
        root = trees[name]['/']
        for prop, key in [('qcom,msm-id', 'msm_id'), ('qcom,board-id', 'board_id')]:
            if cells(root.get(prop, b'')) != base[key]:
                errors.append({'kind': 'base_identity_changed', 'base': name, 'property': prop})
        sequence = base['overlays'] + profile['board_overlays']
        available = set(trees[name].get('/__symbols__', {}))
        for overlay in sequence:
            available.update(trees.get(overlay, {}).get('/__symbols__', {}))
        for overlay in sequence:
            if overlay not in trees:
                continue
            tree = trees[overlay]
            absent = sorted(set(tree.get('/__fixups__', {})) - available)
            if absent:
                errors.append({'kind': 'unresolved_symbols', 'base': name, 'overlay': overlay, 'symbols': absent})
            ids = tree['/'].get('qcom,msm-id')
            if ids:
                kind, selected = overlay_match(base['msm_id'], pairs(ids), rules)
                if kind is None:
                    errors.append({'kind': 'soc_id_mapping_requires_review', 'base': name, 'overlay': overlay,
                                   'note': 'No implicit SoC/OEM ID mask or revision substitution is permitted.'})
                elif kind == 'reviewed_foundry_zero' and matches is not None:
                    matches.append({'base': name, 'overlay': overlay, 'kind': kind,
                                    'base_msm_id': base['msm_id'], 'overlay_msm_id': list(selected)})
    return trees, errors


def run(command):
    result = subprocess.run([str(x) for x in command], capture_output=True, text=True)
    require(result.returncode == 0, 'DT command failed: ' + ' '.join(map(str, command)) + '\n' + result.stderr[-3000:])


def root_metadata(path, reference, tool):
    actual = fdt(path.read_bytes())['/']
    identity = ('model', 'compatible', 'qcom,msm-id', 'qcom,board-id', 'qcom,pmic-id', 'qcom,pmic-id-size', 'xiaomi,miboard-id')
    for prop in identity:
        if prop not in reference:
            if prop in actual:
                run([tool, '-d', path, '/', prop])
            continue
        value = reference[prop]
        if prop in ('model', 'compatible'):
            run([tool, '-t', 's', path, '/', prop, *value.rstrip(b'\0').decode().split('\0')])
        else:
            run([tool, '-t', 'x', path, '/', prop, *[hex(n) for n in cells(value)]])
    result = fdt(path.read_bytes())['/']
    for prop in identity:
        require(result.get(prop) == reference.get(prop), 'Metadata restoration failed: ' + prop)


def provider_errors(tree, required):
    present = set()
    for path, node in tree.items():
        if path.startswith('/__'):
            continue
        # A child of a disabled bus is not a usable hardware provider either.
        ancestors = [path] + [path[:i] for i, c in enumerate(path) if c == '/' and i]
        if any(tree.get(p, {}).get('status', b'okay\0') not in (b'ok\0', b'okay\0') for p in ancestors):
            continue
        present.update(node.get('compatible', b'').rstrip(b'\0').decode().split('\0'))
    return sorted(set(required) - present)


def property_errors(nodes, required):
    errors = []
    for path, properties in required.items():
        for name, expected in properties.items():
            value = nodes.get(path, {}).get(name)
            if isinstance(expected, list):
                matches = value is not None and len(value) % 4 == 0 and cells(value) == expected
            elif isinstance(expected, dict) and set(expected) == {'hex'}:
                # Exact byte values also represent boolean properties with hex="".
                matches = value == bytes.fromhex(expected['hex'])
            elif isinstance(expected, dict) and set(expected) == {'phandle_target'}:
                target = expected['phandle_target']
                # Compare the resolved path, never a compiler-assigned phandle number.
                owners = [p for p, node in nodes.items()
                          if value is not None and len(value) == 4 and value != bytes(4)
                          and value in (node.get('phandle'), node.get('linux,phandle'))]
                matches = owners == [target]
            else:
                raise ValueError('Unknown required-property rule: ' + path + ':' + name)
            if not matches:
                errors.append(path + ':' + name)
    return errors


def verify_table(data, overlay, table):
    require(len(data) >= 64, 'Truncated DTBO image')
    h = struct.unpack_from('>8I', data)
    require(h[0] == 0xd7b7ab1e and h[2:] == (32, 32, 1, 32, table['page_size'], table['version']), 'DTBO table header mismatch')
    require(64 <= h[1] <= len(data) and not any(data[h[1]:]), 'Invalid raw DTBO size/padding')
    e = struct.unpack_from('>8I', data, 32)
    require(e[2:] == (table['id'], table['rev'], *table['custom']), 'DTBO selection metadata mismatch')
    require(e[0] == len(overlay) and e[1] >= 64 and data[e[1]:e[1]+e[0]] == overlay, 'DTBO payload mismatch')
    require(e[1] + e[0] == h[1], 'DTBO table total size does not match payload')


FASTRPC_ORDER_RULES = [
    {'parent': '/soc/remoteproc-adsp@03000000/glink-edge/qcom,fastrpc',
     'overlay_target_symbol': 'remoteproc_adsp_glink',
     'children': ['compute-cb@%d' % i for i in range(1, 7)]},
    {'parent': '/soc/remoteproc-cdsp@32300000/glink-edge/qcom,fastrpc',
     'overlay_target_symbol': 'remoteproc_cdsp_glink',
     'children': ['compute-cb@%d' % i for i in range(1, 12)]},
]
FASTRPC_SOURCE_OVERLAYS = ('canoe-dsp.dtbo', 'canoe-dsp_v2.dtbo')


def fdt_layout(data):
    """Read structure-token spans and ordered direct children without rewriting."""
    nodes = fdt(data)  # Validate the complete property graph first.
    h = struct.unpack_from('>10I', data)
    pos, end = h[2], h[2] + h[9]
    stack, children, spans = [], {}, {}
    while pos + 4 <= end:
        start = pos
        token, = struct.unpack_from('>I', data, pos)
        pos += 4
        if token == 1:
            stop = data.index(b'\0', pos, end)
            name = data[pos:stop].decode()
            path = (stack[-1][0].rstrip('/') + '/' + name) if stack else '/'
            require(path in nodes and path not in children, 'Invalid layout node')
            if stack:
                children[stack[-1][0]].append(path)
            children[path] = []
            stack.append((path, start))
            pos = (stop + 4) & ~3
        elif token == 2:
            require(bool(stack), 'Unbalanced layout node')
            path, begin = stack.pop()
            spans[path] = (begin, pos)
        elif token == 3:
            require(stack and pos + 8 <= end, 'Invalid layout property')
            length, _ = struct.unpack_from('>2I', data, pos)
            pos = (pos + 8 + length + 3) & ~3
            require(pos <= end, 'Invalid layout property size')
        elif token == 4:
            continue
        elif token == 9:
            require(not stack and set(children) == set(nodes), 'Incomplete layout')
            return nodes, children, spans
        else:
            raise ValueError('Unknown layout token')
    raise ValueError('Missing layout end token')


def reviewed_fastrpc_order(profile, spec, files):
    """Only the two reviewed Myron FastRPC domains and exact pinned sources."""
    require(profile.get('device') == 'Redmi K90PM / myron' and spec in profile['bases'],
            'FastRPC order policy is not approved for this source/device')
    require(profile.get('reviewed_fastrpc_child_order') == FASTRPC_ORDER_RULES,
            'Missing or unreviewed FastRPC child-order policy')
    names = [name for name in spec['overlays'] if name in FASTRPC_SOURCE_OVERLAYS]
    require(len(names) == 1, 'Expected exactly one reviewed DSP overlay')
    name = names[0]
    blob = files[name].read_bytes()
    # files has already passed catalog/compiled_catalog against the matching
    # source manifest. Record that build's digest, do not freeze a build hash.
    source_digest = hashlib.sha256(blob).hexdigest()
    nodes, children, _ = fdt_layout(blob)
    proofs = []
    for rule in FASTRPC_ORDER_RULES:
        fixup = nodes.get('/__fixups__', {}).get(rule['overlay_target_symbol'])
        require(fixup is not None, 'DSP overlay target symbol is missing')
        locations = fixup.rstrip(b'\0').decode().split('\0')
        require(len(locations) == 1, 'Ambiguous DSP overlay target symbol')
        parts = locations[0].split(':')
        require(len(parts) == 3 and parts[1:] == ['target', '0'], 'Unexpected DSP overlay target fixup')
        fragment = parts[0]
        require(nodes.get(fragment, {}).get('target') == b'\xff\xff\xff\xff',
                'DSP overlay is not an unresolved target-symbol overlay')
        parent = fragment + '/__overlay__/qcom,fastrpc'
        require(nodes.get(parent, {}).get('compatible') == b'qcom,fastrpc\0',
                'DSP source parent is not FastRPC')
        order = [p.rsplit('/', 1)[1] for p in children.get(parent, [])]
        require(order == rule['children'], 'Pinned DSP source child order changed')
        proofs.append({'source_parent': parent, 'target_symbol': rule['overlay_target_symbol'],
                       'runtime_parent': rule['parent'], 'source_children': order})
    return {'overlay': name, 'sha256': source_digest, 'parents': proofs}


def fastrpc_order_errors(data, profile):
    require(profile.get('reviewed_fastrpc_child_order') == FASTRPC_ORDER_RULES,
            'Missing or unreviewed FastRPC child-order policy')
    _, children, _ = fdt_layout(data)
    return [r['parent'] for r in FASTRPC_ORDER_RULES
            if [p.rsplit('/', 1)[1] for p in children.get(r['parent'], [])] != r['children']]


def restore_fastrpc_order(data, profile, spec, files):
    """Restore only two reviewed sibling lists with byte-preserving subtree moves.

    libfdt inserts newly added siblings at the start of their parent. This host
    assembly stage restores the compiled DSP source order before board overlays
    are applied. It never changes DTS declaration order or any property value.
    """
    source_proof = reviewed_fastrpc_order(profile, spec, files)
    before_nodes, before_children, spans = fdt_layout(data)
    replacements, changes = [], []
    for rule in FASTRPC_ORDER_RULES:
        parent = rule['parent']
        require(before_nodes.get(parent, {}).get('compatible') == b'qcom,fastrpc\0',
                'Reviewed runtime FastRPC parent is absent')
        old_paths = before_children.get(parent, [])
        names = [p.rsplit('/', 1)[1] for p in old_paths]
        expected = rule['children']
        require(names in (expected, list(reversed(expected))),
                'FastRPC child set/order is outside the reviewed source/merge forms')
        require(all(before_nodes[p].get('compatible') == b'qcom,fastrpc-compute-cb\0'
                    for p in old_paths), 'Unexpected child type in FastRPC order span')
        for a, b in zip(old_paths, old_paths[1:]):
            require(spans[a][1] == spans[b][0], 'Noncontiguous FastRPC children; no token may be dropped')
        start, stop = spans[old_paths[0]][0], spans[old_paths[-1]][1]
        ordered_paths = [parent + '/' + name for name in expected]
        replacement = b''.join(data[spans[p][0]:spans[p][1]] for p in ordered_paths)
        require(len(replacement) == stop - start, 'FastRPC subtree length changed')
        replacements.append((start, stop, replacement))
        changes.append({'parent': parent, 'before': names, 'after': expected,
                        'structure_span': [start, stop], 'changed': names != expected})
    ranges = sorted(replacements)
    require(all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:])), 'Overlapping reviewed spans')
    result = bytearray(data)
    for start, stop, replacement in replacements:
        result[start:stop] = replacement
    result = bytes(result)
    require(len(result) == len(data), 'FDT length changed')
    after_nodes, after_children, _ = fdt_layout(result)
    require(after_nodes == before_nodes, 'FDT node/property bytes changed during reorder')
    changed_parents = {p for p in before_children if before_children[p] != after_children[p]}
    expected_changes = {row['parent'] for row in changes if row['changed']}
    require(changed_parents == expected_changes, 'Unreviewed sibling order changed')
    cursor = 0
    for start, stop, _ in ranges:
        require(result[cursor:start] == data[cursor:start], 'Bytes outside order spans changed')
        cursor = stop
    require(result[cursor:] == data[cursor:], 'Trailing FDT bytes changed')
    require(not fastrpc_order_errors(result, profile), 'FastRPC final order check failed')
    return result, {'source_proof': source_proof, 'changes': changes,
                    'all_properties_byte_identical': True, 'all_other_bytes_identical': True,
                    'before_sha256': hashlib.sha256(data).hexdigest(),
                    'after_sha256': hashlib.sha256(result).hexdigest()}


def assemble(files, trees, profile, output, tools):
    work = output / 'work'
    work.mkdir(parents=True, exist_ok=True)
    board = work / 'myron-board.dtbo'
    overlays = profile['board_overlays']
    run([tools.fdtoverlaymerge, '-i', files[overlays[0]], '-o', board, *[files[n] for n in overlays[1:]]])
    root_metadata(board, trees[profile['board_metadata_from']]['/'], tools.fdtput)
    bases, order_proofs = [], []
    use_order_policy = (profile.get('device') == 'Redmi K90PM / myron' or
                        'reviewed_fastrpc_child_order' in profile)
    for i, spec in enumerate(profile['bases']):
        base = work / ('base-%02d.dtb' % i)
        run([tools.fdtoverlay, '-i', files[spec['file']], '-o', base, *[files[n] for n in spec['overlays']]])
        root_metadata(base, trees[spec['file']]['/'], tools.fdtput)
        if use_order_policy:
            shutil.copyfile(base, work / ('preorder-base-%02d.dtb' % i))
            revised, order_proof = restore_fastrpc_order(base.read_bytes(), profile, spec, files)
            base.write_bytes(revised)
            order_proofs.append(dict(order_proof, index=i, base=spec['file']))
        merged = work / ('merged-%02d.dtb' % i)
        run([tools.fdtoverlay, '-i', base, '-o', merged, board])
        nodes = fdt(merged.read_bytes())
        require(not use_order_policy or not fastrpc_order_errors(merged.read_bytes(), profile),
                'Board overlay changed reviewed FastRPC child order')
        absent = provider_errors(nodes, profile['required_compatible'] + spec.get('required_compatible', []))
        require(not absent, 'Missing/disabled hardware providers on ' + spec['file'] + ': ' + ', '.join(absent))
        invalid = property_errors(nodes, profile.get('required_properties', {}))
        require(not invalid, 'Missing/incorrect hardware properties on ' + spec['file'] + ': ' + ', '.join(invalid))
        bases.append(base.read_bytes())
    table = profile['dtbo_table']
    raw_dtbo = work / 'dtbo.img'
    run([tools.mkdtboimg, 'create', raw_dtbo, '--page_size=' + str(table['page_size']),
         '--version=' + str(table['version']), '--id=' + str(table['id']), '--rev=' + str(table['rev']),
         *['--custom%d=%d' % (i, x) for i, x in enumerate(table['custom'])], board])
    verify_table(raw_dtbo.read_bytes(), board.read_bytes(), table)
    # Final ROM inputs are written only after all eight variants passed.
    (output / 'dtb.img').write_bytes(b''.join(bases))
    shutil.copyfile(raw_dtbo, output / 'dtbo.img')
    (output / 'fastrpc-order-proof.json').write_text(json.dumps(order_proofs, indent=2, sort_keys=True) + '\n')
    return {'dtb.img': sha(output / 'dtb.img'), 'dtbo.img': sha(output / 'dtbo.img')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    inputs = p.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--full', type=Path)
    inputs.add_argument('--compiled', type=Path, help='Hash-checked DT-only output; does not attest a full kernel build')
    p.add_argument('--build-status', type=Path, help='Matching integration-reports/build-status.json; required with --full')
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--profile', type=Path, default=HERE / 'dt-profile.json')
    p.add_argument('--fdtoverlay', default='fdtoverlay')
    p.add_argument('--fdtoverlaymerge', default='fdtoverlaymerge')
    p.add_argument('--fdtput', default='fdtput')
    p.add_argument('--mkdtboimg', default='mkdtboimg')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    require(not a.output.is_symlink(), 'Redirected output directory')
    # Never leave a prior success usable after a failed recheck.
    for name in ('dtb.img', 'dtbo.img', 'fastrpc-order-proof.json'):
        path = a.output / name
        require(not path.is_symlink(), 'Redirected image output')
        path.unlink(missing_ok=True)
    report = {'success': False, 'device_tested': False, 'full_rom_compiled': False,
              'input_kind': 'host-dtc-only' if a.compiled else 'full-kernel-output',
              'flash_package': False, 'errors': [], 'reviewed_matches': []}
    try:
        profile = json.loads(a.profile.read_text())
        require(not (a.compiled and a.build_status), '--build-status is only valid with --full')
        files, missing = compiled_catalog(a.compiled, profile) if a.compiled else catalog(a.full, profile, a.build_status)
        trees, errors = preflight(files, profile, missing, report['reviewed_matches'])
        if a.compiled:
            report['compile_manifest_sha256'] = sha(a.compiled / 'dt-compile.json')
        else:
            report['build_status_sha256'] = sha(a.build_status)
        report.update(profile_sha256=sha(a.profile), inputs={n: sha(v) for n, v in files.items()}, errors=errors,
                      base_count=len(profile['bases']), source_dts_commit=profile['dts_commit'])
        require(not errors, 'DT preflight blocked: see source-dt-report.json')
        report['images'] = assemble(files, trees, profile, a.output, a)
        report['variants'] = [{'base': b['file'], 'status': 'structural_checks_passed',
                               'merged_sha256': sha(a.output / 'work' / ('merged-%02d.dtb' % i))}
                              for i, b in enumerate(profile['bases'])]
        report['success'] = True
    except (ValueError, OSError, KeyError, struct.error) as error:
        report['failure'] = str(error)
    (a.output / 'source-dt-report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'inputs'}, indent=2))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
