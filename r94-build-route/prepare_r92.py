"""Reuse only the SHA-pinned R92 engine source preparation, never its build list.

R92 already wraps the frozen R88 engine to apply/check R89, R90 and R92.
Select its contiguous source-preparation statements from the audited AST;
stop before the metadata target helper and before any aquery/build/cquery.
This avoids maintaining another copy of nine rounds of source preparation.
"""
import ast
import hashlib
from pathlib import Path

ENGINE_SHA = '5341b707f8c318d3836936229b919a1bd2bad8c810b32c67b2cb91e6f0d9f591'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def preparation_statements(data):
    require(hashlib.sha256(data).hexdigest() == ENGINE_SHA,
            'Frozen R88 source-preparation engine changed')
    tree = ast.parse(data)
    mains = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main']
    require(len(mains) == 1, 'One frozen main required')
    tries = [n for n in mains[0].body if isinstance(n, ast.Try)]
    require(len(tries) == 1, 'One frozen preparation/build try block required')
    body = tries[0].body
    starts = [i for i, n in enumerate(body) if isinstance(n, ast.Assign) and
              isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and
              n.value.func.id == 'check']
    stops = [i for i, n in enumerate(body) if isinstance(n, ast.Expr) and
             isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute) and
             isinstance(n.value.func.value, ast.Name) and n.value.func.value.id == 'runner' and
             n.value.func.attr == 'build_targets']
    require(len(starts) == len(stops) == 1 and starts[0] < stops[0],
            'Unambiguous frozen source-preparation boundary required')
    selected = body[starts[0]:stops[0]]
    # The fixed hash is authoritative. These checks make the boundary reviewable.
    text = ast.unparse(ast.Module(body=selected, type_ignores=[]))
    require('verify_postimages(root, repo, pc, parent_inputs, r84, route)' in text,
            'R92 wrapper prebuild/source-test boundary omitted')
    require(all(x not in text for x in ('runner.build_targets(', 'aquery', 'cquery',
                                       "bazel + ['build']", 'collect_outputs(', 'finalize(')),
            'Compilation/collection must not run in source preparation')
    return selected


def prepare(boundary, args, reports, status):
    """Return the exact checked runtime helpers plus prepared workspace context."""
    repo = Path(args.repo_root).resolve()
    engine = boundary.engine
    data = (repo / 'r88-build-route/build_fg_policy.py').read_bytes()
    body = preparation_statements(data)
    # Do not patch the frozen file or its checked target contract. R92's own
    # wrapper still applies/checks/tests every inherited production source.
    boundary.install()
    scope = dict(engine.__dict__)
    scope.update(args=args, repo=repo, reports=reports, status=status,
                 status_path=reports / 'r94-source-preparation-status.json',
                 route=repo / 'r88-build-route')
    for key in ('workspace', 'package', 'baseline', 'r18'):
        scope['root' if key == 'workspace' else key] = Path(getattr(args, key)).resolve()
    module = ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
    exec(compile(module, 'sha-pinned-r92-source-preparation', 'exec'), scope, scope)
    require(boundary.applied and boundary.parent.verify_calls == 1,
            'Exactly one successful R92 preparation boundary required')
    return scope
