#!/usr/bin/env python3
"""R75 bounded wall-charger observation. Reads the boot-started R75 GET cache; never loads/restarts modules."""
import argparse,datetime as dt,json,re,shlex,signal,sys,time,uuid,zipfile
from pathlib import Path
from r75_common import *
from r75_recorder_pins import SCRIPT_LOCK_SHA256
import mca_cache
import core_capture
import mca_diagnostics
ROOT=Path(__file__).resolve().parent
TOKEN_RE=re.compile(r'[0-9a-f]{32}')
SCRIPTS=('snapshot.sh','recorder.sh','foreground.sh')
REMOTE_FILES={'claim':4096,'status':8192,'periodic.log':2000000,'launcher.log':65536,'capability.txt':1024,'capability.stderr':4096}

def remote_dir(token):
 if not isinstance(token,str) or not TOKEN_RE.fullmatch(token):raise Stop('Invalid run token')
 return '/data/local/tmp/r75-charge-'+token

def load_lock(root):
 p=root/'SCRIPT-LOCK.json'
 if not SHA_RE.fullmatch(SCRIPT_LOCK_SHA256) or sha(p)!=SCRIPT_LOCK_SHA256:raise Stop('Fixed-script lock mismatch')
 m=json.loads(p.read_text(encoding='utf-8'))
 if set(m.get('files',{}))!=set(SCRIPTS):raise Stop('Unexpected script list')
 for name,x in m['files'].items():
  p=root/name
  if p.is_symlink() or not p.is_file() or p.stat().st_size!=x.get('bytes') or sha(p)!=x.get('sha256'):raise Stop('Fixed script changed: '+name)
 return m['files']

def adb_serial(run,adb,requested=None):
 if requested and not SERIAL_RE.fullmatch(requested):raise Stop('Invalid serial')
 result=run.must('adb-devices',[adb,'devices'],8,65536);rows=[]
 for line in result['stdout'].splitlines():
  if not line.strip() or line.startswith('List of devices attached'):continue
  parts=line.split()
  if len(parts)!=2 or not SERIAL_RE.fullmatch(parts[0]):raise Stop('Ambiguous ADB devices output')
  rows.append(parts)
 if len(rows)!=1 or rows[0][1]!='device':raise Stop('仅连接一台已授权设备；离线、多设备或未授权时停止。')
 if requested and requested!=rows[0][0]:raise Stop('Device serial differs from this run')
 return rows[0][0]

def current(run,adb,serial,boot,label,body,seconds=8,limit=1048576):
 r=run.run(label,[adb,'-s',serial,'shell',shell_guard(body,boot,seconds)],seconds+3,limit)
 if r.get('returncode') in (88,89) or re.search(r'^R75_BOOT_(?:CHANGED|UNAVAILABLE)$',r.get('stderr',''),re.M):raise Stop('Boot changed/unavailable; stopped without relaunch')
 return r

def identity(run,adb,serial):
 d=kv(run.must('identity',[adb,'-s',serial,'shell',bounded_shell(IDENTITY,5)],8,65536)['stdout']);check_identity(d)
 texts=[]
 for label,cmd,cap in [('native-probe','head -c 1048576 /vendor_dlkm/r36-report/probe.log',1048576),('native-dmesg','dmesg',4194304)]:
  r=current(run,adb,serial,d['boot_id'],label,cmd,8,cap)
  if r['ok']:texts.append(r['stdout'])
 if native_build('\n'.join(texts),d['boot_id'])!=[TEST_BUILD]:raise Stop('同启动 R75 标记未验证；不启动记录。')
 return d

def load_receipt(root,arg=None):
 runs=(root/'runs').resolve()
 if arg:p=Path(arg).resolve()
 else:
  pointer=json.loads((runs/'last-run.json').read_text(encoding='utf-8'));p=runs/pointer.get('token','')/'receipt.json'
 p=p.resolve()
 if p.name!='receipt.json' or p.parent.parent!=runs or not TOKEN_RE.fullmatch(p.parent.name):raise Stop('Receipt must be runs/<token>/receipt.json inside this package')
 d=json.loads(p.read_text(encoding='utf-8'))
 if d.get('schema')!=1 or d.get('token')!=p.parent.name or d.get('remote_directory')!=remote_dir(d.get('token')):raise Stop('Invalid receipt token/path')
 if not SERIAL_RE.fullmatch(d.get('serial','')) or not BOOT_RE.fullmatch(d.get('boot_id','')):raise Stop('Invalid receipt identity')
 if d.get('product')!=PRODUCT or d.get('kernel')!=KERNEL or d.get('native_build')!=TEST_BUILD:raise Stop('Receipt build mismatch')
 if d.get('package_manifest_sha256')!=sha(root/'r75-package.json') or not SHA_RE.fullmatch(NATIVE_SHA or '') or d.get('native_contract_sha256')!=NATIVE_SHA:raise Stop('Receipt image/native package pins changed')
 if d.get('script_lock_sha256')!=SCRIPT_LOCK_SHA256 or set(d.get('scripts',{}))!=set(SCRIPTS):raise Stop('Receipt script contract mismatch')
 if d.get('scripts')!=load_lock(root):raise Stop('Receipt script hashes changed')
 if not isinstance(d.get('launch_attempted'),bool):raise Stop('Missing receipt launch state')
 if d.get('slot') not in ('_a','_b'):raise Stop('Invalid receipt slot')
 allowed=('launch_unknown','recording_confirmed','complete','boot_changed') if d['launch_attempted'] else ('prepared',)
 if d.get('state') not in allowed:raise Stop('Invalid receipt state')
 return p,d

