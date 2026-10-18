#!/usr/bin/env python3
"""Compile the complete unmodified candidate translation unit against host primitives."""
import argparse, hashlib, json, os, pathlib, re, shutil, subprocess
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent.parent
ap=argparse.ArgumentParser();ap.add_argument('--source',type=pathlib.Path,default=ROOT/'payload/drivers/power/supply/mca/mca_common/mca_adsp_glink.c');ap.add_argument('--output',type=pathlib.Path,default=ROOT/'test-output');ap.add_argument('--header',type=pathlib.Path,required=True);args=ap.parse_args()
source=args.source.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
text=source.read_text();stubs=out/'stubs';stubs.mkdir(exist_ok=True)
for inc in re.findall(r'^#include <([^>]+)>',text,re.M):
 p=stubs/inc;p.parent.mkdir(parents=True,exist_ok=True)
 if inc=='mca/common/mca_adsp_glink.h':p.write_bytes((ROOT/'reference/mca_adsp_glink.h').read_bytes())
 elif inc=='linux/soc/qcom/qti_pmic_glink.h':p.write_bytes(args.header.read_bytes())
 else:p.write_text('#include "fake_kernel.h"\n')
# The source is copied verbatim, not reimplemented or reduced to a model.
p=out/'production_under_test.c';p.write_bytes(source.read_bytes())
cc=shutil.which('gcc');assert cc, 'GCC required'
flags=['-std=gnu11','-Wstrict-prototypes','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined','-fno-omit-frame-pointer']
cmd=[cc,*flags,'-I'+str(stubs),'-I'+str(HERE),'-I'+str(out),str(HERE/'test_transport.c'),'-o',str(out/'test_transport')]
build=subprocess.run(cmd,text=True,capture_output=True);(out/'compile.log').write_text(build.stdout+build.stderr)
if build.returncode:print(build.stdout+build.stderr);raise SystemExit(build.returncode)
env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
run=subprocess.run([str(out/'test_transport')],text=True,capture_output=True,env=env,timeout=30)
(out/'run.log').write_text(run.stdout+run.stderr)
report={'status':'PASS' if run.returncode==0 else 'FAIL','source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'header_sha256':hashlib.sha256(args.header.read_bytes()).hexdigest(),'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],'compiler_flags':flags,'actual_whole_translation_unit':True,'exit_code':run.returncode,'test_stdout':run.stdout,'limitations':['Host pthread-backed kernel primitives, not a target kernel build or live ADSP protocol test.','ASan and UBSan enabled; LeakSanitizer disabled because probe/list lifetime is explicitly outside this fixture scope.','No runtime load, image modification, firmware operation, CI, or remote repository write.','The pmic_glink_write stub models return/callback interleavings; it does not establish lower-layer send latency or unregister quiescence.']}
(out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(run.returncode)
