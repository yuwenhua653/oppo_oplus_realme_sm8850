#!/usr/bin/env python3
"""Host-only simulations: exact helper with absolute Android paths sandboxed.
This does not emulate a kernel, firmware load, Android SELinux, or target toybox.
"""
import hashlib, json, os, pathlib, re, subprocess, tempfile, time
HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE / 'late-dsp-start.sh'
TOYBOX = '''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
args=sys.argv[1:]; cfg=json.loads(pathlib.Path(os.environ['MOCK_CONFIG']).read_text())
if args[0]=='timeout':
    if cfg.get('timeout_unavailable'): sys.exit(127)
    # Run the exact timed child; the state-file write is an ordinary host file.
    rc=subprocess.run(['/usr/bin/timeout']+args[1:]).returncode
    if 'r55-dsp-write' in args:
        p=pathlib.Path(args[-1]); after=p.read_text().strip()
        with open(os.environ['MOCK_WRITES'],'a') as f:
            f.write(json.dumps({'path':str(p),'state_after_child':after,'rc':rc})+'\\n')
        if after=='start' and cfg.get('state_on_success',True): p.write_text('running\\n')
    sys.exit(rc)
if args[0] in ['cat','readlink','tr','true']:
    os.execv('/usr/bin/'+args[0], ['/usr/bin/'+args[0]]+args[1:])
sys.exit(127)
'''

def run_case(name, cfg):
    with tempfile.TemporaryDirectory(prefix='r55-late-dsp-') as tmp:
        root=pathlib.Path(tmp); fs=root/'android'; fs.mkdir()
        toy=root/'toybox'; toy.write_text(TOYBOX); toy.chmod(0o755)
        config=root/'config.json'; config.write_text(json.dumps(cfg)); writes=root/'writes.jsonl'; writes.touch()
        props={'init.svc.ueventd':'running','ro.cold_boot_done':'true'}; props.update(cfg.get('properties',{}))
        fallback=fs/'proc/sys/kernel/firmware_config/force_sysfs_fallback'; fallback.parent.mkdir(parents=True); fallback.write_text(str(cfg.get('fallback',1))+'\n')
        targets={'adsp':('3000000.remoteproc-adsp','remoteproc-adsp@03000000',7), 'cdsp':('32300000.remoteproc-cdsp','remoteproc-cdsp@32300000',3)}
        for target,(platform,of_name,index) in targets.items():
            parent=fs/'sys/devices/platform/soc'/platform; node=parent/'remoteproc'/f'remoteproc{index}'; node.mkdir(parents=True)
            of=fs/'sys/firmware/devicetree/base/soc'/of_name; of.mkdir(parents=True)
            (of/'compatible').write_bytes(f'qcom,canoe-{target}-pas\0'.encode()); (parent/'of_node').symlink_to(of)
            cls=fs/'sys/class/remoteproc'; cls.mkdir(parents=True,exist_ok=True); (cls/f'remoteproc{index}').symlink_to(node)
            (node/'name').write_text(platform+'\n'); (node/'firmware').write_text(target+'.mdt\n'); (node/'state').write_text('offline\n')
            for suffix in ['.mdt','_dtb.mdt']:
                filename=target+suffix
                if filename in cfg.get('missing',[]): continue
                directory=cfg.get('firmware_dirs',{}).get(filename,'/vendor/firmware_mnt/image')
                path=fs/directory.lstrip('/')/filename; path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(b'' if filename in cfg.get('empty',[]) else b'mock MDT only\n')
        snippet=SOURCE.read_text().replace('/vendor/bin/sh','/bin/sh')
        # Longest prefixes first; all replacements confined to this test copy.
        snippet=re.sub(r'(?<![A-Za-z0-9_/])/(?:sys|proc|vendor|etc|odm|firmware)(?=/)',lambda m:str(fs)+m.group(0),snippet)
        wrapper='set -u\nTIMEOUT='+str(toy)+'\ngetprop() {\n case "$1" in\n'
        wrapper+=''.join(f' {key}) printf "%s\\n" "{value}" ;;\n' for key,value in props.items())
        wrapper+=' esac\n}\nsleep() { /usr/bin/sleep 0.02; }\nsay() { printf "%s\\n" "$*"; }\n'
        script=root/'run.sh'; script.write_text(wrapper+snippet)
        env=dict(os.environ,MOCK_CONFIG=str(config),MOCK_WRITES=str(writes))
        start=time.monotonic(); result=subprocess.run(['/bin/dash',str(script)],env=env,text=True,capture_output=True,timeout=15)
        elapsed=time.monotonic()-start
        events=[json.loads(x) for x in writes.read_text().splitlines()]
        outcome={'name':name,'shell_exit':result.returncode,'elapsed_seconds':round(elapsed,3),'writes':events,'stdout':result.stdout,'stderr':result.stderr}
        assert result.returncode==0, outcome
        assert len(events)==cfg['expected_writes'], outcome
        for marker in cfg['expected_markers']: assert marker in result.stdout, (marker,outcome)
        if cfg['expected_writes']==0: assert 'event=START_ONCE' not in result.stdout,outcome
        outcome['status']='PASS'; return outcome

CASES=[
 ('both_offline_mounted_firmware',{'expected_writes':2,'expected_markers':['target=adsp event=RUNNING','target=cdsp event=RUNNING']}),
 ('stock_search_paths_per_file',{'firmware_dirs':{'adsp.mdt':'/vendor/vm-system','adsp_dtb.mdt':'/etc/firmware','cdsp.mdt':'/odm/firmware','cdsp_dtb.mdt':'/vendor/modem_firmware/image'},'expected_writes':2,'expected_markers':['target=adsp event=RUNNING','target=cdsp event=RUNNING']}),
 ('fallback_zero',{'fallback':0,'expected_writes':0,'expected_markers':['target=adsp event=NOT_READY','target=cdsp event=NOT_READY']}),
 ('ueventd_stopped',{'properties':{'init.svc.ueventd':'stopped'},'expected_writes':0,'expected_markers':['target=adsp event=NOT_READY','target=cdsp event=NOT_READY']}),
 ('coldboot_false',{'properties':{'ro.cold_boot_done':'false'},'expected_writes':0,'expected_markers':['target=adsp event=NOT_READY','target=cdsp event=NOT_READY']}),
 ('adsp_dtb_missing_cdsp_independent',{'missing':['adsp_dtb.mdt'],'expected_writes':1,'expected_markers':['target=adsp event=NOT_READY','target=cdsp event=RUNNING']}),
 ('adsp_mdt_empty_cdsp_independent',{'empty':['adsp.mdt'],'expected_writes':1,'expected_markers':['target=adsp event=NOT_READY','target=cdsp event=RUNNING']}),
 ('writer_zero_without_running_unconfirmed',{'state_on_success':False,'expected_writes':2,'expected_markers':['target=adsp event=START_UNCONFIRMED','target=cdsp event=START_UNCONFIRMED']}),
 ('timeout_unavailable_fails_closed',{'timeout_unavailable':True,'expected_writes':0,'expected_markers':['target=all event=TOOL_UNAVAILABLE','helper_failed; selected module readiness retained']}),
]
if __name__=='__main__':
    results=[run_case(name,cfg) for name,cfg in CASES]
    out={'schema':1,'status':'PASS','tests_passed':len(results),'helper_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256((HERE/'load-modules.sh').read_bytes()).hexdigest(),'scope':'Host dash simulations with redirected absolute paths, mock property values and mock successful remoteproc state transitions; production source untouched. This is not device or firmware validation.','results':results}
    (HERE/'readiness-tests.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k!='results'},indent=2))
