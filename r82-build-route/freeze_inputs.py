#!/usr/bin/env python3
"""Freeze the R82 CNSS-only route after its source and evidence files are final."""
import hashlib
import json
from pathlib import Path
import re


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    route = Path(__file__).resolve().parent
    repo = route.parent
    parent_name = 'r79-build-route/repair-contract.json'
    parent_bytes = (repo / parent_name).read_bytes()
    assert sha(parent_bytes) == 'aabb37375d33dfe9ae1bf9a86e7a3ce4602bd67f06855709b046fa493d744cc2'
    parent = json.loads(parent_bytes)
    for name in ('SOURCE-CONTRACT.json', 'apply_cnss.py', 'test_cnss.py'):
        assert (route / name).is_file(), 'Missing final R82 input: ' + name
    source = json.loads((route / 'SOURCE-CONTRACT.json').read_text())
    c = {key: parent[key] for key in ('baseline_image_sha256', 'baseline_kernel_release',
                                      'sources_lock_sha256', 'git_heads', 'core_targets')}
    c.update({
        'schema': 1,
        'base_commit': '007514c3e5b58dc9b3ea9aa3a72586527fa8c5bc',
        'parent_contract': parent_name,
        'parent_contract_sha256': sha(parent_bytes),
        'compile_only': True,
        'flashable': False,
        'hardware_tested': False,
        'experiment': 'Restore the Myron/Peach stock BDF and REGDB filename selection with existing DT precedence',
        'runtime_candidate_module_names': ['cnss2'],
        'runtime_baseline': {
            'vendor_boot_sha256': 'db3298a43a44f704faf3e593a08bb750389fbc789d6c4dffd95fa85016305806',
            'cnss2_module_sha256': 'a2a29ea47bd7b9a22702cf7d52f27d8fec9aa9a7befd477ec974e5a16924cbb2',
            'wlan_module_sha256': 'd987d12125e5dbd82bfa9225741dadb2a8b7fe8ba8078c3588554e999a973598',
            'hwid_module_sha256': '056ea6ca25ff336c92c43c52729b34f88aab136fca449b2cdffc4bd37cb403d6',
            'hwid_getter_crc32': '0x0f600de8',
        },
        'modules': [{
            'target': '//vendor/qcom/sm8850-modules/qcom/opensource/wlan/platform:canoe_perf_cnss2',
            'module_name': 'cnss2',
            'expected_sources': ['vendor/qcom/sm8850-modules/qcom/opensource/wlan/platform/cnss2/qmi.c'],
        }],
        'locked_files': [],
    })
    assert source['source_commit'] == c['git_heads']['vendor/qcom/sm8850-modules']
    for p in sorted(route.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.name == 'cnss-contract.json':
            continue
        assert not p.is_symlink()
        data = p.read_bytes()
        c['locked_files'].append({'path': str(p.relative_to(repo)), 'bytes': len(data), 'sha256': sha(data)})
    contract = route / 'cnss-contract.json'
    contract.write_text(json.dumps(c, indent=2) + '\n')
    digest = sha(contract.read_bytes())
    workflow = repo / '.github/workflows/build-myron-cnss-r82.yml'
    text = workflow.read_text()
    text, count = re.subn(r"echo '[A-Za-z0-9_]+  r82-build-route/cnss-contract\.json'",
                         "echo '" + digest + "  r82-build-route/cnss-contract.json'", text)
    assert count == 1, 'Workflow must contain one contract hash gate'
    workflow.write_text(text)
    print(json.dumps({'contract_sha256': digest, 'locked_files': len(c['locked_files'])}))


if __name__ == '__main__':
    main()