def validate_status(text,receipt):
 d=kv(text)
 expected={'protocol':'1','token':receipt['token'],'boot_id':receipt['boot_id'],'recorder_sha256':receipt['scripts']['recorder.sh']['sha256'],'snapshot_sha256':receipt['scripts']['snapshot.sh']['sha256']}
 if any(d.get(k)!=v for k,v in expected.items()):raise Stop('Recorder identity/hash mismatch')
 if d.get('state') not in ('recording','complete','boot_unavailable','boot_changed','clock_unavailable'):raise Stop('Recorder state missing/invalid')
 for field in ('rounds','start_uptime_seconds','last_uptime_seconds'):
  if not re.fullmatch(r'[0-9]+',d.get(field,'')):raise Stop('Invalid recorder clock/count')
 if not 0<=int(d['rounds'])<=75 or int(d['last_uptime_seconds'])<int(d['start_uptime_seconds']):raise Stop('Recorder clock/count outside bounds')
 if d['state']=='complete' and int(d['rounds'])<1:raise Stop('Empty recorder completion')
 if int(d['last_uptime_seconds'])-int(d['start_uptime_seconds'])>180:raise Stop('Recorder elapsed time exceeds contract')
 return d

def remote_status(run,adb,receipt):
 path=remote_dir(receipt['token'])+'/status';q=shlex.quote(path)
 r=current(run,adb,receipt['serial'],receipt['boot_id'],'recorder-status','[ -d '+shlex.quote(remote_dir(receipt['token']))+' ] && [ ! -L '+shlex.quote(remote_dir(receipt['token']))+' ] && [ -f '+q+' ] && [ ! -L '+q+' ] && head -c 8192 '+q,4,16384)
 return validate_status(r['stdout'],receipt) if r['ok'] else None

def parse_meta(text,path,limit):
 sizes=re.findall(r'^SIZE=([0-9]+)$',text,re.M);hashes=re.findall(r'^([0-9a-f]{64})\s+'+re.escape(path)+r'$',text,re.M)
 if len(sizes)!=1 or len(hashes)!=1 or not 0<=int(sizes[0])<=limit:raise Stop('Remote file missing metadata/oversize')
 return {'bytes':int(sizes[0]),'sha256':hashes[0]}

def collect_file(run,adb,serial,folder,name,limit,receipt):
 if name not in REMOTE_FILES or limit!=REMOTE_FILES[name]:raise Stop('Remote filename/limit outside allowlist')
 directory=remote_dir(receipt['token']);path=directory+'/'+name;q=shlex.quote(path);qd=shlex.quote(directory)
 result={'remote_path':path,'limit_bytes':limit,'status':'unavailable'}
 body='[ -d '+qd+' ] && [ ! -L '+qd+' ] || exit 45; [ -e '+q+' ] || exit 44; [ -f '+q+' ] && [ ! -L '+q+' ] && [ -r '+q+' ] || exit 45; stat -c SIZE=%s '+q+' && sha256sum '+q
 def meta(suffix):return current(run,adb,serial,receipt['boot_id'],'pull-'+name.replace('.','-')+'-'+suffix,body,4,16384)
 first=meta('before')
 if not first['ok']:
  result['status']='missing' if first.get('returncode')==44 else 'unavailable';return result
 try:before=parse_meta(first['stdout'],path,limit)
 except Stop as e:result['reason']=str(e);return result
 dest=folder/name
 pull=run.run('pull-'+name.replace('.','-'),[adb,'-s',serial,'pull',path,str(dest.resolve())],12,65536,extra=((dest,limit),))
 after_raw=meta('after');result['remote_before']=before
 try:after=parse_meta(after_raw['stdout'],path,limit) if after_raw['ok'] else None
 except Stop:after=None
 result['remote_after']=after
 if dest.is_file():result.update(local_file=name,bytes=dest.stat().st_size,sha256=sha(dest))
 result['status']='verified' if pull['ok'] and before==after and result.get('bytes')==before['bytes'] and result.get('sha256')==before['sha256'] else 'partial_or_changed'
 return result

