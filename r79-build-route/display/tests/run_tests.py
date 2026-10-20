#!/usr/bin/env python3
"""Compile production C bodies; target structs/API declarations are also pinned.
Hardware substitutes model transactions and fail selected operations explicitly.
"""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = root/'payload/qcom/opensource/display-drivers/msm/dsi'
tests = root/'tests'
fixtures = tests/'fixtures'
with tempfile.TemporaryDirectory(prefix='r79-flatmode-') as name:
    tmp = Path(name)
    fake = (fixtures/'fake_kernel_base.h').read_text()
    begin = fake.index('struct device_node{')
    end = fake.index('\n',fake.index('struct dsi_display{',begin))
    fake = fake[:begin] + (tests/'fake_display.h').read_text() + fake[end:]
    (tmp/'fake_kernel.h').write_text(fake)
    code = '\n'.join(line for line in (src/'myron_mi_clone.c').read_text().splitlines() if not line.startswith('#include'))
    (tmp/'candidate.c').write_text('#include "fake_kernel.h"\n#include "myron_mi_clone_state.h"\n#include "myron_flatmode.h"\n'+code)
    for p in (fixtures/'myron_mi_clone_state.h',fixtures/'mi_disp.h',src/'myron_flatmode.h'):
        (tmp/p.name).write_bytes(p.read_bytes())
    base = (fixtures/'test_clone_base.c').read_text().replace('int main(void)','int run_base_tests(void)',1)
    (tmp/'test.c').write_text(base+'\n'+(tests/'test_flatmode.c').read_text())
    command = ['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-variable',
        '-Wno-misleading-indentation','-Wno-missing-field-initializers','-fsanitize=address,undefined',
        '-fno-omit-frame-pointer',str(tmp/'test.c'),'-o',str(tmp/'test')]
    subprocess.run(command,check=True)
    # LeakSanitizer cannot inspect /proc tasks in this executor. The fake
    # allocator independently asserts zero live allocations after detach.
    subprocess.run([str(tmp/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
