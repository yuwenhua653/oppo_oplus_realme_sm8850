"""Strict parsing of the seven-line read-only cache; raw values are never health claims."""
import re
from r75_common import Stop
PROPERTIES=(0x20001,0x20002,0x20004,0x2000c,0x2001,0x2008)
SNAPSHOT='/sys/bus/platform/devices/soc:pmic-glink:mca,adsp_glink/myron_mca_readonly/snapshot'
TARGET='/sys/bus/platform/devices/soc:pmic-glink:mca,adsp_glink'
REAL='/sys/devices/platform/soc/soc:pmic-glink/soc:pmic-glink:mca,adsp_glink'
HEADER_KEYS=set('protocol owner operation round max_rounds active finished stopping link_up requests max_requests run_start_ms run_end_ms round_start_ms round_end_ms clock initial_link_assumed firmware_reply_seen consecutive_timeouts stop_reason'.split())
REPORTING_KEYS=set('power_supply_reporting freshness_ms supply_valid generation'.split())
ITEM_KEYS=set('property seq attempted valid raw_u32 raw_hex error response_seen remote_status start_ms end_ms'.split())
def fields(line,keys):
 result={}
 for item in line.split():
  if item.count('=')!=1:raise Stop('Malformed MCA cache field')
  k,v=item.split('=')
  if k in result:raise Stop('Duplicate MCA cache field')
  result[k]=v
 if set(result)!=keys:raise Stop('Unexpected MCA cache fields')
 return result
def number(value,maximum=2**64-1):
 if not re.fullmatch(r'0|[1-9][0-9]*',value):raise Stop('Malformed unsigned MCA value')
 value=int(value)
 if value>maximum:raise Stop('MCA value overflow')
 return value
def parse_snapshot(text,mode='r75'):
 if mode not in ('r75','r73'):raise Stop('Unknown MCA parser mode')
 reporting=mode=='r75'
 if len(text.encode())>4096:raise Stop('Oversize MCA cache')
 lines=text.splitlines()
 if len(lines)!=7:raise Stop('MCA cache is not header plus six fields')
 raw=fields(lines[0],HEADER_KEYS | REPORTING_KEYS if reporting else HEADER_KEYS)
 expected={'protocol':'1','owner':'0x800a','operation':'GET','max_rounds':'4294967295' if reporting else '60','max_requests':'4294967295' if reporting else '360','clock':'BOOTTIME'}
 if reporting:expected.update(power_supply_reporting='1',freshness_ms='15000')
 if any(raw[k]!=v for k,v in expected.items()):raise Stop('Unexpected MCA protocol/scope')
 h={k:number(v) if k not in ('owner','operation','clock') else v for k,v in raw.items()}
 for k in ('active','finished','stopping','link_up','initial_link_assumed','firmware_reply_seen'):
  if h[k]>1:raise Stop('Invalid MCA state bit')
 if reporting and (h['supply_valid']>1 or not 1<=h['generation']<=2**32-1):raise Stop('Invalid MCA reporting state')
 if h['round']>h['max_rounds'] or h['requests']>h['max_requests'] or h['stop_reason']>(4 if reporting else 3) or h['consecutive_timeouts']>3:raise Stop('MCA bounds exceeded')
 if h['finished'] and (h['stop_reason']==0 or h['run_end_ms']<h['run_start_ms']):raise Stop('MCA completion state inconsistent')
 if h['round'] and (h['round_start_ms']<h['run_start_ms'] or h['round_end_ms']<h['round_start_ms']):raise Stop('MCA time order invalid')
 samples=[]
 for expected,line in zip(PROPERTIES,lines[1:]):
  r=fields(line,ITEM_KEYS)
  for k in ('property','raw_hex','remote_status'):
   if not re.fullmatch(r'0x[0-9a-f]{8}',r[k]):raise Stop('Malformed MCA raw hex')
  if int(r['property'],16)!=expected:raise Stop('MCA property whitelist/order changed')
  if not re.fullmatch(r'0|-[1-9][0-9]*',r['error']):raise Stop('Malformed MCA errno')
  d={k:(int(v,16) if k in ('property','raw_hex','remote_status') else int(v) if k=='error' else number(v)) for k,v in r.items()}
  if d['seq']>2**32-1 or d['raw_u32']>2**32-1 or d['raw_u32']!=d['raw_hex'] or d['error']< -4095:raise Stop('MCA raw/errno overflow or mismatch')
  if any(d[k]>1 for k in ('attempted','valid','response_seen')):raise Stop('Invalid MCA sample flag')
  if d['valid']!=(d['error']==0):raise Stop('MCA valid/error disagreement')
  if d['valid'] and (not d['attempted'] or not d['response_seen'] or d['remote_status']):raise Stop('MCA success lacks reply')
  if not d['attempted'] and (d['valid'] or d['response_seen']):raise Stop('Unattempted MCA sample has data')
  if d['end_ms']<d['start_ms']:raise Stop('MCA sample time order invalid')
  # raw_u32 remains present for provenance, but is interpreted only if valid=1.
  samples.append(d)
 return {'header':h,'samples':samples,'sampling_mode':'persistent_reporting' if reporting else 'r73_bounded_diagnostic','remaining_rounds':None if reporting else 60-h['round'],'has_sample_errors':any(not s['valid'] for s in samples)}
