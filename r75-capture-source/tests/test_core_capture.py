"""Execute the actual fixed shell against isolated fake sysfs; never contact a device."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import collect_r75 as capture
import core_capture
import mca_cache

BOOT = '11111111-2222-3333-4444-555555555555'
TOKEN = 'ab' * 16

def cache():
    fields = dict(protocol=1, owner='0x800a', operation='GET', round=2, max_rounds=4294967295,
                  active=0, finished=0, stopping=0, link_up=1, requests=12, max_requests=4294967295,
                  run_start_ms=1000, run_end_ms=0, round_start_ms=3000, round_end_ms=3010,
                  clock='BOOTTIME', initial_link_assumed=1, firmware_reply_seen=1,
                  consecutive_timeouts=0, stop_reason=0, power_supply_reporting=1,
                  freshness_ms=15000, supply_valid=1, generation=1)
    rows = [' '.join(f'{k}={v}' for k,v in fields.items())]
    for i, prop in enumerate(mca_cache.PROPERTIES):
        raw = 0xffffffff if i == 5 else 1
        rows.append(f'property=0x{prop:08x} seq={i+7} attempted=1 valid=1 raw_u32={raw} raw_hex=0x{raw:08x} error=0 response_seen=1 remote_status=0x00000000 start_ms=3000 end_ms=3001')
    return '\n'.join(rows)+'\n'

@contextlib.contextmanager
def fixture(battery_owner='myron_bq_readonly', usb_model='myron-mca-readonly'):
    with tempfile.TemporaryDirectory(prefix='r75-fake-sysfs-') as temporary:
        root = Path(temporary)
        def path(name): return root / name.lstrip('/')
        def write(name, value):
            p = path(name); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(value+'\n'); return p
        def link(name, target):
            p=path(name);p.parent.mkdir(parents=True,exist_ok=True);p.symlink_to(path(target));return p
        write('/proc/sys/kernel/random/boot_id',BOOT)
        write('/proc/uptime','100.0 0.0')
        real='/sys/devices/platform/soc/soc:pmic-glink/soc:pmic-glink:mca,adsp_glink'
        driver='/sys/bus/platform/drivers/myron_mca_readonly'
        module='/sys/module/myron_mca_readonly'
        path(real).mkdir(parents=True)
        path(driver).mkdir(parents=True)
        path('/sys/firmware/devicetree/base/soc/pmic-glink/mca,adsp_glink').mkdir(parents=True)
        link(mca_cache.TARGET,real)
        link(real+'/driver',driver)
        link(real+'/of_node','/sys/firmware/devicetree/base/soc/pmic-glink/mca,adsp_glink')
        link(driver+'/module',module)
        write(real+'/myron_mca_readonly/snapshot',cache().rstrip())
        for parameter in ('enable_readonly','enable_power_supply'):
            write(module+'/parameters/'+parameter,'Y')
        battery='/sys/class/power_supply/battery'
        device='/sys/bus/i2c/devices/5-0055'
        gauge_driver='/sys/bus/i2c/drivers/'+battery_owner
        path(device).mkdir(parents=True);path(gauge_driver).mkdir(parents=True)
        link(battery+'/device',device);link(device+'/driver',gauge_driver);link(gauge_driver+'/module','/sys/module/myron_bq_readonly')
        for parameter in ('enable_readonly','enable_extended_readonly','enable_status_readonly'):
            write('/sys/module/myron_bq_readonly/parameters/'+parameter,'Y')
        for key,val in dict(type='Battery',status='Charging',current_now='-123000',voltage_now='4000000',capacity='56',temp='307',health='Unknown').items():
            write(battery+'/'+key,val)
        write(battery+'/myron_readonly_diag/battery_status_raw','0xffff')
        usb='/sys/class/power_supply/usb'
        link(usb+'/device',real)
        for key,val in dict(type='USB',model_name=usb_model,online='1',status='Charging',current_now='650000',voltage_now='4828000').items():
            write(usb+'/'+key,val)
        # Poison unsupported/optional files. Core must never read them.
        for name in (usb+'/current_max',usb+'/usb_type','/sys/class/typec/port0/power_role'):
            write(name,'UNREVIEWED_GETTER')
        text=(ROOT/'snapshot.sh').read_text()
        text=re.sub(r'/(sys|proc)/',lambda m:str(root/m.group(1))+'/',text).replace('/system/bin/toybox ','')
        script=root/'snapshot.sh';script.write_text(text)
        def run(timeout=12):
            result=subprocess.run(['sh',str(script),TOKEN,BOOT],capture_output=True,text=True,timeout=timeout)
            normalized=result.stdout.replace(str(root),'')
            return result,normalized
        yield root,write,run


class ShellCoreTests(unittest.TestCase):
    def test_verified_core_first_preserves_signed_and_unsigned_raw_values(self):
        with fixture() as (_,write,run):
            result,text=run();self.assertEqual(result.returncode,0,result.stderr)
            parsed=core_capture.parse_frame(text,TOKEN,BOOT)
            self.assertTrue(parsed['telemetry_valid'],parsed)
            self.assertEqual(len(parsed['properties']),19)
            self.assertEqual(parsed['properties'][core_capture.BATTERY+'current_now']['value'],'-123000')
            self.assertEqual(parsed['properties'][core_capture.BATTERY+'myron_readonly_diag/battery_status_raw']['value'],'0xffff')
            self.assertEqual(parsed['mca']['samples'][-1]['raw_u32'],0xffffffff)
            self.assertLess(text.index('MCA_CACHE_BEGIN'),text.index('PATH='+core_capture.BATTERY+'status'))
            self.assertNotIn('UNREVIEWED_GETTER',text)
            self.assertNotIn('/sys/class/typec/',text)

    def test_wrong_owner_and_usb_model_skip_measurement_getters(self):
        for kwargs,path in [({'battery_owner':'unknown_gauge'},core_capture.BATTERY+'current_now'),({'usb_model':'unknown_usb'},core_capture.USB+'online')]:
            with self.subTest(kwargs=kwargs),fixture(**kwargs) as (_,_,run):
                result,text=run();self.assertEqual(result.returncode,0)
                self.assertNotIn('PATH='+path+'\n',text)
                self.assertFalse(core_capture.parse_frame(text,TOKEN,BOOT)['complete_read_records'])

    def test_failed_getter_is_complete_attempt_but_invalid_and_partial(self):
        with fixture() as (root,_,run):
            p=root/'sys/class/power_supply/usb/online';p.unlink();p.mkdir()
            result,text=run();parsed=core_capture.parse_frame(text,TOKEN,BOOT)
            self.assertTrue(parsed['complete_read_records'],parsed)
            self.assertFalse(parsed['telemetry_valid'])
            value=parsed['properties'][core_capture.USB+'online']
            self.assertEqual(value['read_rc'],1);self.assertIsNone(value['value'])

    def test_blocking_getter_times_out_without_hiding_error(self):
        with fixture() as (root,_,run):
            p=root/'sys/class/power_supply/usb/online';p.unlink();os.mkfifo(p)
            result,text=run();parsed=core_capture.parse_frame(text,TOKEN,BOOT)
            self.assertEqual(parsed['properties'][core_capture.USB+'online']['read_rc'],124)
            self.assertFalse(parsed['telemetry_valid']);self.assertTrue(parsed['complete_read_records'])

    def test_head_success_with_oversized_value_is_explicitly_truncated(self):
        with fixture() as (_,write,run):
            write(core_capture.BATTERY+'current_now','9'*400)
            _,text=run();parsed=core_capture.parse_frame(text,TOKEN,BOOT)
            value=parsed['properties'][core_capture.BATTERY+'current_now']
            self.assertEqual(value['read_rc'],0);self.assertTrue(value['truncated']);self.assertIsNone(value['value'])
            self.assertFalse(parsed['telemetry_valid'])

    def test_published_summary_does_not_promote_head_truncation_to_value(self):
        with fixture() as (_,write,run),tempfile.TemporaryDirectory() as temporary:
            write(core_capture.USB+'current_now','9'*400)
            _,text=run();folder=Path(temporary);(folder/'periodic.log').write_text('ROUND=1\n'+text)
            parsed=capture.reporting_periodic(folder)
            value=parsed['frames'][0]['properties'][core_capture.USB+'current_now']
            self.assertEqual(value['read_rc'],0);self.assertTrue(value['truncated']);self.assertIsNone(value['value'])
            self.assertTrue(parsed['read_issues'])

    def test_truncated_core_or_clock_marker_cannot_be_promoted(self):
        with fixture() as (_,_,run):
            _,text=run()
            for damaged in [text.split('CORE_END')[0],text.replace('CORE_END protocol=1','CORE_END protocol=2'),text.replace('uptime=100.0\nPATH=', 'uptime=\nPATH=',1),text.replace('clock=BOOTTIME uptime=100.0 rc=0','clock=BOOTTIME uptime=99.0 rc=0',1)]:
                with self.subTest(tail=damaged[-100:]):
                    self.assertFalse(core_capture.parse_frame(damaged,TOKEN,BOOT)['complete_read_records'])

    def test_duplicate_attribute_rejected(self):
        with fixture() as (_,_,run):
            _,text=run()
            block=re.search(r'^READ_TIMING_BEGIN.*?^READ_TIMING_END.*?$',text,re.M|re.S)[0]
            text=text.replace('CORE_END',block+'\nCORE_END',1)
            self.assertFalse(core_capture.parse_frame(text,TOKEN,BOOT)['complete_read_records'])

    def test_independent_core_survives_outer_timeout_but_overall_stays_partial(self):
        with fixture() as (_,_,run),tempfile.TemporaryDirectory() as temporary:
            _,text=run();text=text.split('SNAPSHOT_END')[0]+'SNAPSHOT_END token='+TOKEN+' boot_id='+BOOT+' uptime=\nSNAPSHOT_EXEC_RC=124\n'
            folder=Path(temporary);(folder/'periodic.log').write_text('ROUND=1\n'+text)
            receipt=dict(token=TOKEN,boot_id=BOOT)
            report=capture.periodic_check(folder,receipt,{'rounds':'1'})
            self.assertEqual(report['complete_core_records'],1)
            self.assertFalse(report['complete_snapshots']);self.assertEqual(report['ends'],0)

    def test_transition_is_observation_interval_never_hardware_latency(self):
        with fixture() as (_,write,run):
            _,one=run();write(core_capture.USB+'online','0');write('/proc/uptime','104.0 0.0');_,two=run()
            data=core_capture.periodic('ROUND=1\n'+one+'ROUND=2\n'+two,TOKEN,BOOT)
            transition=data['observed_transitions'][0]
            self.assertEqual(transition['observation_interval_seconds'],['100.0','104.0'])
            self.assertIsNone(transition['physical_event_time']);self.assertIsNone(transition['response_latency_seconds'])
            broken=core_capture.periodic('ROUND=1\n'+one+'ROUND=2\n'+two.split('CORE_END')[0]+'ROUND=3\n'+two,TOKEN,BOOT)
            self.assertEqual(broken['observed_transitions'],[])

    def test_cross_frame_clock_and_round_order_cannot_create_transitions(self):
        with fixture() as (_,write,run):
            _,one=run();write(core_capture.USB+'online','0');write('/proc/uptime','90.0 0.0');_,two=run()
            data=core_capture.periodic('ROUND=1\n'+one+'ROUND=2\n'+two,TOKEN,BOOT)
            self.assertFalse(data['frames'][1]['telemetry_valid'])
            self.assertIn('cross_frame_clock_reversed',data['frames'][1]['structural_errors'])
            self.assertEqual(data['observed_transitions'],[])
            skipped=core_capture.periodic('ROUND=1\n'+one+'ROUND=9\n'+one,TOKEN,BOOT)
            self.assertEqual(skipped['frames'][1]['recorder_round'],9)
            self.assertFalse(skipped['frames'][1]['complete_read_records'])

    def test_unfrozen_candidate_blocks_before_resolving_device_tools(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(capture,'ROOT',Path(temporary)),patch.object(capture,'tool',side_effect=AssertionError('device tool forbidden')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(capture.main(['start']),1)
            summary=json.loads(next((Path(temporary)/'results').glob('*/summary.json')).read_text())
            self.assertEqual(summary['commands'],[]);self.assertEqual(summary['status'],'partial')

    def test_optional_metadata_separated_and_has_bounded_frame(self):
        snapshot=(ROOT/'snapshot.sh').read_text();foreground=(ROOT/'foreground.sh').read_text();recorder=(ROOT/'recorder.sh').read_text()
        self.assertNotIn('ucsi-source-psy',snapshot);self.assertIn('ucsi-source-psy',foreground)
        self.assertIn('timeout --foreground -k 1 8',recorder)
        self.assertIn('OPTIONAL_METADATA_BEGIN',foreground);self.assertIn('OPTIONAL_METADATA_END',foreground)
        self.assertFalse(core_capture.metadata_complete('OPTIONAL_METADATA_BEGIN clock=BOOTTIME uptime=1.0\n'))

if __name__=='__main__':unittest.main(verbosity=2)
