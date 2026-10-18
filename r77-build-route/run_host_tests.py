#!/usr/bin/env python3
"""Test only the new observer; unchanged suites retain their pinned R76 evidence."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from thermal_inputs import check, parents, SOURCE

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path)
    p.add_argument('--reports',required=True,type=Path);args=p.parse_args();root=args.root.resolve();reports=args.reports.resolve()
    c=json.loads((root/'r77-build-route/thermal-contract.json').read_text());check(root,c)
    _,checker,_,_=parents(root);output=reports/'r77-host-observer'
    checker.require(not output.exists(),'Fresh observer test output required');reports.mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,str(root/'r77-build-route/tests/run_tests.py'),'--source',str(root/SOURCE),'--output',str(output)]
    result=subprocess.run(cmd,cwd=root,text=True,capture_output=True)
    (reports/'r77-host-observer.log').write_text(result.stdout+result.stderr)
    checker.require(result.returncode==0,'Actual production observer host tests failed')
    report=json.loads((output/'RESULT.json').read_text())
    checker.require(report.get('status')=='PASS' and report.get('source_sha256')==checker.sha((root/SOURCE).read_bytes()),'Observer test not bound to compiled source')
    summary={'status':'PASS','compile_only':True,'hardware_tested':False,'source_sha256':report['source_sha256'],
             'unchanged_R75_R76_host_suites_rerun':False,'new_suite':'observer'}
    (reports/'r77-host-tests.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
