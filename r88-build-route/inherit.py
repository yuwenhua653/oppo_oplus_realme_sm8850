#!/usr/bin/env python3
"""Load the unchanged R87 preparation and reproduce its exact postimages."""
import hashlib
import importlib.util
from pathlib import Path
import sys

PARENT = 'r87-build-route/build-contract.json'
PARENT_SHA = 'ec8e557f2486a97a6fd2577b82e10727a2b9a8e73c7ea0efc62bb580b36eecbe'
PARENT_SOURCE_SHA = '4a4be491f873447a5249f175b3f2e1254b529d7abf4258400c06bdc5d618cad7'
PREFIX = 'vendor/qcom/sm8850/'
SOC = PREFIX + 'drivers/power/supply/mca/mca_strategy/strategy_fg/mca_soc_smooth.c'
SOC_PIN = {'bytes': 9546, 'sha256': '141889a0c5470421c51317873913383f21fa0f469934d1d945af5eae4691be8d'}


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def require(ok, why):
    if not ok:
        raise ValueError(why)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_r87(repo):
    repo = Path(repo).resolve()
    require(pin((repo / PARENT).read_bytes())['sha256'] == PARENT_SHA, 'Frozen R87 build contract changed')
    require(pin((repo / 'r87-build-route/SOURCE-CONTRACT.json').read_bytes())['sha256'] == PARENT_SOURCE_SHA,
            'Frozen R87 source contract changed')
    sys.path.insert(0, str(repo / 'r87-build-route'))
    return load('r88_frozen_r87', repo / 'r87-build-route/build_safety.py')


def parent_postimages(repo):
    r87 = frozen_r87(repo)
    _, _, pc, inputs, _, r84, r85, r86 = r87.check(repo)
    expected = r87.parent_postimages(repo, pc, inputs, r84, r85, r86)
    source = r87.source_contract(repo / 'r87-build-route')
    for row in source['read_only_guards']:
        digest = row['expected']['sha256']
        require(row['path'] not in expected or expected[row['path']] == digest,
                'R87 guard disagrees with inherited source')
        expected[row['path']] = digest
    for row in source['writes']:
        require(expected.get(row['path']) == row['before']['sha256'], 'R87 postimage ancestry mismatch')
        expected[row['path']] = row['after']['sha256']
    # This composite FG source was already compiled by R87. Its action-source
    # pin is explicit here because the R87 overlay did not itself modify it.
    data = (repo / 'r61-build-route/payload' / SOC.removeprefix(PREFIX)).read_bytes()
    require(pin(data) == SOC_PIN, 'R87 SOC action preimage changed')
    require(SOC not in expected or expected[SOC] == SOC_PIN['sha256'], 'SOC ancestor mismatch')
    expected[SOC] = SOC_PIN['sha256']
    return expected


def reconstruct_r87(repo, workspace):
    repo, workspace = Path(repo).resolve(), Path(workspace).resolve()
    r87 = frozen_r87(repo)
    r87.check(repo)
    source = r87.source_contract(repo / 'r87-build-route')
    old = load('r88_r87_offline_test_recipe', repo / 'r87-build-route/test_source.py')
    old.reconstruct_inputs(repo, workspace, source)
    r87.apply(workspace, repo / 'r87-build-route')
    destination = workspace / SOC
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = (repo / 'r61-build-route/payload' / SOC.removeprefix(PREFIX)).read_bytes()
    require(pin(data) == SOC_PIN, 'R87 SOC action preimage changed')
    destination.write_bytes(data)
    storage = PREFIX + 'drivers/power/supply/mca/mca_shared_memory/charger_partition.c'
    data = (repo / 'r61-build-route/payload' / storage.removeprefix(PREFIX)).read_bytes()
    require(pin(data)['sha256'] == parent_postimages(repo)[storage], 'Storage gate ancestor changed')
    destination = workspace / storage
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return r87
