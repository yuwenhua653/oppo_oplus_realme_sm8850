#!/usr/bin/env python3
"""Exercise missing-provider regressions on every actual candidate log user."""
import copy
import json
from pathlib import Path

from check_mca_log_deps import PROVIDER, inspect, registrations

ROOT = Path(__file__).resolve().parent.parent
registry = registrations((ROOT / 'r61-build-route/payload/drivers/xiaomi/myron/modules.bzl').read_text())
result = inspect(ROOT, registry)
assert result['status'] == 'PASS'
cases = []
for user in result['users']:
    mutant = copy.deepcopy(registry)
    mutant[user['module']]['deps'].remove(PROVIDER)
    rejected = inspect(ROOT, mutant)
    assert rejected['status'] == 'FAIL' and rejected['missing_direct_provider'] == [user['module']]
    cases.append(user['module'])
assert len(cases) == 14
print(json.dumps({'schema': 1, 'status': 'PASS', 'missing_provider_mutants_rejected': len(cases),
                  'modules': cases, 'kernel_compiled': False,
                  'scope': 'Actual candidate C macro calls with one dependency removed per fixture.'}, indent=2))
