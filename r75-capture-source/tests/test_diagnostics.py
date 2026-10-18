"""R75 diagnostics states reflect the production serializer, including in-flight reads."""
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import mca_diagnostics as diagnostic
import mca_cache
from r75_common import Stop
from test_core_capture import fixture,TOKEN,BOOT,cache
import core_capture


def data(state='waiting', active=0, next_item=0, attempts=0, stop_error=0, selected=None):
    header=dict(protocol=1,operation='GET',enabled=int(state!='disabled'),state=state,active=active,
                next=next_item,attempts=attempts,max_attempts=5,generation=1 if next_item else 0,
                stop_error=stop_error,clock='BOOTTIME',atomic=0,historical=1)
    rows=[]
    for prop in diagnostic.PROPERTIES:
        rows.append(dict(property=f'0x{prop:08x}',seq=0,core_round=0,generation=0,attempted=0,
                         valid=0,raw_u32=0,raw_hex='0x00000000',error=-61,response_seen=0,
                         remote_status='0x00000000',start_ms=0,end_ms=0))
    for index,changes in (selected or {}).items():rows[index].update(changes)
    return '\n'.join(' '.join(f'{k}={v}' for k,v in row.items()) for row in [header,*rows])+'\n'


class DiagnosticTests(unittest.TestCase):
    def test_waiting_and_disabled_are_valid_nonerror_evidence(self):
        for state in ('waiting','disabled'):
            parsed=diagnostic.parse_snapshot(data(state))
            self.assertFalse(parsed['has_attempt_errors'])
            self.assertTrue(all(not r['attempted'] for r in parsed['samples']))

    def test_active_initial_and_wire_reserved_rows_are_not_mistaken_for_failure(self):
        for update in [dict(core_round=4,generation=1,error=-115),dict(core_round=4,generation=1,error=-115,seq=25,attempted=1,start_ms=8000)]:
            parsed=diagnostic.parse_snapshot(data('running',1,1,update.get('attempted',0),selected={0:update}))
            self.assertFalse(parsed['has_attempt_errors'])
            self.assertEqual(parsed['samples'][0]['end_ms'],0)

    def test_stopped_active_and_pre_wire_errors_preserved(self):
        blocked=diagnostic.parse_snapshot(data('stopped',1,1,1,-32,{0:dict(core_round=4,generation=1,error=-115,seq=25,attempted=1,start_ms=8000)}))
        self.assertTrue(blocked['has_attempt_errors'])
        overflow=diagnostic.parse_snapshot(data('stopped',0,1,0,-75,{0:dict(core_round=4,generation=1,error=-75,start_ms=8000,end_ms=8000)}))
        self.assertTrue(overflow['has_attempt_errors']);self.assertEqual(overflow['header']['attempts'],0)

    def test_complete_preserves_unsigned_history_without_capability_decode(self):
        selected={i:dict(seq=25+i,core_round=4+i,generation=1,attempted=1,valid=1,raw_u32=0xffffffff,
                         raw_hex='0xffffffff',error=0,response_seen=1,start_ms=8000+i*2000,end_ms=8001+i*2000) for i in range(5)}
        parsed=diagnostic.parse_snapshot(data('complete',0,5,5,selected=selected))
        self.assertFalse(parsed['has_attempt_errors'])
        self.assertEqual(parsed['scope'],'historical_sequential_nonatomic_only')
        self.assertEqual(parsed['samples'][0]['raw_u32'],0xffffffff)
        self.assertNotIn('pps_capability',parsed)

    def test_schema_order_truncation_and_false_completion_are_rejected(self):
        valid=data()
        for bad in [valid[:-20],valid.replace('max_attempts=5','max_attempts=6'),valid.replace('property=0x00002002','property=0x00002029'),data('complete',0,5,5),valid.replace('atomic=0','atomic=1')]:
            with self.subTest(bad=bad[:100]),self.assertRaises(Stop):diagnostic.parse_snapshot(bad)

    def test_extra_cache_is_after_core_and_core_parser_remains_six_gets(self):
        with fixture() as (_,write,run):
            write(mca_cache.TARGET+'/myron_mca_readonly/diagnostics',data().rstrip())
            _,text=run()
            self.assertLess(text.index('CORE_END'),text.index('DIAGNOSTICS_CACHE_BEGIN'))
            self.assertTrue(core_capture.parse_frame(text,TOKEN,BOOT)['telemetry_valid'])
            parsed=diagnostic.periodic('ROUND=1\n'+text)
            self.assertFalse(parsed['read_issues']);self.assertEqual(parsed['frames'][0]['header']['state'],'waiting')
            with self.assertRaises(Stop):mca_cache.parse_snapshot(data())
            with self.assertRaises(Stop):diagnostic.parse_snapshot(cache())

    def test_missing_or_truncated_extra_keeps_core_valid_but_records_gap(self):
        with fixture() as (_,_,run):
            _,text=run()
            self.assertTrue(core_capture.parse_frame(text,TOKEN,BOOT)['telemetry_valid'])
            self.assertTrue(diagnostic.periodic('ROUND=1\n'+text)['read_issues'])
            self.assertTrue(diagnostic.periodic('ROUND=1\n'+text.split('DIAGNOSTICS_CACHE_END')[0])['read_issues'])

    def test_legacy_bounded_diagnostic_remains_explicit(self):
        old=cache().replace('max_rounds=4294967295','max_rounds=60').replace('max_requests=4294967295','max_requests=360')
        old=old.replace(' power_supply_reporting=1 freshness_ms=15000 supply_valid=1 generation=1','')
        self.assertEqual(mca_cache.parse_snapshot(old,mode='r73')['header']['max_rounds'],60)
        with self.assertRaises(Stop):mca_cache.parse_snapshot(old)

if __name__=='__main__':unittest.main(verbosity=2)
