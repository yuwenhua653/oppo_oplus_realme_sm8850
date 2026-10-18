"""R75 core-record validation and observation intervals, never physical-event inference."""
import re
from decimal import Decimal
import mca_cache
from r75_common import Stop

CLOCK = r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?'
BATTERY = '/sys/class/power_supply/battery/'
USB = '/sys/class/power_supply/usb/'
EXPECTED = {BATTERY + k for k in ('type', 'status', 'current_now', 'voltage_now', 'capacity', 'temp', 'health', 'myron_readonly_diag/battery_status_raw')}
EXPECTED |= {USB + k for k in ('type', 'model_name', 'online', 'status', 'voltage_now', 'current_now')}
EXPECTED |= {'/sys/module/myron_bq_readonly/parameters/' + k for k in ('enable_readonly', 'enable_extended_readonly', 'enable_status_readonly')}
EXPECTED |= {'/sys/module/myron_mca_readonly/parameters/' + k for k in ('enable_readonly', 'enable_power_supply')}
OBSERVED = (USB+'online', USB+'status', BATTERY+'status')


def scalar_valid(path, value):
    if '\n' in value or len(value.encode()) > 256:
        return False
    if '/parameters/' in path:
        return value in ('Y', '1')
    if path == USB+'model_name':
        return value == 'myron-mca-readonly'
    if path.endswith('/type'):
        return value == ('Battery' if path.startswith(BATTERY) else 'USB')
    if path.endswith('/status'):
        return value in ('Unknown', 'Charging', 'Discharging', 'Not charging', 'Full')
    if path.endswith('/health'):
        return value == 'Unknown'  # This independent gauge deliberately has no decoded health.
    if path.endswith('/battery_status_raw'):
        return re.fullmatch(r'0x[0-9a-fA-F]{4}', value) is not None
    if path == USB+'online':
        return value in ('0', '1')
    return re.fullmatch(r'-?(?:0|[1-9][0-9]*)', value) is not None


def parse_frame(frame, token, boot):
    result = {'complete_read_records': False, 'telemetry_valid': False,
              'properties': {}, 'structural_errors': [], 'read_issues': []}
    errors = result['structural_errors']
    boundary = r'^CORE_(BEGIN|END) protocol=1 token=([^ ]+) boot_id=([^ ]+) clock=BOOTTIME uptime=('+CLOCK+r')$'
    markers = list(re.finditer(boundary, frame, re.M))
    if frame.count('CORE_BEGIN ') != 1 or frame.count('CORE_END ') != 1 or len(markers) != 2 or [m[1] for m in markers] != ['BEGIN', 'END']:
        errors.append('core_boundary_missing_duplicate_or_truncated')
        return result
    if any((m[2], m[3]) != (token, boot) for m in markers):
        errors.append('core_identity_mismatch')
    begin, end = (Decimal(m[4]) for m in markers)
    if begin > end:
        errors.append('core_clock_reversed')
    result['interval'] = {'clock': 'BOOTTIME', 'start_seconds': str(begin), 'end_seconds': str(end)}
    body = frame[markers[0].end():markers[1].start()]
    pattern = (r'^READ_TIMING_BEGIN path=([^\n ]+) clock=BOOTTIME uptime=('+CLOCK+r')\n'
               r'PATH=([^\n]+)\nEXISTS=([01])\n(.*?)\nREAD_RC=([0-9]+)\n'
               r'READ_TIMING_END path=([^\n ]+) clock=BOOTTIME uptime=('+CLOCK+r') rc=([0-9]+) truncated=([01])$')
    reads = list(re.finditer(pattern, body, re.M | re.S))
    if body.count('\nREAD_TIMING_BEGIN ') != len(reads) or body.count('\nREAD_TIMING_END ') != len(reads):
        errors.append('read_timing_missing_or_truncated')
    intervals = []
    for m in reads:
        path, start, repeated_path, exists, raw, rc, end_path, finish, end_rc, truncated = m.groups()
        if path not in EXPECTED or path in result['properties']:
            errors.append('unexpected_or_duplicate_path:'+path)
            continue
        a, b = Decimal(start), Decimal(finish)
        intervals.append((m.start(), a, b))
        if repeated_path != path or end_path != path or rc != end_rc or not begin <= a <= b <= end:
            errors.append('read_identity_rc_or_clock_mismatch:'+path)
        valid = exists == '1' and rc == '0' and truncated == '0' and scalar_valid(path, raw)
        value = {'exists': exists == '1', 'raw_text': raw, 'read_rc': int(rc),
                 'truncated': truncated == '1', 'value': raw if valid else None,
                 'clock': 'BOOTTIME', 'start_seconds': start, 'end_seconds': finish}
        result['properties'][path] = value
        if not valid:
            result['read_issues'].append({'path': path, 'read_rc': int(rc), 'truncated': truncated == '1', 'error': 'failed_missing_truncated_or_invalid_value'})
    for path in sorted(EXPECTED - set(result['properties'])):
        errors.append('missing_read:'+path)
    # MCA is distinct from scalar reads; six raw samples retain their original parser.
    pattern = (r'^MCA_TIMING_BEGIN clock=BOOTTIME uptime=('+CLOCK+r')\nMCA_CACHE_BEGIN\n(.*?)'
               r'^MCA_CACHE_READ_RC=([0-9]+)\nMCA_CACHE_END\n'
               r'MCA_TIMING_END clock=BOOTTIME uptime=('+CLOCK+r') rc=([0-9]+) truncated=([01])$')
    caches = list(re.finditer(pattern, body, re.M | re.S))
    if len(caches) != 1 or body.count('MCA_TIMING_BEGIN ') != 1 or body.count('MCA_TIMING_END ') != 1:
        errors.append('mca_read_missing_duplicate_or_truncated')
    else:
        m = caches[0]; a, b = Decimal(m[1]), Decimal(m[4])
        intervals.append((m.start(), a, b))
        if not begin <= a <= b <= end or m[3] != m[5]:
            errors.append('mca_rc_or_clock_mismatch')
        result['mca_read'] = {'clock': 'BOOTTIME', 'start_seconds': m[1], 'end_seconds': m[4], 'read_rc': int(m[3]), 'truncated': m[6] == '1'}
        if m[3] != '0' or m[6] != '0':
            result['read_issues'].append({'path': mca_cache.SNAPSHOT, 'error': 'mca_failed_or_truncated'})
        else:
            try:
                result['mca'] = mca_cache.parse_snapshot(m[2])
                if result['mca']['has_sample_errors']:
                    result['read_issues'].append({'path': mca_cache.SNAPSHOT, 'error': 'mca_sample_error_or_not_attempted'})
            except Stop as e:
                result['read_issues'].append({'path': mca_cache.SNAPSHOT, 'error': str(e)})
    last = begin
    for _, a, b in sorted(intervals):
        if a < last:
            errors.append('sequential_read_clock_reversed')
        last = b
    result['complete_read_records'] = not errors
    result['telemetry_valid'] = not (errors or result['read_issues'])
    return result


