#!/usr/bin/env python3
"""Reuse pinned R75 suites and test the exact new transport/control sources."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from foundation_inputs import check, parent_modules, PARENT, STEMS

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,type=Path);parser.add_argument('--reports',required=True,type=Path)
    args=parser.parse_args();root=args.root.resolve();reports=args.reports.resolve()
    contract=json.loads((root/'r76-build-route/foundation-contract.json').read_text());check(root,contract)
    checker,_=parent_modules(root);require,sha=checker.require,checker.sha
    parent=json.loads((root/PARENT).read_text());reports.mkdir(parents=True,exist_ok=True)
    tests=parent['host_tests']+[{'name':'mca_transport','script':'r76-build-route/tests/mca_transport/run_tests.py',
        'source':'r76-build-route/payload/'+STEMS['mca_adsp_glink']+'.c',
        'header':'r75-build-route/payload/include/linux/soc/qcom/qti_pmic_glink.h','result_file':'RESULT.json'}]
    results=[]
    for row in tests:
        output=reports/('r76-host-'+row['name']);require(not output.exists(),'Fresh test output required')
        cmd=[sys.executable,str(root/row['script']),'--source',str(root/row['source']),'--output',str(output)]
        if row.get('header'):cmd+=['--header',str(root/row['header'])]
        run=subprocess.run(cmd,cwd=root,text=True,capture_output=True)
        (reports/('r76-host-'+row['name']+'.log')).write_text(run.stdout+run.stderr)
        require(run.returncode==0,'Host source test failed: '+row['name'])
        result=json.loads((output/'RESULT.json').read_text());require(result.get('status')=='PASS','Host test not PASS')
        require(result.get('source_sha256')==sha((root/row['source']).read_bytes()),'Test source not compiled source')
        if row.get('header'):
            key='public_header_sha256' if row['name']=='client' else 'header_sha256'
            require(result.get(key)==sha((root/row['header']).read_bytes()),'Test header not compiled header')
        results.append({'name':row['name'],'status':'PASS','source_sha256':result['source_sha256']})
    output=reports/'r76-host-control';require(not output.exists(),'Fresh control output required');output.mkdir()
    cmd=[sys.executable,str(root/'r76-build-route/tests/control/run_extracted_tests.py'),
         '--source-root',str(root/'r76-build-route/payload'),'--report',str(output/'RESULT.json')]
    run=subprocess.run(cmd,cwd=root,text=True,capture_output=True)
    (reports/'r76-host-control.log').write_text(run.stdout+run.stderr)
    require(run.returncode==0,'Actual control function tests failed')
    result=json.loads((output/'RESULT.json').read_text());require(result.get('pass') is True,'Control tests not PASS')
    expected={STEMS[n]+'.c':contract_row['after_sha256'] for n in ('mca_qcom_subpmic_proxy','mca_strategy_buckchg')
              for contract_row in contract['writes'] if contract_row['source']=='r76-build-route/payload/'+STEMS[n]+'.c'}
    require({r['path']:r['sha256'] for r in result['source_files']}==expected,'Control test production source pins differ')
    results.append({'name':'control','status':'PASS','sources':expected})
    summary={'status':'PASS','compile_only':True,'hardware_tested':False,'suites':results}
    (reports/'r76-host-tests.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
