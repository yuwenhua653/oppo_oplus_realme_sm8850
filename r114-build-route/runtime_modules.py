#!/usr/bin/env python3
"""Retain the previously validated direct-touch driver in full kernel builds."""
import hashlib
import importlib.util
import json
from pathlib import Path

SOC = 'vendor/qcom/sm8850/'
TARGET = '//vendor/qcom/sm8850:canoe_perf/drivers/input/touchscreen/myron/focaltech_myron'
PREIMAGES = {
    'drivers/xiaomi/myron/modules.bzl': 'b9472f15988805e6150c395f418e3a5b2a7a0c02668c5eddf8f1a7f9215153b8',
    'drivers/xiaomi/myron/Kconfig': '2d1ff3da5a4ec586c19b5c573b5c47370b19a01fd55cdf3d6dfba5515b7fe5c0',
    'configs/canoe_perf.bzl': '73e51362e61cf75c15c0ed9f026cc1b36ed72eedafc826405fb70f2c6ed7b6c3',
}

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def inputs(repo):
    route = repo / 'r58-build-route'
    spec = importlib.util.spec_from_file_location('r114_touch_check', route/'check_touch_inputs.py')
    checker = importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    contract = json.loads((route/'touch-contract.json').read_text())
    checker.check(repo, contract)
    require([r['target'] for r in contract['modules']] == [TARGET], 'Unexpected touch target')
    audio = repo/'r78-build-route/audio'
    before = {}
    for name, digest in PREIMAGES.items():
        before[SOC+name] = (audio/'preimage'/name).read_bytes() + (audio/'fragments'/Path(name).name).read_bytes()
        require(sha(before[SOC+name]) == digest, 'Inherited source preimage mismatch: '+name)
    source = (route/'payload/drivers/xiaomi/myron/modules.bzl').read_text()
    registration = source[source.rindex('    registry.register('):]
    require(registration.count('focaltech_myron.ko') == 1, 'Ambiguous touch registration')
    config = (route/'payload/drivers/xiaomi/myron/Kconfig').read_text()
    start = config.index('config TOUCHSCREEN_FOCALTECH_MYRON\n')
    fragment = config[start:config.index('\nendmenu', start)]
    after = dict(before)
    after[SOC+'drivers/xiaomi/myron/modules.bzl'] += registration.encode()
    after[SOC+'drivers/xiaomi/myron/Kconfig'] += ('\n'+fragment+'\n').encode()
    after[SOC+'configs/canoe_perf.bzl'] += b'\n# Preserve the validated direct-touch runtime module.\ncanoe_perf_config["CONFIG_TOUCHSCREEN_FOCALTECH_MYRON"] = "m"\n'
    for source, destination in [('focaltech_myron.c','focaltech_myron.c'),('fts_myron_frame.h','fts_myron_frame.h')]:
        name = SOC+'drivers/input/touchscreen/myron/'+destination
        before[name] = None
        after[name] = (repo/'r58-driver'/source).read_bytes()
    return before, after

def prepare(root, repo, reports):
    before, after = inputs(repo)
    for name in after:
        path = root/name
        require(not path.is_symlink() and path.resolve().is_relative_to(root.resolve()), 'Redirected touch source')
        data = path.read_bytes() if path.exists() else None
        require(data in (before[name], after[name]), 'Unexpected prepared touch input: '+name)
    for name, data in after.items():
        path = root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    reports.mkdir(parents=True,exist_ok=True)
    (reports/'r114-runtime-touch.json').write_text(json.dumps({
        'target':TARGET, 'driver_behavior_changed':False,
        'files':{name:{'before':sha(before[name]) if before[name] is not None else None,'after':sha(data)} for name,data in after.items()},
    },indent=2)+'\n')

def required_names(repo):
    names=json.loads((repo/'r114-build-route/runtime-module-names.json').read_text())['required_module_names']
    require(len(names)==297 and names==sorted(set(names)) and 'focaltech_myron' in names,'Unexpected runtime name inventory')
    return set(names)

def check_coverage(repo, modules):
    required=required_names(repo)
    missing=sorted(required-{m['name'] for m in modules})
    require(not missing,'Missing runtime module outputs: '+repr(missing))
    return {'required_names':len(required),'missing':missing,'abi_qualified':False}
