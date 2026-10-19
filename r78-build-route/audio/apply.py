#!/usr/bin/env python3
"""Apply or verify the exact, compile-only TFA source delta after R77 preparation."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('Unsafe relative path: ' + relative)
    root = Path(root).resolve()
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Symlink in path: ' + relative)
    if not current.resolve().is_relative_to(root):
        raise ValueError('Path escapes root: ' + relative)
    return current


def check(package_dir):
    root = Path(package_dir).resolve()
    contract = json.loads(safe(root, 'contract.json').read_text())
    if (contract['schema'] != 1 or contract['compile_only'] is not True or
            contract['runtime_loading_approved'] is not False):
        raise ValueError('Expected compile-only source contract')
    locked = contract['files']
    if len({r['path'] for r in locked}) != len(locked):
        raise ValueError('Duplicate locked file')
    for row in locked:
        data = safe(root, row['path']).read_bytes()
        if len(data) != row['bytes'] or sha(data) != row['sha256']:
            raise ValueError('Locked input changed: ' + row['path'])
    actual = {str(p.relative_to(root)) for p in root.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.name != 'contract.json'}
    if actual != {r['path'] for r in locked}:
        raise ValueError('Source package inventory changed')
    fragment = safe(root, 'fragments/modules.bzl').read_text()
    body = ast.parse('def register_modules(registry):\n' + fragment).body[0].body
    if len(body) != 1 or not isinstance(body[0], ast.Expr) or not isinstance(body[0].value, ast.Call):
        raise ValueError('Exactly one TFA registration required')
    call = body[0].value
    if (not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name) or
            call.func.value.id != 'registry' or call.func.attr != 'register' or call.args):
        raise ValueError('Expected registry.register declaration')
    args = {r.arg: ast.literal_eval(r.value) for r in call.keywords}
    if args != contract['registration'] or len(args) != len(call.keywords):
        raise ValueError('TFA registration mismatch')
    srcs = args['srcs']
    if len(srcs) != 76 or len(set(srcs)) != 76 or sum(x.endswith('.c') for x in srcs) != 4:
        raise ValueError('Expected exact four C units and 72 headers')
    if set(srcs) != {str(p.relative_to(root / 'payload')) for p in (root / 'payload').rglob('*')
                     if p.is_file() and p.suffix in ('.c', '.h')}:
        raise ValueError('Registry source inventory mismatch')
    provenance = json.loads(safe(root, 'provenance/upstream-source-lock.json').read_text())
    upstream = {r['path'].removeprefix('asoc/codecs/tfa986x/'): r for r in provenance['files']}
    if (provenance['repository'] != 'MiCode/vendor_qcom_opensource_audio-kernel' or
            provenance['commit'] != 'e5ba38a941f1065f0eb984412dfe702e6b0add90'):
        raise ValueError('Wrong pinned donor')
    for source in srcs:
        relative = source.removeprefix('drivers/xiaomi/myron_tfa98xx/')
        data = safe(root, 'payload/' + source).read_bytes()
        changed = {r['relative']: r for r in contract['modified_sources']}
        if relative in changed:
            row = changed[relative]
            before = safe(root, row['before_path']).read_bytes()
            diff = ''.join(difflib.unified_diff(before.decode().splitlines(keepends=True),
                          data.decode().splitlines(keepends=True), fromfile='a/' + relative,
                          tofile='b/' + relative)).encode()
            if diff != safe(root, row['patch']).read_bytes():
                raise ValueError('Reviewed driver delta changed: ' + relative)
            data = before
        if sha(data) != upstream[relative]['sha256'] or len(data) != upstream[relative]['bytes']:
            raise ValueError('Donor behavior changed: ' + relative)
    kconfig = safe(root, 'payload/drivers/xiaomi/myron_tfa98xx/Kconfig').read_text()
    if [s.strip() for s in kconfig.splitlines() if s.strip().startswith('default ')] != ['default n']:
        raise ValueError('TFA Kconfig must remain default n')
    config = ast.parse(safe(root, 'fragments/canoe_perf.bzl').read_text()).body
    if len(config) != 1 or not isinstance(config[0], ast.Assign) or len(config[0].targets) != 1:
        raise ValueError('Only one compile configuration assignment permitted')
    target = config[0].targets[0]
    if (not isinstance(target, ast.Subscript) or not isinstance(target.value, ast.Name) or
            target.value.id != 'canoe_perf_config' or ast.literal_eval(target.slice) != 'CONFIG_MYRON_TFA98XX' or
            ast.literal_eval(config[0].value) != 'm'):
        raise ValueError('Expected target-local modular TFA compilation')
    writes = contract['writes']
    if len(writes) != 81 or len({r['destination'] for r in writes}) != 81:
        raise ValueError('Expected three appended build files, 77 new TFA files, and one machine source')
    for row in writes:
        data = safe(root, row['source']).read_bytes()
        if row['mode'] == 'new':
            if row['before_sha256'] is not None:
                raise ValueError('New source must have absent preimage')
        elif row['mode'] in ('append', 'replace'):
            before = safe(root, row['preimage']).read_bytes()
            if sha(before) != row['before_sha256']:
                raise ValueError('R77 preimage changed')
            if row['mode'] == 'append':
                data = before + data
        else:
            raise ValueError('Unknown operation')
        if len(data) != row['bytes'] or sha(data) != row['after_sha256']:
            raise ValueError('Postimage changed: ' + row['destination'])
    return {'status': 'PASS_SOURCE_DELTA', 'compile_only': True, 'runtime_loading_approved': False,
            'writes': len(writes), 'registry_source_count': 76, 'C_units': 4, 'headers': 72,
            'module': contract['module'], 'compiled': False}


def apply(workspace, package_dir, verify=False):
    result = check(package_dir)
    root, workspace = Path(package_dir).resolve(), Path(workspace).resolve()
    contract = json.loads((root / 'contract.json').read_text())
    pending = []
    for row in contract['writes']:
        target = safe(workspace, row['destination'])
        if target.exists() and not target.is_file():
            raise ValueError('Non-file destination: ' + row['destination'])
        current = sha(target.read_bytes()) if target.exists() else None
        if current not in (row['before_sha256'], row['after_sha256']):
            raise ValueError('Unexpected R77 prepared preimage: ' + row['destination'])
        if verify and current != row['after_sha256']:
            raise ValueError('TFA source delta not applied: ' + row['destination'])
        data = safe(root, row['source']).read_bytes()
        if row['mode'] == 'append':
            data = safe(root, row['preimage']).read_bytes() + data
        pending.append((target, data, current != row['after_sha256']))
    # Every preimage is checked before the first write; no shell or device calls.
    if not verify:
        for target, data, changed in pending:
            if changed:
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + '.r78-tfa-tmp')
                with temporary.open('xb') as stream:
                    stream.write(data)
                temporary.replace(target)
    result.update(mode='verify' if verify else 'apply', changed=sum(x[2] for x in pending))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-dir', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(json.dumps(apply(args.workspace, args.package_dir, args.check) if args.workspace else
                     check(args.package_dir), indent=2))
