#!/usr/bin/env python3
"""Bind exact requested targets to real DDK KO and symvers outputs before build."""
from pathlib import PurePosixPath

def require(ok,message):
    if not ok: raise ValueError(message)

def resolve(graph,module):
    fragments={str(r['id']):r for r in graph.get('pathFragments',[])}
    cache={}
    def path(key,seen=None):
        key=str(key)
        if key in cache:return cache[key]
        seen=set() if seen is None else seen
        require(key in fragments and key not in seen,'Invalid action path fragment');seen.add(key)
        r=fragments[key];parent=str(r.get('parentId','0'))
        out=(path(parent,seen)+'/' if parent not in ('','0') else '')+r['label'];seen.remove(key);cache[key]=out;return out
    artifacts={str(r['id']):r.get('execPath') or path(r['pathFragmentId']) for r in graph.get('artifacts',[])}
    targets={str(r['id']):r['label'] for r in graph.get('targets',[])}
    owned=[a for a in graph.get('actions',[]) if targets.get(str(a.get('targetId')))==module['target']]
    declared={artifacts[str(i)] for a in owned for i in a.get('outputIds',[])}
    kos=[p for p in declared if PurePosixPath(p).name==module['module_name']+'.ko']
    symvers=[p for p in declared if p.endswith('_Module.symvers')]
    require(len(kos)==1 and len(symvers)==1,'Target must declare exactly one final KO and one Module.symvers: '+module['target'])
    for p in kos+symvers:
        q=PurePosixPath(p)
        require(not q.is_absolute() and '..' not in q.parts and p.startswith('bazel-out/'),'Unsafe actual build output')
    return dict(module,output=kos[0],symvers=symvers[0])