def foreground(run,adb,receipt,root,context,metadata_only=False):
 # Fixed source text, hash verified before start/resume; never arbitrary user command.
 boot=receipt['boot_id'];serial=receipt['serial']
 commands=[
  ('owners-dt',(root/'foreground.sh').read_text(encoding='utf-8'),20,524288),
  ('snapshot',(root/'snapshot.sh').read_text(encoding='utf-8').replace('token=$1','token='+receipt['token'],1).replace('expected_boot=$2','expected_boot='+boot,1),12,262144),
  ('mca-claim','head -c 4096 /vendor_dlkm/r36-report/r75-mca.claim',5,8192),
  ('mca-status','head -c 16384 /vendor_dlkm/r36-report/r75-mca.status',5,32768),
  ('mca-log','head -c 65536 /vendor_dlkm/r36-report/r75-mca.log',5,131072),
  ('qti-loaded-note','od -An -tx1 -v -N 256 /sys/module/qti_pmic_glink/notes/.note.gnu.build-id',5,4096),
  ('native-claim','head -c 4096 /vendor_dlkm/r36-report/r70-gauge.claim',5,8192),
  ('native-status','head -c 16384 /vendor_dlkm/r36-report/r70-gauge.status',5,32768),
  ('native-samples','head -c 16384 /vendor_dlkm/r36-report/r70-gauge.samples',5,32768),
  ('native-log','head -c 262144 /vendor_dlkm/r36-report/r70-gauge.log',5,524288),
  ('battery','dumpsys battery',8,1048576),('health','dumpsys android.hardware.health.IHealth/default',8,1048576),
  ('usb','dumpsys usb',8,1048576),('modules','cat /proc/modules',5,131072),
  ('logcat','logcat -b all -d -v threadtime',20,8388608),('dmesg','dmesg',8,4194304)]
 if metadata_only:commands=[x for x in commands if x[0] in ('owners-dt','dmesg','logcat')]
 for label,body,seconds,cap in commands:
  current(run,adb,serial,boot,context+'-'+label,body,seconds,cap)

def wait_android(run,adb,serial,seconds=120):
 # Only read-only polling after a confirmed flash+reboot ACK. No adb root/reboot.
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  r=run.run('wait-adb',[adb,'devices'],5,65536)
  rows=[]
  for line in r['stdout'].splitlines():
   if not line.strip() or line.startswith('List of devices attached'):continue
   row=line.split()
   if len(row)!=2 or not SERIAL_RE.fullmatch(row[0]):raise Stop('Ambiguous ADB wait output')
   rows.append(row)
  if rows and (len(rows)!=1 or rows[0][0]!=serial):raise Stop('Unexpected device during Android startup wait')
  if rows and rows[0][1]=='unauthorized':raise Stop('USB debugging is not authorized; preserve partial and use COLLECT after authorization')
  if rows and rows[0][1]=='device':
   r=run.run('wait-identity',[adb,'-s',serial,'shell',bounded_shell(IDENTITY,5)],8,65536)
   if r['ok']:
    d=kv(r['stdout']);check_identity(d)
    if d.get('boot_completed')=='1' and d.get('modules_ready')=='1':return
  time.sleep(1)
 raise Stop('Android startup wait expired; no reboot/reflash/reload attempted. Restore remains available independently.')

def cache_text(text):
 matches=re.findall(r'^MCA_CACHE_BEGIN\r?\n(.*?)^MCA_CACHE_READ_RC=0\r?\nMCA_CACHE_END\r?$',text,re.M|re.S)
 if len(matches)!=1:raise Stop('Verified MCA cache unavailable or read failed')
 return matches[0]

def read_window(run,adb,receipt,root,label):
 script=(root/'snapshot.sh').read_text(encoding='utf-8').replace('token=$1','token='+receipt['token'],1).replace('expected_boot=$2','expected_boot='+receipt['boot_id'],1)
 r=current(run,adb,receipt['serial'],receipt['boot_id'],label,script,12,262144)
 if not r['ok']:raise Stop('Bounded snapshot failed')
 snap=mca_cache.parse_snapshot(cache_text(r['stdout']))
 times=re.findall(r'^SNAPSHOT_END token='+re.escape(receipt['token'])+' boot_id='+re.escape(receipt['boot_id'])+r' uptime=([0-9]+(?:\.[0-9]+)?) ',r['stdout'],re.M)
 if len(times)!=1:raise Stop('Device snapshot BOOTTIME unavailable')
 return snap,mca_cache.window(snap,times[0])

