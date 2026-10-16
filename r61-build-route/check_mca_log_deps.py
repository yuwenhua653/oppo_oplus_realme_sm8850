#!/usr/bin/env python3
"""Reject MCA log users without their direct symbol provider before source sync."""
import argparse
import ast
import json
from pathlib import Path
import re

PROVIDER = 'drivers/power/supply/mca/mca_common/mca_log'
SOC_PREFIX = '//vendor/qcom/sm8850:canoe_perf/'
LOG_CALL = re.compile(r'\b(?:_{0,2}mca_log_(?:err|info|debug)|mca_log_(?:jirabot|charge_log_register|get_charge_boot_mode))\s*\(')


def registrations(text):
    result = {}
    for call in ast.walk(ast.parse(text)):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute) or call.func.attr != 'register':
            continue
        values = {kw.arg: kw.value for kw in call.keywords}
        name = ast.literal_eval(values['name'])
        if name in result:
            raise ValueError('Duplicate module registration: ' + name)
        result[name] = {key: ast.literal_eval(values[key]) for key in ('name', 'config', 'srcs', 'deps') if key in values}
    return result


def strip_comments_and_strings(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '', text, flags=re.S)


def inspect(root, registry=None):
    route = root / 'r61-build-route'
    registry = registrations((route / 'payload/drivers/xiaomi/myron/modules.bzl').read_text()) if registry is None else registry
    provider = registry.get(PROVIDER)
    if not provider or provider.get('config') != 'CONFIG_MYRON_MCA_BASE':
        raise ValueError('Expected mca_log provider registration missing')
    config_tree = ast.parse((route / 'payload/configs/canoe_perf.bzl').read_text())
    config = ast.literal_eval(config_tree.body[0].value)
    if config.get(provider['config']) not in ('y', 'm'):
        raise ValueError('mca_log provider is disabled in the actual compile config')
    contract = json.loads((route / 'battery-contract.json').read_text())
    users, missing = [], []
    for module in contract['modules']:
        if not module['target'].startswith(SOC_PREFIX):
            continue
        name = module['target'][len(SOC_PREFIX):]
        row = registry[name]
        sources = [p for p in row['srcs'] if p.endswith('.c')]
        if not sources:
            raise ValueError('No C source declared: ' + name)
        calls = []
        for source in sources:
            candidate = route / 'payload' / source
            if not candidate.is_file():
                raise ValueError('Missing candidate source: ' + source)
            calls.extend(match.group(0).split('(')[0].strip() for match in LOG_CALL.finditer(strip_comments_and_strings(candidate.read_text())))
        if calls:
            users.append({'module': name, 'calls': sorted(set(calls)), 'direct_provider': PROVIDER})
            if PROVIDER not in row.get('deps', []):
                missing.append(name)
    return {'schema': 1, 'status': 'FAIL' if missing else 'PASS', 'missing_direct_provider': missing,
            'users': users, 'scope': 'Known MCA logging macro/provider relation only; not a kernel build or complete symbol audit.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.root.resolve())
    print(json.dumps(result, indent=2))
    return 1 if result['missing_direct_provider'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
