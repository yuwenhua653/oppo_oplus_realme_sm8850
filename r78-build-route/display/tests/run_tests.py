#!/usr/bin/env python3
import os,pathlib,subprocess,tempfile
root=pathlib.Path(__file__).resolve().parent.parent
src=root/'payload/qcom/opensource/display-drivers/msm/dsi'
with tempfile.TemporaryDirectory(prefix='r78-clone-test-') as d:
 p=pathlib.Path(d)
 code=(src/'myron_mi_clone.c').read_text()
 code='\n'.join(line for line in code.splitlines() if not line.startswith('#include'))
 (p/'candidate.c').write_text('#include "fake_kernel.h"\n#include "myron_mi_clone_state.h"\n'+code)
 for filename,source in [('mi_disp.h',root/'reference/mi_disp.h'),('fake_kernel.h',root/'tests/fake_kernel.h'),('test_clone.c',root/'tests/test_clone.c'),('myron_mi_clone_state.h',src/'myron_mi_clone_state.h')]:
  (p/filename).write_bytes(source.read_bytes())
 subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-variable','-Wno-misleading-indentation','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(p/'test_clone.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