def mca_preflight(run,adb,receipt,root,report):
 c=json.loads((root/'native-contract.json').read_text(encoding='utf-8'))
 r=current(run,adb,receipt['serial'],receipt['boot_id'],'mca-modules-before','cat /proc/modules',5,131072)
 if not r['ok']:raise Stop('Module inventory unavailable')
 report['mca_module_state']=mca_cache.module_set(r['stdout'],c['runtime_module_names'])
 r=current(run,adb,receipt['serial'],receipt['boot_id'],'mca-helper-status','head -c 16384 /vendor_dlkm/r36-report/r75-mca.status',5,32768)
 if r['ok']:
  status=kv(r['stdout']);report['mca_native_status']=status
 else:status={}
 expected={'protocol':'1','helper':TEST_BUILD,'status':'complete','boot_id':receipt['boot_id'],'kernel':KERNEL,'contract_sha256':NATIVE_SHA,'stage':'complete','errno':'0','baseline_verified':'247','files_verified':'1','insert_returned_success':'1','parameter':'enable_readonly=1 enable_power_supply=1 enable_extra_diagnostics=1','parameter_verified':'1','bound':'1','worker_budget_ms':'10000','usb_identity_verified':'1','telemetry_live':'not_asserted','completion_scope':'module_binding_and_usb_interface_identity_only'}
 if report['mca_module_state']!='get248' or any(status.get(k)!=v for k,v in expected.items()):
  report['mca_window']={'eligible':False,'reason':'loader_failed_partial_or_unverified'}
  raise Stop('GET loader not verified complete; keeping native failure evidence; no retry or reload')
 r=current(run,adb,receipt['serial'],receipt['boot_id'],'gauge-helper-status','head -c 16384 /vendor_dlkm/r36-report/r70-gauge.status',5,32768)
 gauge=kv(r['stdout']) if r['ok'] else {};report['gauge_native_status']=gauge
 expected_gauge={'protocol':'2','helper':TEST_BUILD,'status':'complete','boot_id':receipt['boot_id'],'kernel':KERNEL,'contract_sha256':c['gauge_native_contract_sha256'],'stage':'complete','errno':'0','baseline_verified':'246','files_verified':'1','insert_returned_success':'1','parameter':'enable_readonly=1 enable_extended_readonly=1 enable_status_readonly=1','parameter_verified':'1','extended_parameter_verified':'1','status_parameter_verified':'1','bound':'1','base_samples_ok':'1','extended_samples_ok':'1','telemetry_power_supply':'1'}
 if any(gauge.get(k)!=v for k,v in expected_gauge.items()):
  report['mca_window']={'eligible':False,'reason':'gauge_status_forwarding_loader_unverified'}
  raise Stop('R75 gauge status forwarding not verified; keeping evidence without retry/reload')
 snap,decision=read_window(run,adb,receipt,root,'pc-before-snapshot')
 report['mca_initial_snapshot']=snap;report['mca_window']=decision
 if not decision['eligible']:raise Stop('GET sampling window unavailable: '+decision['reason']+'; collecting existing evidence only')

def mca_periodic(folder):
 result={'frames':[],'valid_frames':0,'errors':[]}
 p=folder/'periodic.log'
 if not p.is_file():result['errors'].append('periodic unavailable');return result
 text=p.read_text(encoding='utf-8',errors='replace')
 for ordinal,frame in enumerate(re.split(r'^ROUND=[0-9]+\n',text,flags=re.M)[1:],1):
  try:
   snap=mca_cache.parse_snapshot(cache_text(frame))
   result['frames'].append({'recorder_round':ordinal,**snap})
   result['valid_frames']+=1
   if snap['has_sample_errors']:result['errors'].append('GET error/not-attempted in recorder round '+str(ordinal))
  except Stop as e:result['errors'].append('recorder round '+str(ordinal)+': '+str(e))
 return result

def reporting_periodic(folder):
 """Preserve published values and read errors; never decode raw MCA into status."""
 result={'frames':[],'read_issues':[],'interpretation':'Sequential cached USB properties and independent battery readings; no automatic charging verdict'}
 p=folder/'periodic.log'
 if not p.is_file():return result
 selected={'/sys/class/power_supply/usb/'+name for name in ('type','model_name','online','status','voltage_now','current_now')}
 selected.update('/sys/class/power_supply/battery/'+name for name in ('status','health','capacity','voltage_now','current_now'))
 for ordinal,frame in enumerate(re.split(r'^ROUND=[0-9]+\n',p.read_text(encoding='utf-8',errors='replace'),flags=re.M)[1:],1):
  observed={}
  for block in re.split(r'^PATH=',frame,flags=re.M)[1:]:
   path=block.splitlines()[0]
   if path not in selected:continue
   if path in observed:
    result['read_issues'].append({'recorder_round':ordinal,'path':path,'error':'duplicate_path'});continue
   match=re.match(r'[^\n]+\nEXISTS=([01])\n(.*?)\nREAD_RC=([0-9]+)(?:\n|$)',block,re.S)
   if not match:
    result['read_issues'].append({'recorder_round':ordinal,'path':path,'error':'missing_read_result'});continue
   rc=int(match[3]);raw=match[2].strip()
   timing=re.match(r'READ_TIMING_END path='+re.escape(path)+r' clock=BOOTTIME uptime=('+core_capture.CLOCK+r') rc='+str(rc)+r' truncated=([01])(?:\n|$)',block[match.end():])
   valid=bool(match[1]=='1' and rc==0 and timing and timing[2]=='0' and core_capture.scalar_valid(path,raw))
   observed[path]={'exists':match[1]=='1','read_rc':rc,'raw_text':raw,'value':raw if valid else None,'end_timing_verified':bool(timing),'truncated':timing[2]=='1' if timing else None}
   if not valid:result['read_issues'].append({'recorder_round':ordinal,'path':path,'error':'read_failed_truncated_or_invalid','read_rc':rc})
  for path in sorted(selected-set(observed)):
   result['read_issues'].append({'recorder_round':ordinal,'path':path,'error':'not_read_or_owner_not_verified'})
  result['frames'].append({'recorder_round':ordinal,'properties':observed})
 return result

