#!/usr/bin/env python3
"""Execute production shell flow with temporary filesystem/command boundaries.
No device, module insertion, firmware action or charging write is performed.
"""
import hashlib, json, os, re, shutil, subprocess, tempfile, unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
KERNEL='6.12.81-android16-6-maybe-dirty-4k'
class Runtime(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='r97-test-');self.root=Path(self.temp.name)
        for p in ['system/bin','tmp','proc/sys/kernel','sys/firmware/devicetree/base','r97-runtime/modules','props']:(self.root/p).mkdir(parents=True)
        self.put('props/ro.boot.hardware.sku','myron');self.put('props/init.svc.ueventd','running')
        self.put('sys/firmware/devicetree/base/model','Qualcomm Technologies, Inc. Myron based on SM8850\0')
        self.put('proc/sys/kernel/modules_disabled','0\n');self.put('proc/modules','first 1 0 - Live 0x0\n')
        self.put('r97-runtime/firststage.txt','first\n');self.put('r97-runtime/allowed-live.txt','first\nui\nhardware\n')
        self.put('r97-runtime/ui.list','ui|ui.ko|\n');self.put('r97-runtime/hardware.list','hardware|hardware.ko|\n')
        for n in ['ui','hardware']:self.put('r97-runtime/modules/'+n+'.ko',n)
        self.put('r97-runtime/modules.sha256',''.join(hashlib.sha256(n.encode()).hexdigest()+'  modules/'+n+'.ko\n' for n in ['ui','hardware']))
        for p in (HERE/'overlay/recovery/root/r97-runtime').glob('*.sh'):
            s=p.read_text()
            s=re.sub(r'(?<![\w/-])/(system|r97-runtime|proc|sys|tmp|firmware)(?=/|\n)',lambda m:str(self.root/m[1]),s)
            self.put('r97-runtime/'+p.name,s)
        wrapper='''#!/usr/bin/python3
import os,sys,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[2]; cmd=Path(sys.argv[0]).name;a=sys.argv[1:]
os.environ['PATH']='/usr/bin:/bin'
if cmd=='getprop':
 p=r/'props'/a[0];print(p.read_text().strip() if p.exists() else '');sys.exit(0)
if cmd=='setprop':
 (r/'props'/a[0]).write_text(a[1]);sys.exit(0)
cmd=a.pop(0)
if cmd=='uname':print('KERNEL');sys.exit(0)
if cmd=='insmod':
 n=Path(a[0]).stem
 if (r/'fail-insert').exists():sys.exit(1)
 with (r/'proc/modules').open('a') as f:f.write(n+' 1 0 - Live 0x0\\n')
 sys.exit(0)
if cmd=='timeout':
 os.execvp('timeout',['timeout']+a)
os.execvp(cmd,[cmd]+a)
'''.replace('KERNEL',KERNEL)
        self.put('system/bin/toybox',wrapper,True)
        for n in ['getprop','setprop']:self.put('system/bin/'+n,wrapper,True)
        (self.root/'system/bin/sh').symlink_to('/bin/sh')
        (self.root/'system/bin/mkdir').symlink_to('/bin/mkdir')
        self.put('system/bin/sleep','#!/bin/sh\nexit 0\n',True)
    def tearDown(self):self.temp.cleanup()
    def put(self,n,s,executable=False):
        p=self.root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
        if executable:p.chmod(0o755)
    def run_script(self,n,ok):
        p=subprocess.run(['/bin/sh',str(self.root/'r97-runtime'/n)],capture_output=True,timeout=30)
        self.assertEqual(p.returncode==0,ok,p.stderr.decode()+self.logs())
    def logs(self):return '\n'.join(p.read_text() for p in (self.root/'tmp').glob('*.log'))
    def ready(self):return (self.root/'props/sys.r97.ui.ready').exists()
    def test_ui_success(self):
        self.run_script('load-ui.sh',True);self.assertTrue(self.ready())
        self.assertEqual((self.root/'props/twrp.modules.loaded').read_text(),'true')
    def test_bad_hash(self):
        self.put('r97-runtime/modules/hardware.ko','corrupt');self.run_script('load-ui.sh',False)
        self.assertFalse(self.ready());self.assertNotIn('ui ',(self.root/'proc/modules').read_text())
    def test_wrong_kernel(self):
        p=self.root/'system/bin/toybox';p.write_text(p.read_text().replace(KERNEL,'other'))
        self.run_script('load-ui.sh',False);self.assertFalse(self.ready())
    def test_wrong_sku(self):
        self.put('props/ro.boot.hardware.sku','pudding');self.run_script('load-ui.sh',False);self.assertFalse(self.ready())
    def test_missing_firststage(self):
        self.put('proc/modules','');self.run_script('load-ui.sh',False);self.assertFalse(self.ready())
    def test_unknown_owner(self):
        self.put('proc/modules','first 1 0 - Live 0x0\nmyron_bq_readonly 1 0 - Live 0x0\n')
        self.run_script('load-ui.sh',False);self.assertFalse(self.ready())
    def test_insert_failure(self):
        self.put('fail-insert','1');self.run_script('load-ui.sh',False);self.assertFalse(self.ready())
    def test_no_hot_retry(self):
        self.run_script('load-ui.sh',True);before=(self.root/'proc/modules').read_bytes()
        self.run_script('load-ui.sh',False);self.assertEqual(before,(self.root/'proc/modules').read_bytes())
    def test_hardware_failure_keeps_ui(self):
        self.run_script('load-ui.sh',True);self.run_script('load-hardware.sh',False)
        self.assertTrue(self.ready());self.assertFalse((self.root/'props/sys.r97.battery.ready').exists())
    def test_hardware_identity_chain(self):
        self.run_script('load-ui.sh',True)
        dt='sys/firmware/devicetree/base/soc/qcom,qupv3_1_geni_se@ac0000/i2c@a94000/bq27z561_standlone@55'
        self.link('sys/bus/i2c/devices/5-0055/of_node',dt)
        self.put(dt+'/compatible','ti,bq27z561_master\0');self.put(dt+'/status','ok\0');self.put(dt+'/ic_role','\0\0\0\0')
        self.put('sys/bus/i2c/devices/5-006e/of_node/compatible','sc8585_master\0')
        self.put('sys/bus/i2c/devices/5-006e/of_node/status','ok\0')
        self.put('sys/bus/platform/devices/soc:strategy-fg/of_node/fg_type','\0\0\0\0')
        self.put('sys/bus/platform/devices/soc:strategy-fg/of_node/adapt_power','\0\0\0d')
        self.link('sys/bus/platform/devices/soc:pmic-glink/driver','sys/bus/platform/drivers/pmic_glink')
        self.link('sys/bus/platform/drivers/pmic_glink/module','sys/module/qti_pmic_glink')
        self.run_script('load-hardware.sh',True)
        for n in ['sys.r97.battery.check','sys.r97.adsp.check','sys.r97.hardware.modules']:
            self.assertEqual((self.root/'props'/n).read_text(),'1')
        self.assertFalse((self.root/'props/sys.r97.battery.ready').exists())
    def test_wrong_adsp_is_never_started(self):
        self.put('sys/class/remoteproc/remoteproc1/name','32300000.remoteproc-cdsp\n')
        self.put('sys/class/remoteproc/remoteproc1/state','offline\n')
        self.run_script('start-adsp.sh',False)
        self.assertEqual((self.root/'sys/class/remoteproc/remoteproc1/state').read_text(),'offline\n')
        self.assertFalse((self.root/'props/twrp.adsp.ready').exists())
    def adsp(self,duplicate=False):
        parent=self.root/'sys/devices/platform/soc/3000000.remoteproc-adsp'
        node=parent/'remoteproc/remoteproc7';node.mkdir(parents=True)
        for n,s in [('name','3000000.remoteproc-adsp'),('firmware','adsp.mdt'),('state','running')]:self.put(str((node/n).relative_to(self.root)),s)
        dt=self.root/'sys/firmware/devicetree/base/soc/remoteproc-adsp@03000000';dt.mkdir(parents=True)
        (dt/'compatible').write_bytes(b'qcom,canoe-adsp-pas\0');(parent/'of_node').symlink_to(dt)
        cls=self.root/'sys/class/remoteproc';cls.mkdir(parents=True);(cls/'remoteproc7').symlink_to(node)
        if duplicate:(cls/'remoteproc8').symlink_to(node)
    def test_adsp_nonfixed_index(self):
        self.adsp();self.run_script('start-adsp.sh',True)
        self.assertEqual((self.root/'props/twrp.adsp.ready').read_text(),'true')
    def test_duplicate_adsp_rejected(self):
        self.adsp(True);self.run_script('start-adsp.sh',False)
        self.assertFalse((self.root/'props/twrp.adsp.ready').exists())
    def test_offline_without_firmware_no_write(self):
        self.adsp();state=self.root/'sys/devices/platform/soc/3000000.remoteproc-adsp/remoteproc/remoteproc7/state'
        state.write_text('offline');self.run_script('start-adsp.sh',False)
        self.assertEqual(state.read_text(),'offline')
    def link(self,name,target):
        p=self.root/name;q=self.root/target;p.parent.mkdir(parents=True,exist_ok=True);q.mkdir(parents=True,exist_ok=True);p.symlink_to(q)
    def battery(self,cap='96'):
        self.link('sys/bus/i2c/devices/5-0055/driver','sys/bus/i2c/drivers/bq27z561')
        self.link('sys/bus/i2c/drivers/bq27z561/module','sys/module/bq27z561')
        self.link('sys/bus/platform/devices/soc:strategy-fg/driver','sys/bus/platform/drivers/strategy_fg')
        self.link('sys/bus/platform/drivers/strategy_fg/module','sys/module/mca_strategy_fg_comp')
        self.link('sys/bus/platform/devices/soc:mca_business_battery/driver','sys/bus/platform/drivers/business_battery')
        self.link('sys/bus/platform/drivers/business_battery/module','sys/module/mca_business_battery_comp')
        real='sys/devices/platform/soc/soc:mca_business_battery/power_supply/battery'
        self.link('sys/class/power_supply/battery',real)
        for n,v in [('type','Battery'),('present','1'),('capacity',cap)]:self.put(real+'/'+n,v)
    def test_real_battery_node_gate(self):
        self.battery();self.run_script('wait-battery.sh',True)
        self.assertEqual((self.root/'props/sys.r97.battery.ready').read_text(),'1')
    def test_battery_out_of_range_not_ready(self):
        self.battery('101');self.run_script('wait-battery.sh',False)
        self.assertFalse((self.root/'props/sys.r97.battery.ready').exists())
    def test_missing_battery_not_faked(self):
        self.run_script('wait-battery.sh',False)
        self.assertFalse((self.root/'props/sys.r97.battery.ready').exists())
if __name__=='__main__':unittest.main()
