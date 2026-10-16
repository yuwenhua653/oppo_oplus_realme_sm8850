#!/usr/bin/env python3
"""Compile the entire independent driver with bounded Linux API mocks."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,tempfile
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,default=HERE.parent/'source/drivers/power/supply/myron_bq_readonly.c')
a=p.parse_args();source=a.source.resolve();s=source.read_text()
# Only Linux headers, no private donor source/headers or indirect old-driver source.
headers=re.findall(r'^#include\s+<([^>]+)>',s,re.M)
assert len(headers)==12 and all(h.startswith('linux/') for h in headers)
assert not re.search(r'^#include\s+"',s,re.M)
assert 'MODULE_DEVICE_TABLE' not in s
assert dict(re.findall(r'#define (MYRON_REG_[A-Z_]+)\s+(0x[0-9a-f]+)',s)) == {'MYRON_REG_SOC':'0x2c','MYRON_REG_VOLTAGE':'0x08','MYRON_REG_TEMPERATURE':'0x06','MYRON_REG_BATTERY_STATUS':'0x0a','MYRON_REG_CURRENT':'0x0c'}
code=re.sub(r'/\*.*?\*/','',s,flags=re.S)
assert len(re.findall(r'i2c_smbus_read_word_data\(',code))==4
for forbidden in ('i2c_smbus_write','i2c_transfer','i2c_master_send','i2c_new','device_release_driver','device_bind_driver','driver_override','schedule_work','queue_delayed_work','set_property','property_is_writeable','POWER_SUPPLY_PROP_PRESENT','POWER_SUPPLY_PROP_ONLINE','i2c_smbus_read_byte','i2c_smbus_read_i2c_block'):
 assert forbidden not in code,forbidden
assert re.search(r'static bool enable_readonly;',s)
assert 'module_param(enable_readonly, bool, 0444);' in s
assert 'module_param(enable_extended_readonly, bool, 0444);' in s
assert 'static bool enable_extended_readonly;' in s
assert not re.search(r'\.remove\s*=|\.shutdown\s*=|\.pm\s*=',s)
with tempfile.TemporaryDirectory(prefix='myron-readonly-') as td:
 t=Path(td);inc=t/'include';(inc/'linux').mkdir(parents=True)
 (inc/'fake_kernel.h').write_bytes((HERE/'fake_kernel.h').read_bytes())
 for h in headers:(inc/h).write_text('#include "fake_kernel.h"\n')
 # Entire production translation unit, no slicing out inconvenient functions.
 (t/'test.c').write_text(s+'\n'+(HERE/'cases.c').read_text())
 cmd=['cc','-std=gnu11','-g','-O1','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-function','-Wno-misleading-indentation','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(inc),str(t/'test.c'),'-o',str(t/'test')]
 compiled=subprocess.run(cmd,capture_output=True,text=True)
 if compiled.returncode:
  raise RuntimeError('Standalone driver host compilation failed:\n'+compiled.stderr)
 r=subprocess.run([str(t/'test')],check=True,capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
assert 'TOTAL 44 standalone driver fixture groups passed' in r.stdout
print(json.dumps({'passed':True,'host_fixture_groups':44,'production_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'entire_source_compiled':True,'sanitizers':['address','undefined'],'leak_sanitizer':False,'leak_sanitizer_reason':'Host /proc task enumeration unavailable; explicit ownership and devres assertions retained.','kernel_compilation':False,'device_tested':False,'uses_old_driver_source_or_headers':False,'output':r.stdout}))