def setup_and_launch(run,adb,receipt,receipt_path,root):
 serial=receipt['serial'];boot=receipt['boot_id'];directory=remote_dir(receipt['token']);q=shlex.quote(directory)
 def must(label,body,seconds=8,limit=65536):
  r=current(run,adb,serial,boot,label,body,seconds,limit)
  if not r['ok']:raise Stop(label+' failed; no retry')
  return r
 must('create-run','[ ! -e '+q+' ] && [ ! -L '+q+' ] && (umask 077; mkdir '+q+')')
 for name in SCRIPTS:
  run.must('push-'+name.replace('.','-'),[adb,'-s',serial,'push',str(root/name),directory+'/'+name],8,65536)
  remote=directory+'/'+name;qr=shlex.quote(remote)
  r=must('verify-'+name.replace('.','-'),'[ -f '+qr+' ] && [ ! -L '+qr+' ] && stat -c SIZE=%s '+qr+' && sha256sum '+qr)
  if parse_meta(r['stdout'],remote,100000)!=receipt['scripts'][name]:raise Stop('Remote script byte/hash mismatch')
 # Exercise all actual launch primitives, with every write in this run directory.
 token=receipt['token'];capability='R75_CAPABILITY_'+token
 inner='/system/bin/toybox timeout --foreground -k 1 1 /system/bin/sh -c '+shlex.quote('printf %s '+shlex.quote(capability))
 body='umask 077; set -C; /system/bin/toybox nohup /system/bin/toybox setsid /system/bin/toybox timeout -k 1 3 /system/bin/sh -c '+shlex.quote(inner)+' </dev/null >'+q+'/capability.txt 2>'+q+'/capability.stderr'
 must('detach-capability',body)
 for attempt in range(5):
  cap=must('capability-read','head -c 1024 '+q+'/capability.txt')
  if cap['stdout']==capability:break
  time.sleep(0.1)
 else:raise Stop('Detached launch capability not confirmed')
 receipt['launch_attempted']=True;receipt['state']='launch_unknown';atomic_json(receipt_path,receipt)
 # Mark BEFORE sending: an ADB failure may occur after the device accepted launch.
 launch='umask 077; set -C; /system/bin/toybox nohup /system/bin/toybox setsid /system/bin/toybox timeout -k 1 179 /system/bin/sh '+q+'/recorder.sh '+q+' '+shlex.quote(token)+' '+shlex.quote(boot)+' </dev/null >'+q+'/launcher.log 2>&1 &\nprintf "LAUNCH_SUBMITTED=%s\\n" '+shlex.quote(token)
 r=current(run,adb,serial,boot,'launch-once',launch,6,65536)
 if not r['ok'] or r['stdout'].strip()!='LAUNCH_SUBMITTED='+token:raise Stop('启动回执不确定；不重试。接回 USB 后使用 RESUME-R75.cmd。')
 for attempt in range(6):
  status=remote_status(run,adb,receipt)
  if status:
   if status['state']!='recording' or int(status['rounds'])>2:raise Stop('Fresh recording state not confirmed; do not disconnect USB')
   clock=must('launch-freshness','cat /proc/uptime',3,1024)['stdout'].split()
   if not clock or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',clock[0]) or not 0<=float(clock[0])-int(status['start_uptime_seconds'])<=30:raise Stop('Recording start window expired; do not disconnect USB')
   receipt['state']='recording_confirmed';receipt['start_status']=status;atomic_json(receipt_path,receipt);return status
  time.sleep(0.3)
 raise Stop('启动证据未确认；不允许拔线，也不重启记录。稍后使用 RESUME-R75.cmd。')

