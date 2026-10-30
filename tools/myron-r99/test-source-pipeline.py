#!/usr/bin/env python3
"""Exercise real inherited R97 adaptation plus exact-byte R99 source guards."""
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

from source_checks import check_source

HERE = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name,path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def main():
    prior = Path(sys.argv[1])
    inherited = load('r97_actual_compile_only',prior/'ci/apply-compile-only.py')
    selector = load('r99_actual_selector',HERE/'apply-selector.py')
    capture = load('r99_actual_capture',HERE/'inspect-init.py')
    original_lock = json.loads((HERE/'source-lock.json').read_text())
    cases = []
    with tempfile.TemporaryDirectory(prefix='r99-real-source-pipeline-') as tmp:
        root=Path(tmp);source=root/'source';core=source/'system/core';init=core/'init';init.mkdir(parents=True)
        for name in ('selinux.cpp','Android.bp'):
            shutil.copyfile(HERE/'selector/baseline'/name,init/name)
        def git(*args):
            return subprocess.check_output(['git','-C',str(core),*args],text=True).strip()
        git('init','-q');git('add','init')
        git('-c','user.name=R99 host fixture','-c','user.email=r99-fixture@example.invalid','commit','-qm','exact upstream source blobs')
        # This fixture's commit differs because it contains only two files. The
        # source blob/byte identities and all remaining production pins are real.
        lock={**original_lock,'system_core_commit':git('rev-parse','HEAD')}
        check_source(source,'baseline',lock);cases.append('exact_upstream_blob_bytes')
        device=source/'device/xiaomi/sm8850';shutil.copytree(prior/'reference/device',device)
        rec=source/'bootable/recovery';(rec/'etc').mkdir(parents=True);(rec/'twrpminui').mkdir()
        shutil.copyfile(prior/'reference/init.rc',rec/'etc/init.rc')
        shutil.copyfile(prior/'reference/events.cpp',rec/'twrpminui/events.cpp')
        inherited.apply(source)
        check_source(source,'baseline',lock);cases.append('real_inherited_compile_only_leaves_core_exact')
        for name in ('selinux.cpp','Android.bp'):
            path=init/name;before=path.read_bytes();path.write_bytes(before+b'\n')
            try:check_source(source,'baseline',lock,root/(name+'-rejected.json'))
            except ValueError:cases.append('reject_added_LF_'+name)
            else:raise AssertionError('historical extra LF accepted')
            path.write_bytes(before)
        controls=root/'controls';(controls/'selector').mkdir(parents=True)
        (controls/'source-lock.json').write_text(json.dumps(lock))
        shutil.copyfile(HERE/'selector/recovery-only-permissive.patch',controls/'selector/recovery-only-permissive.patch')
        with patch.object(selector,'HERE',controls),patch.object(sys,'argv',['apply-selector.py',str(source)]), contextlib.redirect_stdout(io.StringIO()):
            selector.main()
        check_source(source,'patched',lock);cases.append('actual_selector_after_real_inherited_pipeline')
        try:check_source(source,'baseline',lock)
        except ValueError:cases.append('patched_source_rejected_as_baseline')
        else:raise AssertionError('stage confusion accepted')
        # Capture failure must retain raw outputs before source/ELF checks.
        # Deliberately non-ELF fixture data cannot become a qualified binary.
        product=source/'out/target/product/sm8850'
        for path in ('recovery/root/system/bin/init','symbols/recovery/root/system/bin/init'):
            target=product/path;target.parent.mkdir(parents=True);target.write_bytes(b'UNQUALIFIED HOST DIAGNOSTIC FIXTURE\n')
        evidence=root/'evidence';deliver=root/'deliver'
        with patch.object(capture,'HERE',controls):
            try:capture.capture('baseline',source,evidence,deliver)
            except ValueError:pass
            else:raise AssertionError('wrong-stage diagnostic fixture qualified')
            assert (deliver/'baseline/init').read_bytes()==b'UNQUALIFIED HOST DIAGNOSTIC FIXTURE\n'
            assert (deliver/'baseline/init.unstripped.raw').is_file()
            assert (evidence/'baseline-capture-failure.json').is_file()
            assert not (evidence/'baseline-init.json').exists()
            cases.append('failed_baseline_retains_unqualified_binary_and_source_evidence')
            try:capture.capture('patched',source,evidence,deliver)
            except ValueError:pass
            else:raise AssertionError('non-ELF diagnostic fixture qualified')
            assert (deliver/'baseline/init').is_file() and (deliver/'patched/init').is_file()
            assert not (evidence/'patched-init.json').exists()
            cases.append('second_failure_retains_both_stages_without_success_metadata')
        assert original_lock['baseline_init_sha256']=='34a9c7b745adc3a8a34b78f920d72d819924b9e48c5660f17e164eeaca4a0cce'
        assert original_lock['baseline_init_bytes']==2760632
        cases.append('known_binary_qualification_unchanged')
    print(json.dumps({'status':'PASS','cases':cases,'count':len(cases),'android_build_performed':False}))

if __name__ == '__main__':
    main()
