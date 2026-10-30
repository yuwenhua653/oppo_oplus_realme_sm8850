#!/usr/bin/env python3
"""Check exact Git objects and post-setup source bytes before compiling init."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

def identity(data):
    return {'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest(),
            'git_blob':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()}

def inspect_source(root, stage, lock):
    if stage not in ('baseline', 'patched'):
        raise ValueError('unknown init source stage')
    core = Path(root)/'system/core'
    report = {'stage':stage, 'status':'FAIL', 'files':{}, 'errors':[], 'flash_qualified':False}
    def git(*args):
        return subprocess.check_output(['git','-C',str(core),*args],text=True).strip()
    report['head'] = git('rev-parse','HEAD')
    if report['head'] != lock['system_core_commit']:
        report['errors'].append('system/core commit mismatch')
    for name, prefix in [('selinux.cpp','selinux'),('Android.bp','android_bp')]:
        relative = 'init/'+name
        path = core/relative
        current = identity(path.read_bytes())
        current['head_git_blob'] = git('rev-parse','HEAD:'+relative)
        current['expected_head_git_blob'] = lock['baseline_'+prefix+'_git_blob']
        report['files'][relative] = current
        if path.is_symlink():
            report['errors'].append('source symlink: '+relative)
        if current['head_git_blob'] != lock['baseline_'+prefix+'_git_blob']:
            report['errors'].append('pinned Git blob mismatch: '+relative)
        key = 'candidate_selinux_sha256' if stage == 'patched' and prefix == 'selinux' else 'baseline_'+prefix+'_sha256'
        current['expected_sha256'] = lock[key]
        current['expected_bytes'] = lock[key.replace('_sha256','_bytes')]
        if current['sha256'] != lock[key]:
            report['errors'].append('source byte mismatch: '+relative)
        if current['bytes'] != current['expected_bytes']:
            report['errors'].append('source length mismatch: '+relative)
        if key.startswith('baseline_') and current['git_blob'] != lock['baseline_'+prefix+'_git_blob']:
            report['errors'].append('worktree Git blob mismatch: '+relative)
    report['status'] = 'FAIL' if report['errors'] else 'PASS'
    return report

def check_source(root, stage, lock, output=None):
    report = inspect_source(root, stage, lock)
    if output:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+'\n')
        core = Path(root)/'system/core'
        for name in ('selinux.cpp','Android.bp'):
            output.with_suffix('.'+name).write_bytes((core/'init'/name).read_bytes())
        diff = subprocess.check_output(['git','-C',str(core),'diff','--binary','HEAD','--','init/selinux.cpp','init/Android.bp'])
        output.with_suffix('.diff').write_bytes(diff)
    if report['errors']:
        raise ValueError('; '.join(report['errors']))
    return report

if __name__ == '__main__':
    lock = json.loads((HERE/'source-lock.json').read_text())
    result = check_source(Path(sys.argv[1]),sys.argv[2],lock,Path(sys.argv[3]))
    print(json.dumps({'status':result['status'],'stage':result['stage'],'files':result['files']}))
