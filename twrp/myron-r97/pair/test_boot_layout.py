#!/usr/bin/env python3
"""Exercise production PID1 empty_dir() against exact Recovery image layouts.

This host test reads real images and creates only a private temporary directory.
It neither changes PID1 source nor mounts, boots or flashes the images.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

NATIVE_SHA = '326c784a750db829c1dd89af0190e5f6847bf34d358b9ab8c0c5b3ade2eb00fc'
R95_SHA = 'ed4b2d1d54ab4c8b381d7ccc989e5b3d93666b86f6e0553540b70e76dc5adfdc'
R97_SHA = 'a6c948213c352690dac05b12ea7aee4b55566d75d7a198be4403e5410f16dd01'
ENTRY = 'vendor_dlkm/etc'
TARGET = b'/vendor/vendor_dlkm/etc'

C_TEST = r'''
#define R36_UNIT_TEST
#include "r36_init.c"

/* On an unprivileged CI host, normalize only the owner numbers observed by
 * secure_dir(). opendir/readdir, actual mode and st_dev remain real syscalls.
 * Root-host runs use the original lstat with no normalization. */
static int fixture_lstat(const char *p,struct stat *s){
 int r=lstat(p,s);
 if(!r){s->st_uid=0;s->st_gid=0;}
 return r;
}
int main(int argc,char **argv){
 struct stat st;char log[16384];int expected,rc,e,fd;ssize_t n;
 if(argc!=4)return 90;
 expected=atoi(argv[2]);
 if(lstat(argv[1],&st))return 91;
 if(getuid()!=0||getgid()!=0)call.lstat_fn=fixture_lstat;
 fd=open(argv[3],O_RDWR|O_CREAT|O_TRUNC,0600);if(fd<0)return 92;
 reportfd=fd;errno=0;rc=empty_dir(argv[1],st.st_dev);e=errno;
 if(lseek(fd,0,SEEK_SET)<0)return 93;
 n=read(fd,log,sizeof(log)-1);if(n<0)return 94;log[n]=0;
 if(close(fd))return 95;
 reportfd=-1;
 if(report_error)return 96;
 printf("rc=%d errno=%d directory_not_empty=%d owner_normalized=%d\n",
        rc,e,strstr(log,"check=directory-not-empty")!=NULL,
        getuid()!=0||getgid()!=0);
 if(expected==0)return rc==0?0:10;
 return rc==-1&&e==EINVAL&&strstr(log,"check=directory-not-empty")?0:11;
}
'''

def need(condition, message):
    if not condition:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def load_reader(directory):
    path = Path(directory) / 'read_candidate.py'
    spec = importlib.util.spec_from_file_location('r98_layout_reader', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_image

def describe(entries):
    result = {}
    for name in ('system_dlkm', 'vendor_dlkm'):
        row = entries[name]
        need(stat.S_ISDIR(row['mode']) and row['uid'] == row['gid'] == 0,
             'root-owned mountpoint directory: ' + name)
        need(row['mode'] & 0o777 == 0o755, 'mountpoint mode: ' + name)
        result[name] = sorted(p for p in entries if p.startswith(name + '/'))
    return result

def test(native, reader, r95, r97, r98=None):
    native = Path(native).resolve()
    need(sha((native / 'r36_init.c').read_bytes()) == NATIVE_SHA,
         'exact production baseline native source')
    read_image = load_reader(reader)
    b95, e95 = read_image(r95)
    b97, e97 = read_image(r97)
    need(sha(b95) == R95_SHA, 'exact R95 Recovery')
    need(sha(b97) == R97_SHA, 'exact issued R97 Recovery')
    d95, d97 = describe(e95), describe(e97)
    need(d95 == {'system_dlkm': [], 'vendor_dlkm': []}, 'known R95 layout')
    need(d97 == {'system_dlkm': [], 'vendor_dlkm': [ENTRY]}, 'known R97 regression layout')
    link = e97[ENTRY]
    need(stat.S_ISLNK(link['mode']) and link['data'] == TARGET,
         'exact unexpected R97 symlink')
    cases = []
    with tempfile.TemporaryDirectory(prefix='r98-production-layout-') as tmp:
        root = Path(tmp)
        source, executable = root / 'test.c', root / 'test'
        source.write_text(C_TEST)
        subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra',
                        '-Werror', '-Wno-unused-function', '-fsanitize=address,undefined',
                        '-fno-omit-frame-pointer', '-no-pie', '-I', str(native),
                        str(source), '-o', str(executable)], check=True)
        env = {**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0:abort_on_error=1',
               'UBSAN_OPTIONS': 'halt_on_error=1'}
        mountpoint = root / 'vendor_dlkm'
        mountpoint.mkdir(mode=0o755)
        mountpoint.chmod(0o755)

        def run(name, expected):
            result = subprocess.run([str(executable), str(mountpoint), str(expected),
                                     str(root / 'probe.log')], check=True, capture_output=True,
                                    text=True, env=env)
            cases.append({'case': name, 'production_result': result.stdout.strip()})

        run('actual_R95_empty_vendor_dlkm', 0)
        (mountpoint / 'etc').symlink_to(link['data'].decode())
        run('actual_R97_symlink_reproduces_directory_not_empty', -1)
        # Matching directory records from another CPIO do not delete this link.
        mountpoint.mkdir(exist_ok=True)
        mountpoint.chmod(0o755)
        run('later_same_type_directory_record_does_not_clear_child', -1)
        (mountpoint / 'etc').unlink()
        run('remove_only_confirmed_symlink_restores_empty_contract', 0)
        (mountpoint / 'unexpected').write_bytes(b'x')
        run('unrelated_nonempty_content_still_rejected', -1)

        if r98:
            b98, e98 = read_image(r98)
            need(describe(e98) == d95, 'fixed Recovery mountpoint layout')
            (mountpoint / 'unexpected').unlink()
            run('actual_fixed_image_empty_vendor_dlkm', 0)
    return {'status': 'PASS_PRODUCTION_EMPTY_DIR_LAYOUT_REGRESSION',
            'native_source_sha256': NATIVE_SHA,
            'R95_recovery_sha256': sha(b95), 'R97_recovery_sha256': sha(b97),
            'fixed_recovery_sha256': sha(b98) if r98 else None,
            'R95_layout': d95, 'R97_layout': d97,
            'unexpected_entry': {'path': ENTRY, 'mode': oct(link['mode']),
                                 'target': TARGET.decode()},
            'cases': cases, 'PID1_modified': False, 'device_tested': False,
            'host_owner_normalization': os.getuid() != 0 or os.getgid() != 0}

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--native-dir', required=True)
    p.add_argument('--reader-dir', required=True)
    p.add_argument('--r95-image', required=True)
    p.add_argument('--r97-image', required=True)
    p.add_argument('--fixed-image')
    p.add_argument('--out', required=True)
    a = p.parse_args()
    result = test(a.native_dir, a.reader_dir, a.r95_image, a.r97_image, a.fixed_image)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
