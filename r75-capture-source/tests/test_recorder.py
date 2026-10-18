"""Exercise the unchanged once-per-run boundary and faster cadence with a fake clock."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest
from test_core_capture import ROOT,BOOT,TOKEN

class RecorderTests(unittest.TestCase):
    def test_two_second_start_cadence_and_immutable_claim_without_device(self):
        with tempfile.TemporaryDirectory(prefix='r75-recorder-') as temporary:
            root=Path(temporary);clock=root/'proc/uptime';clock.parent.mkdir(parents=True);clock.write_text('100.0 0.0\n')
            boot=root/'proc/sys/kernel/random/boot_id';boot.parent.mkdir(parents=True);boot.write_text(BOOT+'\n')
            directory=root/'data/local/tmp'/('r75-charge-'+TOKEN);directory.mkdir(parents=True)
            text=(ROOT/'recorder.sh').read_text().replace('/data/local/tmp',str(root/'data/local/tmp')).replace('/proc/',str(root/'proc')+'/').replace('/system/bin/toybox ','').replace('/system/bin/sh','sh')
            (directory/'recorder.sh').write_text(text)
            # One-second fake frame, no sysfs or real device.
            snapshot='#!/bin/sh\nIFS=" " read -r now idle < "'+str(clock)+'"\nnow=${now%%.*}\nprintf "%s.0 0.0\\n" "$((now+1))" > "'+str(clock)+'"\nprintf "FAKE_FRAME_START=%s\\n" "$now"\n'
            (directory/'snapshot.sh').write_text(snapshot)
            bin_dir=root/'bin';bin_dir.mkdir()
            sleep=bin_dir/'sleep';sleep.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "'+str(root/'sleeps')+'"\nIFS=" " read -r now idle < "'+str(clock)+'"\nnow=${now%%.*}\nprintf "%s.0 0.0\\n" "$((now+$1))" > "'+str(clock)+'"\n');sleep.chmod(0o755)
            env=dict(os.environ,PATH=str(bin_dir)+os.pathsep+os.environ['PATH'])
            command=['sh',str(directory/'recorder.sh'),str(directory),TOKEN,BOOT]
            result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            log=(directory/'periodic.log').read_text();starts=re.findall(r'^FAKE_FRAME_START=([0-9]+)$',log,re.M)
            self.assertEqual(list(map(int,starts)),list(range(100,250,2)))
            self.assertEqual((root/'sleeps').read_text().splitlines(),['1']*75)
            self.assertIn('state=complete',(directory/'status').read_text())
            before={name:(directory/name).read_bytes() for name in ('claim','periodic.log','status')}
            again=subprocess.run(command,env=env,capture_output=True,text=True,timeout=3)
            self.assertEqual(again.returncode,68)
            self.assertEqual(before,{name:(directory/name).read_bytes() for name in before})

if __name__=='__main__':unittest.main(verbosity=2)