def window(snapshot,uptime_seconds):
 h=snapshot['header'];now_ms=int(float(uptime_seconds)*1000)
 if now_ms<h['run_start_ms']:raise Stop('MCA clock later than current device BOOTTIME')
 if snapshot.get('sampling_mode')=='persistent_reporting':
  # Capture invalid/stale reporting too: that is useful evidence. This gate only
  # proves the reviewed persistent worker has not stopped; it never causes GET.
  return {'eligible':not bool(h['finished'] or h['stopping'] or h['stop_reason']),
          'remaining_rounds':None,'device_elapsed_ms':now_ms-h['run_start_ms'],
          'reason':'sampling_finished_or_stopped' if h['finished'] or h['stopping'] or h['stop_reason'] else 'persistent_reporting_active',
          'supply_valid':bool(h['supply_valid']),'freshness_ms':h['freshness_ms'],
          'cache_round_age_ms':now_ms-h['round_start_ms'] if h['round'] else None,
          'seconds_remaining':'not_applicable; persistent reporting, bounded host recorder'}
 result={'eligible':False,'remaining_rounds':60-h['round'],'device_elapsed_ms':now_ms-h['run_start_ms'],'reason':'not_started_or_no_committed_round','seconds_remaining':'not_estimated; requests/send/suspend do not provide a wall-clock deadline'}
 if h['finished'] or h['stopping'] or h['stop_reason']:
  result['reason']='sampling_finished_or_stopped'
 elif h['round']>=1 and h['round']<=30 and now_ms-h['run_start_ms']<=150000:
  result.update(eligible=True,reason='bounded_run_has_30_or_more_uncommitted_rounds')
 elif h['round']:
  result['reason']='window_too_late_for_wall_interval'
 # active=0 with finished=0 is an ordinary interval between rounds.
 return result
def module_set(text,baseline_names):
 names=[]
 for line in text.splitlines():
  p=line.split()
  if len(p) not in (6,7) or p[4]!='Live' or not re.fullmatch(r'0x[0-9a-fA-F]{1,16}',p[5]):raise Stop('Invalid/not-Live module row')
  if not re.fullmatch(r'[A-Za-z0-9_]+',p[0]) or not p[1].isdigit() or not p[2].isdigit():raise Stop('Invalid module identity')
  if len(p)==7:
   if not re.fullmatch(r'\([PFCOEKXTN]+\)',p[6]):raise Stop('Invalid module taints')
   flags=p[6][1:-1]
   if flags!=''.join(x for x in 'PFCOEKXTN' if x in flags):raise Stop('Unordered/repeated taint')
  names.append(p[0])
 if len(set(names))!=len(names):raise Stop('Duplicate loaded module')
 expected=set(baseline_names)
 if len(expected)!=247:raise Stop('Native baseline must be exact247')
 if set(names)==expected:return 'baseline247_client_absent'
 if set(names)==expected|{'myron_mca_readonly'}:return 'get248'
 raise Stop('Loaded modules differ from exact247/248 contract')
