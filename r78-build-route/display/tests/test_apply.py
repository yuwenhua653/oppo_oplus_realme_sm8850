#!/usr/bin/env python3
import hashlib,importlib.util,json,pathlib,tempfile
root=pathlib.Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('display_apply',root/'apply.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
contract=m.check(root)['contract']
with tempfile.TemporaryDirectory(prefix='r78-display-apply-') as temp:
 workspace=pathlib.Path(temp)
 for row in contract['writes']:
  if row['before_sha256'] is not None:
   p=workspace/row['destination'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((root/'preimage'/row['path']).read_bytes())
 target=workspace/contract['writes'][0]['destination'];original=target.read_bytes();target.write_bytes(b'unknown')
 before={str(p.relative_to(workspace)):hashlib.sha256(p.read_bytes()).hexdigest() for p in workspace.rglob('*') if p.is_file()}
 try:m.apply(workspace,root)
 except ValueError:pass
 else:raise AssertionError('unknown preimage accepted')
 after={str(p.relative_to(workspace)):hashlib.sha256(p.read_bytes()).hexdigest() for p in workspace.rglob('*') if p.is_file()}
 assert before==after,'failed preflight changed workspace'
 target.write_bytes(original);assert len(m.apply(workspace,root)['written'])==12
 assert not m.apply(workspace,root)['written'];assert m.apply(workspace,root,True)['verified']
 for row in contract['writes']:
  if row.get('r28_sha256'):(workspace/row['destination']).write_bytes((root/'r28-effective'/row['path']).read_bytes())
 assert len(m.apply(workspace,root)['written'])==1 # only dsi_display differs from exact R28
 m.apply(workspace,root,True)
 print('PASS: all-preimage failure leaves zero writes, raw->R78, idempotence, R28->R78, full verify')
