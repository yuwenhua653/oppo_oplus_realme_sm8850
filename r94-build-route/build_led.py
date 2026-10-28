#!/usr/bin/env python3
"""Build one inactive LED candidate after exact frozen R92 preparation.

No kernel sync, preparation or build occurs until the reviewed LED payload
and its actual-source tests are pinned.
This route does not assemble images, alter R92 files, upload or flash anything.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from prepare_r92 import prepare

R92_SHA = '4771cf9fbaf45a31d1330e1f8f7d855bc0edfb61afbbf4022411639f98663bdb'
R92_ENGINE_SHA = '4d22b96c51e704faf6eac56436d17d0b25a506c924eec679dd6bd9fed973f672'
SOURCE = 'vendor/qcom/sm8850/drivers/leds/flash/leds-qcom-flash.c'
BEFORE = {'bytes': 38374, 'sha256': '84fd44ce4b6170066b82eeb082b634e6e051a412f736760cf76ec42c33017766'}
MODULE = {'module_name': 'leds_qcom_flash',
          'target': '//vendor/qcom/sm8850:canoe_perf/drivers/leds/flash/leds-qcom-flash',
          'expected_sources': [SOURCE]}
CONFIG_PIN = {'bytes': 261809, 'sha256': 'c758847251c59a89b3e3deb297e9a9830244da78a78156a98dfcd34e7ef4e6ea'}
CORE_CONFIG_PIN = {'bytes': 224834, 'sha256': '1694fba9900e978fb9494250fb5be8515d022b8b52062721b1a2d267f92490c0'}
POLICY = {'compile_only': True, 'flashable': False, 'activation_allowed': False,
          'hardware_tested': False, 'runtime_abi_compatible': 'NOT_YET_VALIDATED',
          'runtime_candidate_module_names': ['leds_qcom_flash']}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def safe(root, relative):
    root = Path(root).resolve()
    name = PurePosixPath(relative)
    require(relative and not name.is_absolute() and '..' not in name.parts, 'Unsafe source path')
    path = root / name
    require(path.resolve().is_relative_to(root), 'Escaping source path')
    require(all(not (root / Path(*name.parts[:i])).is_symlink()
                for i in range(1, len(name.parts) + 1)), 'Symlink source path')
    return path


def generated(root, relative):
    """Read a graph-bound Bazel artifact through its normal output symlink.

    Input sources disallow symlinks. Generated outputs are different: the
    pinned runner fixes --output_base to <workspace>/out/bazel-integration,
    and bazel-out points into that tree. Reject other escapes/redirects.
    The caller must supply a fixed CORE path or a verified aquery output.
    """
    root = Path(root).resolve()
    name = PurePosixPath(relative)
    require(relative and not name.is_absolute() and '..' not in name.parts and
            name.parts[0] == 'bazel-out', 'Only graph-bound Bazel outputs allowed')
    base = (root / 'out/bazel-integration').resolve()
    require(base.is_relative_to(root), 'Redirected pinned Bazel output base')
    link = root / 'bazel-out'
    if link.is_symlink():
        anchor = link.resolve()
        require(anchor.is_relative_to(base), 'Bazel output symlink escapes pinned output base')
    else:
        anchor = link.resolve()
        require(anchor.is_relative_to(root), 'Generated output tree escapes workspace')
    path = root / name
    require(path.resolve().is_relative_to(anchor), 'Generated artifact escapes Bazel output tree')
    require(path.is_file(), 'Missing generated artifact')
    return path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_patch(route):
    p = safe(route, 'LED-PATCH.json')
    c = json.loads(p.read_bytes())
    require(c.get('schema') == 1 and c.get('status') == 'FROZEN_REVIEWED_SOURCE',
            'LED patch is pending; no build authorized by this draft')
    require(all(c.get(k) is POLICY[k] for k in ('compile_only', 'flashable', 'activation_allowed')),
            'Compile-only inactive patch required')
    require(c.get('source') == SOURCE and c.get('before') == BEFORE,
            'Only the exact upstream LED source may be replaced')
    require(c.get('payload') == 'payload/leds-qcom-flash.c', 'Fixed LED payload path required')
    after = c.get('after')
    require(isinstance(after, dict) and set(after) == {'bytes', 'sha256'} and
            isinstance(after['bytes'], int) and after['bytes'] > 0 and
            isinstance(after['sha256'], str) and re.fullmatch('[0-9a-f]{64}', after['sha256']) and
            after != BEFORE, 'Real reviewed LED postimage required')
    require(pin(safe(route, c['payload']).read_bytes()) == after, 'LED payload pin mismatch')
    tests = c.get('source_tests')
    require(isinstance(tests, list) and tests, 'Pinned actual-source tests required')
    seen = set()
    for row in tests:
        require(set(row) == {'file', 'bytes', 'sha256'} and row['file'].startswith('tests/') and
                row['file'].endswith('.py') and row['file'] not in seen, 'Explicit unique Python test scripts required')
        seen.add(row['file'])
        require(pin(safe(route, row['file']).read_bytes()) == {k: row[k] for k in ('bytes', 'sha256')},
                'Production source test pin mismatch')
    inputs = c.get('test_inputs')
    require(isinstance(inputs, list) and inputs, 'Pinned host test inputs required')
    paths = [r['file'] for r in inputs]
    actual = {str(p.relative_to(route)) for p in safe(route, 'tests').rglob('*')
              if p.is_file() and '__pycache__' not in p.parts}
    require(len(paths) == len(set(paths)) and set(paths) == actual and seen <= set(paths),
            'Exact production test input inventory required')
    for row in inputs:
        require(set(row) == {'file', 'bytes', 'sha256'} and row['file'].startswith('tests/'),
                'Test inputs must stay inside tests/')
        require(pin(safe(route, row['file']).read_bytes()) == {k: row[k] for k in ('bytes', 'sha256')},
                'Production test support pin mismatch')
    return c


def patch_source(root, route, contract, verify=False):
    source = safe(root, SOURCE)
    expected = contract['after'] if verify else BEFORE
    require(pin(source.read_bytes()) == expected, 'Exact LED source pre/postimage mismatch')
    if not verify:
        source.write_bytes(safe(route, contract['payload']).read_bytes())
    require(pin(source.read_bytes()) == contract['after'], 'LED postimage verification failed')


def plan(bazel, options, cores):
    require(cores == ['//common:kernel_aarch64', '//myron_artifact_metadata:kernel_release'],
            'Frozen core metadata targets changed')
    targets = [MODULE['target']] + cores
    return {'analysis': bazel + ['aquery'] + options + ['--output=jsonproto',
                '--include_artifacts=true', '--include_commandline=true',
                'deps(' + MODULE['target'] + ')'],
            'kconfig': bazel + ['build'] + options + ['//vendor/qcom/sm8850:kconfig.msm.generated'],
            'config': bazel + ['build'] + options + ['//vendor/qcom/sm8850:canoe_perf_config'],
            'build': bazel + ['build'] + options + targets,
            'outputs': bazel + ['cquery'] + options + ['--output=files',
                'deps(set(' + ' '.join(targets) + '))']}


def resolve_led(graph, resolver):
    # Existing resolver matches filenames literally; ELF names normalize '-'.
    row = resolver.resolve(graph, dict(MODULE, module_name='leds-qcom-flash'))
    return dict(row, module_name=MODULE['module_name'])


def verify_config(root, graph):
    labels = {str(r['id']): r['label'] for r in graph.get('targets', [])}
    fragments = {str(r['id']): r for r in graph.get('pathFragments', [])}
    def fragment(k, seen=None):
        k = str(k); seen = set() if seen is None else seen
        require(k in fragments and k not in seen, 'Invalid config artifact path')
        seen.add(k); row = fragments[k]; parent = str(row.get('parentId', '0'))
        result = (fragment(parent, seen) + '/' if parent not in ('', '0') else '') + row['label']
        seen.remove(k)
        return result
    artifacts = {str(r['id']): r.get('execPath') or fragment(r['pathFragmentId']) for r in graph.get('artifacts', [])}
    depsets = {str(r['id']): r for r in graph.get('depSetOfFiles', [])}
    def consumed(keys, seen=None):
        seen = set() if seen is None else seen; result = set()
        for key in keys:
            key = str(key)
            require(key in depsets and key not in seen, 'Invalid config depset')
            seen.add(key); row = depsets[key]
            result.update(str(x) for x in row.get('directArtifactIds', []))
            result.update(consumed(row.get('transitiveDepSetIds', []), seen)); seen.remove(key)
        return result
    def actions(target, mnemonic=None):
        return [a for a in graph.get('actions', []) if labels.get(str(a.get('targetId'))) == target and
                (mnemonic is None or a.get('mnemonic') == mnemonic)]
    ca = actions('//vendor/qcom/sm8850:canoe_perf_config', 'DdkConfig')
    la = actions(MODULE['target'], 'KernelModule')
    require(len(ca) == len(la) == 1, 'One shared config and one LED compile action required')
    tree = 'bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf_config/out_dir'
    tree_ids = [str(k) for k in ca[0].get('outputIds', []) if artifacts[str(k)] == tree]
    inputs = consumed(la[0].get('inputDepSetIds', []))
    require(len(tree_ids) == 1 and tree_ids[0] in inputs, 'LED must consume the exact common R92 module config')
    own = actions(MODULE['target'] + '_config')
    require(not any(a.get('mnemonic') == 'DdkConfig' for a in own), 'Per-LED config override forbidden')
    setup = [str(k) for a in own for k in a.get('outputIds', []) if artifacts[str(k)].endswith('_config_setup.sh')]
    require(len(setup) == 1 and setup[0] in inputs and artifacts[setup[0]] in '\n'.join(la[0].get('arguments', [])),
            'LED config setup must feed its actual compiler command')
    relative = tree + '/.config'; data = generated(root, relative).read_bytes()
    require(pin(data) == CONFIG_PIN and b'CONFIG_LEDS_QCOM_FLASH=m\n' in data,
            'Effective external config must stay byte-exact R92')
    return {'config_path': relative, **pin(data), 'consumed_by': MODULE['target']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root', type=Path, required=True)
    p.add_argument('--route', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--check-inputs', action='store_true')
    for name in ('workspace', 'package', 'baseline', 'r18'):
        p.add_argument('--' + name, type=Path)
    p.add_argument('--jobs', type=int, default=2)
    p.add_argument('--ram-mb', type=int, default=10000)
    args = p.parse_args()
    route = args.route.resolve(); repo = args.repo_root.resolve()
    # Must be first: the unfinished draft cannot launch inherited preparation.
    patch = check_patch(route)
    require(pin(safe(repo, 'r92-build-route/build-contract.json').read_bytes())['sha256'] == R92_SHA,
            'Frozen R92 build contract changed')
    engine_path = safe(repo, 'r92-build-route/build_pd_provider.py')
    require(pin(engine_path.read_bytes())['sha256'] == R92_ENGINE_SHA, 'Frozen R92 boundary changed')
    sys.path.insert(0, str(engine_path.parent))
    parent = load('r94_frozen_r92', engine_path)
    boundary = parent.Boundary(repo)
    boundary.check(repo)
    if args.check_inputs:
        print(json.dumps({'status': 'PASS_PATCH_AND_R92_INPUTS', **POLICY}))
        return 0
    require(all(getattr(args, n) for n in ('workspace', 'package', 'baseline', 'r18')), 'Four build paths required')
    require(1 <= args.jobs <= 4 and args.ram_mb >= 2048, 'Invalid resources')
    root = args.workspace.resolve(); reports = root / 'integration-reports'
    output = root / 'integration-artifacts/r94-led-candidate'
    require(not output.exists() and not output.is_symlink(), 'Fresh candidate output required')
    status = dict(POLICY, success=False, compiled=False, phase='prepare_frozen_r92',
                  github={k: os.environ.get(k, '') for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')})
    try:
        scope = prepare(boundary, args, reports, status)
        patch_source(root, route, patch)
        for row in patch['source_tests']:
            scope['runner'].logged([sys.executable, '-B', str(safe(route, row['file'])),
                '--source', str(safe(root, SOURCE)), '--out', str(reports / 'r94-host' / Path(row['file']).stem)],
                root, reports / ('r94-' + Path(row['file']).stem + '.log'))
        scope['runner'].build_targets(root, 'soc')  # Metadata only; ignore aggregate labels.
        commands = plan(scope['bazel'], scope['options'], scope['contract']['core_targets'])
        write(reports / 'r94-commands.json', commands)
        result = subprocess.run(commands['analysis'], cwd=root, capture_output=True, text=True)
        (reports / 'r94-aquery.json').write_text(result.stdout)
        (reports / 'r94-aquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'LED aquery failed before compilation')
        graph = json.loads(result.stdout)
        selected = resolve_led(graph, scope['resolver'])
        write(reports / 'r94-led-action.json', scope['shared'].action_chain(graph, [SOURCE], selected['output']))
        for stage in ('kconfig', 'config'):
            scope['runner'].logged(commands[stage], root, reports / ('r94-' + stage + '.log'))
        config = verify_config(root, graph)
        write(reports / 'r94-config-prebuild.json', config)
        scope['runner'].logged(commands['build'], root, reports / 'r94-build.log')
        result = subprocess.run(commands['outputs'], cwd=root, capture_output=True, text=True)
        (reports / 'r94-cquery.txt').write_text(result.stdout)
        (reports / 'r94-cquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'LED output cquery failed')
        patch_source(root, route, patch, verify=True)
        write(reports / 'r94-parent-postimages.json', boundary.prebuild_or_postbuild(root, repo,
              scope['pc'], scope['parent_inputs'], scope['r84'], repo / 'r88-build-route'))
        require(verify_config(root, graph) == config, 'Module configuration changed during build')
        core = generated(root, scope['shared'].CORE + 'kernel_aarch64_dot_config')
        require(pin(core.read_bytes()) == CORE_CONFIG_PIN, 'Core config differs from R92 compile proof')
        collected = scope['shared'].collect_outputs(root, output, scope['contract'],
                    [selected], result.stdout.splitlines(), args.r18.resolve())
        # Compiled provider KOs and compiled Image are never runtime replacements.
        shutil.copy2(safe(root, SOURCE), output / 'leds-qcom-flash.c')
        shutil.copy2(route / 'LED-PATCH.json', output / 'LED-PATCH.json')
        status.update(success=True, compiled=True, phase='single_led_compiled_pending_runtime_abi',
                      round='R94', exact_changed_sources=[SOURCE], config=config,
                      parent_build_contract_sha256=R92_SHA,
                      source_contract_sha256=pin((route / 'LED-PATCH.json').read_bytes())['sha256'],
                      build_route_sha256=pin(Path(__file__).read_bytes())['sha256'],
                      source_preparation_sha256=pin((route / 'prepare_r92.py').read_bytes())['sha256'],
                      **collected)
        status.pop('build_contract_sha256', None)  # inherited R88 value is not R94's contract
        write(output / 'candidate-status.json', status)
        write(output / 'artifact-lock.json', {'schema': 1, **POLICY, 'files': [
            {'file': str(p.relative_to(output)), **pin(p.read_bytes())}
            for p in sorted(output.rglob('*')) if p.is_file()]})
    except Exception as error:
        status.update(success=False, phase='failed', error=str(error))
        raise
    finally:
        write(reports / 'r94-status.json', status)
    return 0


if __name__ == '__main__':
    sys.exit(main())