def periodic_check(folder,receipt,status):
 result={'complete_snapshots':False,'reason':'unavailable'}
 p=folder/'periodic.log'
 if not p.is_file():return result
 text=p.read_text(encoding='utf-8',errors='replace')
 rounds=re.findall(r'^ROUND=([0-9]+)$',text,re.M)
 begin=re.findall(r'^SNAPSHOT_BEGIN token=([^ ]+) boot_id=([^ ]+) uptime=(?:[0-9]+(?:\.[0-9]+)?) (?:[0-9]+(?:\.[0-9]+)?)$',text,re.M)
 end=re.findall(r'^SNAPSHOT_END token=([^ ]+) boot_id=([^ ]+) uptime=(?:[0-9]+(?:\.[0-9]+)?) (?:[0-9]+(?:\.[0-9]+)?)$',text,re.M)
 rc=re.findall(r'^SNAPSHOT_EXEC_RC=([0-9]+)$',text,re.M)
 n=int(status.get('rounds','0'));expected=(receipt['token'],receipt['boot_id'])
 good=1<=n<=75 and rounds==list(map(str,range(1,n+1))) and len(begin)==len(end)==len(rc)==n and all(x==expected for x in begin+end) and all(x=='0' for x in rc)
 frames=re.split(r'^ROUND=[0-9]+\n',text,flags=re.M)
 if frames[0].strip() or len(frames)!=n+1:good=False
 for frame in frames[1:]:
  starts=list(re.finditer(r'^SNAPSHOT_BEGIN token=([^ ]+) boot_id=([^ ]+) uptime=(?:[0-9]+(?:\.[0-9]+)?) (?:[0-9]+(?:\.[0-9]+)?)$',frame,re.M))
  ends=list(re.finditer(r'^SNAPSHOT_END token=([^ ]+) boot_id=([^ ]+) uptime=(?:[0-9]+(?:\.[0-9]+)?) (?:[0-9]+(?:\.[0-9]+)?)$',frame,re.M))
  exits=list(re.finditer(r'^SNAPSHOT_EXEC_RC=([0-9]+)\s*\Z',frame,re.M))
  if len(starts)!=1 or len(ends)!=1 or len(exits)!=1 or not starts[0].start()<ends[0].start()<exits[0].start():good=False
 core=core_capture.periodic(text,receipt['token'],receipt['boot_id'])
 result['complete_core_records']=core['complete_core_records']
 result['core_records_expected']=n
 good=good and len(core['frames'])==n and core['complete_core_records']==n
 result.update(complete_snapshots=good,reason='verified_boundaries' if good else 'missing_truncated_failed_or_mismatched_snapshot',round_markers=len(rounds),begins=len(begin),ends=len(end),returncodes=rc)
 # The immutable claim must describe exactly the same run and start as final status.
 try:
  claim=kv((folder/'claim').read_text(encoding='utf-8'))
  keys=('protocol','token','boot_id','recorder_sha256','snapshot_sha256','start_uptime_seconds')
  result['claim_matches_status']=all(claim.get(k)==status.get(k) for k in keys)
 except (OSError,Stop):result['claim_matches_status']=False
 return result

def archive(folder,report,run,receipt):
 old=signal.signal(signal.SIGINT,signal.SIG_IGN)
 try:
  report['commands']=run.summary();report['finished_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
  if receipt:atomic_json(folder/'receipt-copy.json',receipt)
  atomic_json(folder/'summary.json',report)
  atomic_json(folder/'file-manifest.json',{'files':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(folder.iterdir()) if p.is_file()]})
  path=folder.with_suffix('.zip')
  with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
   for p in sorted(folder.iterdir()):
    if p.is_file():z.write(p,folder.name+'/'+p.name)
  return path
 finally:signal.signal(signal.SIGINT,old)

