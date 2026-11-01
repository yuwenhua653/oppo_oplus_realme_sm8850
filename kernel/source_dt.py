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


def catalog(full, profile):
    status = json.loads((full / 'validation-status.json').read_text())
    require(status.get('verified') is True, 'Unverified compiler output')
    manifest = json.loads((full / 'artifact-manifest.json').read_text())
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


def preflight(files, profile, missing):
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
            if ids and tuple(base['msm_id']) not in pairs(ids):
                errors.append({'kind': 'soc_id_mapping_requires_review', 'base': name, 'overlay': overlay,
                               'note': 'No implicit SoC/SKU mask or revision substitution is permitted.'})
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
            if value is None or cells(value) != expected:
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


def assemble(files, trees, profile, output, tools):
    work = output / 'work'
    work.mkdir(parents=True, exist_ok=True)
    board = work / 'myron-board.dtbo'
    overlays = profile['board_overlays']
    run([tools.fdtoverlaymerge, '-i', files[overlays[0]], '-o', board, *[files[n] for n in overlays[1:]]])
    root_metadata(board, trees[profile['board_metadata_from']]['/'], tools.fdtput)
    bases = []
    for i, spec in enumerate(profile['bases']):
        base = work / ('base-%02d.dtb' % i)
        run([tools.fdtoverlay, '-i', files[spec['file']], '-o', base, *[files[n] for n in spec['overlays']]])
        root_metadata(base, trees[spec['file']]['/'], tools.fdtput)
        merged = work / ('merged-%02d.dtb' % i)
        run([tools.fdtoverlay, '-i', base, '-o', merged, board])
        nodes = fdt(merged.read_bytes())
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
    return {'dtb.img': sha(output / 'dtb.img'), 'dtbo.img': sha(output / 'dtbo.img')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--full', required=True, type=Path)
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
    for name in ('dtb.img', 'dtbo.img'):
        path = a.output / name
        require(not path.is_symlink(), 'Redirected image output')
        path.unlink(missing_ok=True)
    report = {'success': False, 'device_tested': False, 'full_rom_compiled': False, 'errors': []}
    try:
        profile = json.loads(a.profile.read_text())
        files, missing = catalog(a.full, profile)
        trees, errors = preflight(files, profile, missing)
        report.update(profile_sha256=sha(a.profile), inputs={n: sha(v) for n, v in files.items()}, errors=errors,
                      base_count=len(profile['bases']), source_dts_commit=profile['dts_commit'])
        require(not errors, 'DT preflight blocked: see source-dt-report.json')
        report['images'] = assemble(files, trees, profile, a.output, a)
        report['success'] = True
    except (ValueError, OSError, KeyError, struct.error) as error:
        report['failure'] = str(error)
    (a.output / 'source-dt-report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'inputs'}, indent=2))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
