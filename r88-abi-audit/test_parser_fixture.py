#!/usr/bin/env python3
"""Regress the generic graph parser against actual historical R87 actions.

This does not call audit_identity/audit_closure or produce an R88 qualification.
"""
import argparse
import json
from pathlib import Path
from audit_identity import Graph, need, pin, read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', required=True, type=Path)
    parser.add_argument('--action-dir', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    need(not args.out.exists(), 'fresh test report path')
    graph = Graph(read(args.graph))
    fixtures = sorted(args.action_dir.glob('r87-action-*.json'))
    need(len(fixtures) == 47, 'actual historical R87 47-action fixture')
    for path in fixtures:
        row = read(path)
        calculated, action = graph.chain(row['required_sources'], row['output'])
        need(calculated == {key: row[key] for key in calculated}, 'unchanged generic parser: ' + path.name)
        declared = graph.declared(action)
        target = graph.labels[str(action['targetId'])]
        setups = [graph.artifacts[str(key)] for step in graph.actions
                  if graph.labels.get(str(step.get('targetId'))) == target + '_config'
                  for key in step.get('outputIds', [])
                  if graph.artifacts[str(key)].endswith('_config_setup.sh')]
        need(len(setups) == 1 and setups[0] in declared and setups[0] in '\n'.join(action['arguments']),
             'real target config setup: ' + path.name)
    report = {'schema': 1, 'status': 'PASS_GENERIC_GRAPH_PARSER_HISTORICAL_FIXTURE_ONLY',
              'graph': pin(args.graph), 'actions': len(fixtures),
              'activation_allowed': False, 'image_created': False, 'R88_artifact_qualified': False}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
