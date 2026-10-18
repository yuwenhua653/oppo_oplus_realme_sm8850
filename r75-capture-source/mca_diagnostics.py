"""Strict separate R75 historical GET diagnostics; never capability or live supply data."""
import re
from decimal import Decimal
from r75_common import Stop
import mca_cache
from core_capture import CLOCK

PROPERTIES = (0x2002, 0x2029, 0x21013, 0x21014, 0x21019)
HEADER_KEYS = set('protocol operation enabled state active next attempts max_attempts generation stop_error clock atomic historical'.split())
ITEM_KEYS = mca_cache.ITEM_KEYS | {'core_round','generation'}
STATES = ('disabled','waiting','running','complete','stopped')


def errno(value):
    if not re.fullmatch(r'0|-[1-9][0-9]*', value) or int(value) < -4095:
        raise Stop('Invalid diagnostic errno')
    return int(value)


def parse_snapshot(text):
    if len(text.encode()) > 4096:
        raise Stop('Oversize diagnostics cache')
    lines = text.splitlines()
    if len(lines) != 6:
        raise Stop('Diagnostics must be one header plus five ordered fields')
    raw = mca_cache.fields(lines[0],HEADER_KEYS)
    if any(raw[k] != v for k,v in dict(protocol='1',operation='GET',max_attempts='5',clock='BOOTTIME',atomic='0',historical='1').items()) or raw['state'] not in STATES:
        raise Stop('Unexpected diagnostics protocol/scope')
    h = {k:(errno(v) if k=='stop_error' else v if k in ('operation','state','clock') else mca_cache.number(v,2**32-1)) for k,v in raw.items()}
    if h['enabled']>1 or h['active']>1 or h['next']>5 or h['attempts']>5:
        raise Stop('Diagnostics bounds exceeded')
    if (h['state']=='disabled') != (h['enabled']==0):
        raise Stop('Diagnostics enable/state disagreement')
    samples=[]
    for prop,line in zip(PROPERTIES,lines[1:]):
        row=mca_cache.fields(line,ITEM_KEYS)
        for k in ('property','raw_hex','remote_status'):
            if not re.fullmatch(r'0x[0-9a-f]{8}',row[k]):
                raise Stop('Invalid diagnostic hexadecimal field')
        if int(row['property'],16)!=prop:
            raise Stop('Diagnostics property allowlist/order changed')
        d={k:(int(v,16) if k in ('property','raw_hex','remote_status') else errno(v) if k=='error' else mca_cache.number(v)) for k,v in row.items()}
        if any(d[k]>2**32-1 for k in ('seq','core_round','generation','raw_u32')) or d['raw_u32']!=d['raw_hex']:
            raise Stop('Diagnostics overflow/raw mismatch')
        in_progress = bool(h['active'] and not d['valid'] and d['end_ms']==0 and d['error']==-115)
        if any(d[k]>1 for k in ('attempted','valid','response_seen')) or (d['end_ms']<d['start_ms'] and not in_progress):
            raise Stop('Diagnostics flag/time mismatch')
        if bool(d['valid']) != bool(d['attempted'] and d['response_seen'] and not d['error'] and not d['remote_status']):
            raise Stop('Historical diagnostic validity/reply fields disagree')
        if not d['attempted'] and (d['valid'] or d['response_seen']):
            raise Stop('Unattempted diagnostic claims data')
        samples.append(d)
    if h['state']=='waiting' and (h['next'] or h['attempts'] or h['active'] or h['stop_error']):
        raise Stop('Diagnostics waiting state inconsistent')
    if h['state']=='complete' and (h['next']!=5 or h['attempts']!=5 or not all(d['valid'] for d in samples)):
        raise Stop('Diagnostics completion lacks five accepted historical replies')
    if h['state']=='stopped' and not h['stop_error']:
        raise Stop('Stopped diagnostics lacks terminal error')
    if h['state']!='stopped' and h['stop_error']:
        raise Stop('Unexpected diagnostic terminal error')
    if sum(d['attempted'] for d in samples)>h['attempts']:
        raise Stop('Diagnostics attempted count inconsistent')
    return {'header':h,'samples':samples,'scope':'historical_sequential_nonatomic_only',
            'has_attempt_errors':any(d['attempted'] and not d['valid'] and d['error'] not in (0,-115) for d in samples) or bool(h['stop_error']),
            'waiting_without_pd_is_valid':h['state']=='waiting'}


def periodic(text):
    result={'frames':[],'read_issues':[],'interpretation':'Five historical sequential diagnostics. Never live USB current/voltage, available PPS capability, or proof of an unchanged physical charger session. Disabled/waiting is valid evidence, not a GET failure.'}
    pattern=(r'^DIAGNOSTICS_TIMING_BEGIN clock=BOOTTIME uptime=('+CLOCK+r')\nDIAGNOSTICS_CACHE_BEGIN\n(.*?)'
             r'^DIAGNOSTICS_CACHE_READ_RC=([0-9]+)\nDIAGNOSTICS_CACHE_END\n'
             r'DIAGNOSTICS_TIMING_END clock=BOOTTIME uptime=('+CLOCK+r') rc=([0-9]+) truncated=([01])$')
    for number,frame in enumerate(re.split(r'^ROUND=[0-9]+\n',text,flags=re.M)[1:],1):
        record={'recorder_round':number};result['frames'].append(record)
        matches=list(re.finditer(pattern,frame,re.M|re.S))
        try:
            if len(matches)!=1 or frame.count('DIAGNOSTICS_TIMING_BEGIN ')!=1 or frame.count('DIAGNOSTICS_TIMING_END ')!=1:
                raise Stop('Diagnostics read missing/duplicate/truncated')
            m=matches[0]
            record.update(clock='BOOTTIME',start_seconds=m[1],end_seconds=m[4],read_rc=int(m[3]),truncated=m[6]=='1')
            if m[3]!=m[5] or Decimal(m[1])>Decimal(m[4]):
                raise Stop('Diagnostics read rc/time mismatch')
            if m[3]!='0' or m[6]!='0':
                raise Stop('Diagnostics getter failed/truncated')
            record.update(parse_snapshot(m[2]))
            if record['has_attempt_errors']:
                result['read_issues'].append({'recorder_round':number,'error':'Historical diagnostic attempt failed'})
        except Stop as e:
            result['read_issues'].append({'recorder_round':number,'error':str(e)})
    return result
