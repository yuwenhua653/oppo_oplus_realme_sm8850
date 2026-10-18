#!/usr/bin/env python3
"""Build the complete production client against host kernel/lifetime primitives."""
import argparse, hashlib, json, os, pathlib, re, shutil, subprocess
HERE = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument('--source', type=pathlib.Path, default=HERE.parent/'candidate/drivers/power/supply/myron_mca_readonly/myron_mca_readonly.c')
ap.add_argument('--header', type=pathlib.Path, default=HERE/'qti_pmic_glink.h')
ap.add_argument('--output', type=pathlib.Path, default=HERE.parent/'test-output')
args=ap.parse_args();source=args.source.resolve();header=args.header.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
stubs=out/'stubs'
for inc in re.findall(r'^#include <([^>]+)>',source.read_text(),re.M):
 p=stubs/inc;p.parent.mkdir(parents=True,exist_ok=True)
 p.write_bytes(header.read_bytes() if inc=='linux/soc/qcom/qti_pmic_glink.h' else b'#include "fake_kernel.h"\n')
(stubs/'linux/types.h').write_text('#include "fake_kernel.h"\n')
(out/'production_under_test.c').write_bytes(source.read_bytes())
cc=shutil.which('gcc');assert cc
flags=['-std=gnu11','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-Wstrict-prototypes','-Wno-unused-parameter','-fsanitize=address,undefined','-fno-omit-frame-pointer']
cmd=[cc,*flags,'-I'+str(stubs),'-I'+str(HERE),'-I'+str(out),str(HERE/'test_client.c'),'-o',str(out/'test_client')]
build=subprocess.run(cmd,text=True,capture_output=True);(out/'compile.log').write_text(build.stdout+build.stderr)
if build.returncode:print(build.stdout+build.stderr);raise SystemExit(build.returncode)
run=subprocess.run([str(out/'test_client')],text=True,capture_output=True,timeout=30,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'))
(out/'run.log').write_text(run.stdout+run.stderr)
report={'status':'PASS' if run.returncode==0 else 'FAIL','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'public_header_sha256':hashlib.sha256(header.read_bytes()).hexdigest(),'actual_whole_production_translation_unit':True,'public_header_copied_verbatim':True,'config_qti_pmic_glink_enabled':True,'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],'flags':flags,'exit_code':run.returncode,'stdout':run.stdout,'stderr':run.stderr,'limits':['Host pthread-backed primitives, not target kernel/ADSP/hardware validation.','Transport stubs model registration early callback, sender blocking, callback drain and finite work scheduling. Actual lower-layer implementation is independently reviewed.','No TSan/lockdep. LeakSanitizer disabled for host primitive objects; ASan/UBSan enabled.']}
(out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(run.returncode)
