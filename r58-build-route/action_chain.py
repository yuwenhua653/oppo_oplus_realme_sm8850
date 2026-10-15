#!/usr/bin/env python3
"""Check Kleaf source -> KernelModule staging -> copied KO provenance.

This accepts the actual two-action DDK graph rather than requiring source inputs
on the final copy action. It never executes action arguments.
"""
import argparse
import json
from pathlib import Path


def require(ok, message):
    if not ok:
        raise ValueError(message)


def action_chain(document, sources, output):
    fragments = {str(row['id']): row for row in document.get('pathFragments', [])}
    path_cache = {}

    def fragment(identifier, visiting=None):
        identifier = str(identifier)
        if identifier in path_cache:
            return path_cache[identifier]
        visiting = set() if visiting is None else visiting
        require(identifier in fragments and identifier not in visiting, 'Invalid path fragment')
        visiting.add(identifier)
        row = fragments[identifier]
        parent = str(row.get('parentId', '0'))
        result = (fragment(parent, visiting) + '/' if parent not in ('0', '') else '') + row['label']
        visiting.remove(identifier)
        path_cache[identifier] = result
        return result

    artifacts = {str(row['id']): row.get('execPath') or fragment(row['pathFragmentId'])
                 for row in document.get('artifacts', [])}
    depsets = {str(row['id']): row for row in document.get('depSetOfFiles', [])}
    input_cache = {}

    def inputs(identifier, visiting=None):
        identifier = str(identifier)
        if identifier in input_cache:
            return input_cache[identifier]
        visiting = set() if visiting is None else visiting
        require(identifier in depsets and identifier not in visiting, 'Invalid input depset')
        visiting.add(identifier)
        row = depsets[identifier]
        result = {artifacts[str(value)] for value in row.get('directArtifactIds', [])}
        for child in row.get('transitiveDepSetIds', []):
            result.update(inputs(child, visiting))
        visiting.remove(identifier)
        input_cache[identifier] = result
        return result

    rows = []
    for action in document.get('actions', []):
        inpaths = set()
        for identifier in action.get('inputDepSetIds', []):
            inpaths.update(inputs(identifier))
        rows.append({'action': action, 'inputs': inpaths,
                     'outputs': {artifacts[str(value)] for value in action.get('outputIds', [])}})
    final = [row for row in rows if output in row['outputs']]
    require(len(final) == 1, 'Expected one final KO-producing action')
    final = final[0]
    required = set(sources)
    require(required, 'No expected source inputs supplied')
    candidates = []
    for compile_row in rows:
        if compile_row['action'].get('mnemonic') != 'KernelModule':
            continue
        if not required <= compile_row['inputs']:
            continue
        if compile_row is final:
            candidates.append((compile_row, 'direct', [output]))
        elif final['action'].get('mnemonic') == 'KernelModuleCpOutputs':
            shared = sorted(compile_row['outputs'] & final['inputs'])
            staging = [path for path in shared if path.endswith('/staging')]
            if len(staging) == 1:
                candidates.append((compile_row, 'staging-copy', staging))
    require(len(candidates) == 1, 'Expected one source-bound compiler-to-KO action chain')
    compile_row, kind, intermediates = candidates[0]
    return {'schema': 1, 'status': 'PASS', 'kind': kind, 'required_sources': sorted(required),
            'output': output, 'intermediate_artifacts': intermediates,
            'compile_mnemonic': compile_row['action'].get('mnemonic'),
            'compile_action_key': compile_row['action'].get('actionKey'),
            'final_mnemonic': final['action'].get('mnemonic'),
            'final_action_key': final['action'].get('actionKey'),
            'compile_declared_input_count': len(compile_row['inputs']),
            'limits': 'Graph provenance only; hash locked sources, ELF ABI and hardware behavior require separate gates.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aquery', required=True, type=Path)
    parser.add_argument('--source', action='append', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    result = action_chain(json.loads(args.aquery.read_text()), args.source, args.output)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