def periodic(text, token, boot):
    frames = []
    pieces = re.split(r'^ROUND=([0-9]+)\n', text, flags=re.M)
    previous_end = None
    for index in range(1, len(pieces), 2):
        number, raw = int(pieces[index]), pieces[index+1]
        frame = {'recorder_round': number, **parse_frame(raw, token, boot)}
        if number != (index+1)//2 or pieces[0].strip():
            frame['structural_errors'].append('recorder_round_order_or_preamble_invalid')
        interval = frame.get('interval')
        if interval:
            start, end = Decimal(interval['start_seconds']), Decimal(interval['end_seconds'])
            if previous_end is not None and start < previous_end:
                frame['structural_errors'].append('cross_frame_clock_reversed')
            previous_end = max(previous_end, end) if previous_end is not None else end
        frame['complete_read_records'] = not frame['structural_errors']
        frame['telemetry_valid'] = frame['complete_read_records'] and not frame['read_issues']
        frames.append(frame)
    transitions = []
    previous = {}
    for frame in frames:
        for path in OBSERVED:
            v = frame['properties'].get(path)
            if not frame['complete_read_records'] or not v or v['value'] is None:
                previous.pop(path, None)
                continue
            if path in previous and previous[path]['value'] != v['value']:
                before = previous[path]
                transitions.append({'path': path, 'before_raw': before['value'], 'after_raw': v['value'],
                    'clock': 'BOOTTIME', 'observation_interval_seconds': [before['start_seconds'], v['end_seconds']],
                    'before_read_interval_seconds': [before['start_seconds'], before['end_seconds']],
                    'after_read_interval_seconds': [v['start_seconds'], v['end_seconds']],
                    'physical_event_time': None, 'response_latency_seconds': None})
            previous[path] = v
    return {'frames': frames, 'complete_core_records': sum(f['complete_read_records'] for f in frames),
            'valid_telemetry_frames': sum(f['telemetry_valid'] for f in frames),
            'observed_transitions': transitions,
            'interpretation': 'Intervals bound observations of published values, not physical cable events. Reads are sequential. Missing/failed records break transition continuity. No hardware event time or response latency is inferred from operator stages or host clock.'}


def metadata_complete(text):
    starts = re.findall(r'^OPTIONAL_METADATA_BEGIN clock=BOOTTIME uptime=('+CLOCK+r')$', text, re.M)
    ends = re.findall(r'^OPTIONAL_METADATA_END clock=BOOTTIME uptime=('+CLOCK+r')$', text, re.M)
    return len(starts) == len(ends) == 1 and Decimal(starts[0]) <= Decimal(ends[0])
