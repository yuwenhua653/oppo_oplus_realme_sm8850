#!/usr/bin/env python3
"""Apply reviewed R79 postimages after unchanged R78 preparation."""
import argparse
import json
from pathlib import Path
from r79_inputs import check, inherited_postimages, require, safe, sha

def apply(workspace, repo, c, verify=False):
    check(repo, c)
    pending = []
    for row in c['writes']:
        p = safe(workspace, row['destination'], exists=False)
        require(not p.exists() or p.is_file(), 'Non-file destination')
        actual = sha(p.read_bytes()) if p.exists() else None
        allowed = {row['after_sha256']} if verify else {row['before_sha256'], row['after_sha256']}
        require(actual in allowed, 'Unexpected R79 preimage: ' + row['destination'])
        pending.append((p, safe(repo, row['source']).read_bytes(), actual != row['after_sha256']))
    # Validate every destination before writing any source.
    if not verify:
        for p, data, changed in pending:
            if changed:
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_name(p.name + '.r79-tmp')
                with tmp.open('xb') as f:
                    f.write(data)
                tmp.replace(p)
    return {'status': 'PASS', 'mode': 'verify' if verify else 'apply', 'writes': len(pending)}

def verify_applied(workspace, repo, c):
    expected = inherited_postimages(repo)
    expected.update({r['destination']: r['after_sha256'] for r in c['writes']})
    for relative, digest in expected.items():
        require(sha(safe(workspace, relative).read_bytes()) == digest, 'Integrated postimage changed: ' + relative)
    return {'status': 'PASS', 'checked_destinations': len(expected)}

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', required=True, type=Path)
    p.add_argument('--repo-root', required=True, type=Path)
    p.add_argument('--check', action='store_true')
    a = p.parse_args()
    repo = a.repo_root.resolve()
    c = json.loads((repo / 'r79-build-route/repair-contract.json').read_text())
    print(json.dumps(apply(a.workspace.resolve(), repo, c, a.check), indent=2))