def main(argv=None):
 for stream in (sys.stdout,sys.stderr):
  if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('mode',choices=['start','resume']);ap.add_argument('--adb');ap.add_argument('--serial');ap.add_argument('--receipt');ap.add_argument('--wait-for-boot',action='store_true');args=ap.parse_args(argv)
 stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:8]
 folder=ROOT/'results'/('r75-charge-'+stamp);folder.mkdir(parents=True,exist_ok=False);run=Runner(folder)
 report={'schema':1,'collector':'R75-READONLY-MCA-CAPTURE-20261018-01','mode':args.mode,'status':'partial','recorded_complete':False,'evidence_partial':True,'same_boot':False,'errors':[],'remote_files':{},'wall_charger_interval':'user_reported_only; periodic samples are not automatically labelled wall-charger', 'device_writes':'Collector only writes fixed recorder files in its run directory. GET client was explicitly enabled by this test image once at boot; collector never loads/restarts it.'}
 receipt=receipt_path=previous=None;halted=False
 try:
  package_manifest=load_package(ROOT);report['package_manifest_sha256']=sha(ROOT/'r75-package.json');report['native_contract_sha256']=package_manifest['native_contract_sha256']
  scripts=load_lock(ROOT)
  if args.mode=='resume':
   receipt_path,receipt=load_receipt(ROOT,args.receipt)
   if not receipt['launch_attempted']:raise Stop('此 run 未尝试启动；resume 不会创建或启动记录。')
  elif args.receipt:raise Stop('--receipt is only valid for resume')
  elif (ROOT/'runs'/'last-run.json').exists():
   _,previous=load_receipt(ROOT)
   if previous['launch_attempted'] and previous.get('state') not in ('complete','boot_changed'):
    raise Stop('已有启动或状态不确定的 run；请先用 RESUME-R75.cmd 取回，不重复启动。')
  adb=tool('adb',ROOT,args.adb)
  if args.wait_for_boot:
   if args.mode!='start' or not args.serial or not SERIAL_RE.fullmatch(args.serial):raise Stop('--wait-for-boot requires start and the verified transaction serial')
   wait_android(run,adb,args.serial)
  serial=adb_serial(run,adb,receipt['serial'] if receipt else args.serial)
  if receipt and args.serial and args.serial!=serial:raise Stop('Requested serial differs from receipt')
  before=identity(run,adb,serial);report['identity_before']=before
  if before.get('boot_completed')!='1' or before.get('modules_ready')!='1':raise Stop('Android boot/module readiness not complete; no recorder launched')
  if previous and previous['launch_attempted'] and before['boot_id']==previous['boot_id']:
   raise Stop('本次开机已启动过记录；使用 RESUME-R75.cmd 读取原记录，不重复启动。')
  if receipt:
   if before['boot_id']!=receipt['boot_id'] or before['slot']!=receipt['slot']:
    receipt['state']='boot_changed';atomic_json(receipt_path,receipt);raise Stop('Boot changed from recorded run; no old data relabelled or recorder restarted')
  else:
   token=uuid.uuid4().hex;run_dir=ROOT/'runs'/token;run_dir.mkdir(parents=True,exist_ok=False);receipt_path=run_dir/'receipt.json'
   receipt={'schema':1,'token':token,'remote_directory':remote_dir(token),'serial':serial,'boot_id':before['boot_id'],'slot':before['slot'],'product':PRODUCT,'kernel':KERNEL,'native_build':TEST_BUILD,'package_manifest_sha256':sha(ROOT/'r75-package.json'),'native_contract_sha256':package_manifest['native_contract_sha256'],'script_lock_sha256':SCRIPT_LOCK_SHA256,'scripts':scripts,'launch_attempted':False,'state':'prepared','created_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
   atomic_json(receipt_path,receipt);atomic_json(ROOT/'runs'/'last-run.json',{'token':token})
   try:mca_preflight(run,adb,receipt,ROOT,report)
   except (Stop,OSError,ValueError,KeyError):
    foreground(run,adb,receipt,ROOT,'preflight-partial')
    raise
   # Optional metadata is captured once before launch. Its errors remain evidence.
   foreground(run,adb,receipt,ROOT,'pc-before',metadata_only=True)
   setup_and_launch(run,adb,receipt,receipt_path,ROOT)
   report['launch_confirmed']=True
   snap,decision=read_window(run,adb,receipt,ROOT,'launch-window-snapshot')
   report['mca_prompt_snapshot']=snap;report['mca_prompt_window']=decision
   if not decision['eligible']:raise Stop('GET sampling window expired during recorder setup; no wall-charger prompt, no restart')
   receipt['mca_prompt_window']=decision;atomic_json(receipt_path,receipt)
   print('R75 持续状态上报已核验；缓存有效标记='+str(snap['header']['supply_valid'])+'，数据失效期限为 15 秒。未知或读取失败也会原样保留。')
   print('\n已核验同 token / 同启动的后台记录。按顺序操作：拔下电脑 USB 等 15 秒；接墙充 45 秒；拔下墙充等 15 秒；再接同一墙充 30 秒；最后接回电脑。')
   print('记录最长约 180 秒自行结束。无需开网络 ADB、重启、刷机或改充电设置。不要重复运行 COLLECT-R75.cmd。')
   receipt['wall_prompt_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
   receipt['requested_stages']=[{'stage':'unplugged','seconds':15},{'stage':'wall_connected','seconds':45},{'stage':'unplugged','seconds':15},{'stage':'same_wall_reconnected','seconds':30}]
   receipt['stage_timing_limit']='operator instructions only; per-stage actual times are not automatically asserted'
   atomic_json(receipt_path,receipt)
   input('接回电脑并确认 USB 调试可用后，按回车取回（中断可用 RESUME-R75.cmd）：')
   report['operator_reconnected_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
   adb_serial(run,adb,serial)
   after=identity(run,adb,serial)
   if after['boot_id']!=receipt['boot_id'] or after['slot']!=receipt['slot']:raise Stop('Boot changed after wall interval; stopped')
  deadline=time.monotonic()+120
  while True:
   status=remote_status(run,adb,receipt)
   if not status:raise Stop('记录状态暂不可读；保留部分包，接回后再次 RESUME，不重新启动。')
   report['recorder_status']=status
   if status['state']!='recording':break
   if time.monotonic()>=deadline:break
   print('记录仍在限时运行，正在等待；Ctrl+C 可保存部分包。')
   time.sleep(5)
  for name,limit in REMOTE_FILES.items():report['remote_files'][name]=collect_file(run,adb,serial,folder,name,limit,receipt)
  foreground(run,adb,receipt,ROOT,'pc-after')
  last=kv(run.must('identity-after',[adb,'-s',serial,'shell',bounded_shell(IDENTITY,5)],8,65536)['stdout']);check_identity(last);report['identity_after']=last
  report['same_boot']=last['boot_id']==receipt['boot_id'] and last['slot']==receipt['slot']
  if not report['same_boot']:raise Stop('Final boot/slot differs')
  if status['state']=='complete':receipt['state']='complete';atomic_json(receipt_path,receipt)
  report['periodic_validation']=periodic_check(folder,receipt,status)
  report['recorded_complete']=bool(status['state']=='complete' and report['periodic_validation']['complete_snapshots'] and report['periodic_validation'].get('claim_matches_status') and all(x['status']=='verified' for x in report['remote_files'].values()) and report['same_boot'])
  report['operator_observation']=input('可选：墙充/功率计显示、停留秒数及现象（直接回车留空，不作为自动判定）：')[:2000]
 except (OSError,ValueError,KeyError,Stop,KeyboardInterrupt,EOFError) as e:
  report['errors'].append(str(e) or 'Operator interrupted/EOF');report['recorded_complete']=False;halted=True
 finally:
  # No more device commands here: EOF/disconnect/Ctrl+C must still preserve partial evidence.
  report['read_issues']=[{'label':r['label'],'error':r.get('error'),'returncode':r.get('returncode')} for r in run.records if not r.get('ok')]
  text='\n'.join(r.get('stdout','') for r in run.records if r['label'].startswith(('pc-before-owners','pc-before-snapshot','pc-after-owners','pc-after-snapshot')))
  periodic=folder/'periodic.log'
  if periodic.is_file():text+='\n'+periodic.read_text(encoding='utf-8',errors='replace')
  report['mca_cache_validation']=mca_periodic(folder)
  report['historical_diagnostics']=mca_diagnostics.periodic(periodic.read_text(encoding='utf-8',errors='replace')) if periodic.is_file() else {'frames':[], 'read_issues':[]}
  report['published_power_supply_observations']=reporting_periodic(folder)
  report['core_capture']=core_capture.periodic(periodic.read_text(encoding='utf-8',errors='replace'),receipt['token'],receipt['boot_id']) if periodic.is_file() and receipt else {'frames':[], 'complete_core_records':0, 'valid_telemetry_frames':0, 'observed_transitions':[]}
  report['core_errors_or_missing']=bool(not report['core_capture']['frames'] or any(not f['telemetry_valid'] for f in report['core_capture']['frames']))
  metadata=[r for r in run.records if r['label'].endswith('-owners-dt')]
  report['optional_metadata']=[{'label':r['label'], 'complete':bool(r.get('ok') and core_capture.metadata_complete(r.get('stdout','')))} for r in metadata]
  report['response_timing_evidence']={'clock':'BOOTTIME', 'transitions':report['core_capture']['observed_transitions'], 'verified_physical_cable_events':[], 'hardware_event_time_available':False, 'reason':'No verified physical cable event format is currently available; original dmesg/logcat are preserved as log evidence. Transport SSR/PDR and operator instructions are not cable events.', 'system_log_commands':[{'label':r['label'],'ok':r.get('ok'),'returncode':r.get('returncode')} for r in run.records if r['label'].endswith(('-dmesg','-logcat'))]} 
  report['published_supply_errors_or_missing']=bool(report['published_power_supply_observations']['read_issues'] or not report['published_power_supply_observations']['frames'])
  report['mca_errors_or_missing']=bool(report['mca_cache_validation']['errors'] or not report['mca_cache_validation']['valid_frames'])
  report['optional_evidence_gaps']=bool(report['historical_diagnostics']['read_issues'] or any(not m['complete'] for m in report['optional_metadata']) or re.search(r'^(?:READ|READLINK|META|STAT|SELECTION|SNAPSHOT_EXEC)_RC=[1-9]|^MEASUREMENTS_SKIPPED=|_ENUM_LIMIT=|^VALUE_TRUNCATED=1$',text,re.M))
  report['evidence_partial']=bool(report['read_issues'] or report['core_errors_or_missing'] or report['optional_evidence_gaps'] or report['mca_errors_or_missing'] or report['published_supply_errors_or_missing'] or not report['recorded_complete'])
  report['status']='collected' if report['recorded_complete'] and not report['evidence_partial'] else 'partial'
  report['interpretation_limit']='UCSI voltage/current describe source negotiation/request, not measured battery net current. MCA usb current_now is cached charger-input current; battery current_now is a separate signed gauge reading. USB and battery status are recorded from the reviewed kernel reporting path, not recomputed from current or raw flags by this collector. Raw BatteryStatus and six MCA raw unsigned GET fields remain undecoded evidence; transport-valid 0xffffffff is not automatically a usable limit. A valid=0 raw_u32=0 is only a placeholder. Cache reads never send GET; six fields and sysfs attributes are sequential, not one atomic hardware reading. active=0/finished=0 means the interval between rounds. R75 reports persistently at a two-second target interval with a 15-second freshness limit; max_rounds=U32_MAX is not a remaining observation deadline. Operator unplug/replug stages are not automatically labelled wall-charger measurements. No charging success or health conclusion is generated.'
  if receipt:report['receipt']=str(receipt_path.resolve())
  try:
   path=archive(folder,report,run,receipt);print('请发送 ZIP（partial 也发送）：'+str(path.resolve()))
   if receipt and receipt.get('launch_attempted') and receipt.get('state')!='complete':print('保留整个目录。接回同一设备后双击 RESUME-R75.cmd；不要重复运行 COLLECT-R75.cmd。')
  except (OSError,ValueError) as e:print('ZIP 保存失败；原始结果保留在 '+str(folder.resolve())+'：'+str(e),file=sys.stderr);return 1
 return 0 if report['recorded_complete'] else 1
if __name__=='__main__':sys.exit(main())
