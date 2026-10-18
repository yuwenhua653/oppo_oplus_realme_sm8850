"""R75 host utilities. Python standard library; never requests device privilege."""
import hashlib,json,os,re,shlex,shutil,subprocess,time,uuid
from pathlib import Path
from r75_pins import PRODUCT, KERNEL, BASE_BUILD, TEST_BUILD, PARTITION_BYTES, BASE_SHA, TEST_SHA, NATIVE_SHA, SOURCE_BUILDS
BOOT_RE=re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
SERIAL_RE=re.compile(r'[A-Za-z0-9._:-]{1,128}')
SHA_RE=re.compile(r'[0-9a-f]{64}')
IDENTITY = """printf 'boot_id='; cat /proc/sys/kernel/random/boot_id
printf 'product='; getprop ro.product.device
printf 'kernel='; uname -r
printf 'slot='; getprop ro.boot.slot_suffix
printf 'boot_completed='; getprop sys.boot_completed
printf 'modules_ready='; getprop vendor.all.modules.ready
printf 'bootmode='; getprop ro.bootmode
printf 'recovery='; getprop init.svc.recovery
printf 'twrp='; getprop ro.twrp.version
printf 'uptime='; cat /proc/uptime
printf 'boot_id_end='; cat /proc/sys/kernel/random/boot_id"""
class Stop(RuntimeError):pass
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def atomic_json(path,data):
 path=Path(path);tmp=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
 with tmp.open('x',encoding='utf-8',newline='\n') as f:
  json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def kv(text):
 d={}
 for line in text.splitlines():
  if '=' not in line:continue
  k,v=line.split('=',1)
  if k in d:raise Stop('Duplicate identity/status key: '+k)
  d[k]=v.strip()
 return d
def check_identity(d):
 if d.get('product')!=PRODUCT or d.get('kernel')!=KERNEL:raise Stop('Device product/kernel differs from this package')
 if d.get('slot') not in ('_a','_b'):raise Stop('Current A/B slot unavailable')
 if not BOOT_RE.fullmatch(d.get('boot_id','')) or d.get('boot_id_end')!=d['boot_id']:raise Stop('Boot ID missing/changed within identity read')
 if d.get('bootmode') in ('recovery','fastboot') or d.get('recovery')=='running' or d.get('twrp'):raise Stop('Normal Android required')

def native_build(text,boot):
 return sorted(set(build for build,bid in re.findall(r'R36_PROBE build_id=(\S+).*?\bboot_id=([0-9a-f-]{36})\b',text) if bid==boot))
def tool(name,root,override=None):
 if override:
  p=Path(override).resolve()
  if not p.is_file():raise Stop('Missing tool: '+str(p))
 else:
  p=next((p for p in [root/'platform-tools'/(name+'.exe'),root/(name+'.exe'),root/'platform-tools'/name] if p.is_file()),None)
  if p is None:
   found=shutil.which(name)
   if not found:raise Stop(name+' unavailable; use official platform-tools')
   p=Path(found)
 if os.name=='nt' and p.suffix.lower()!='.exe':raise Stop('Windows tool must be an .exe, not a batch file')
 return str(p.resolve())

def load_package(root):
 if not SHA_RE.fullmatch(TEST_SHA or '') or not SHA_RE.fullmatch(NATIVE_SHA or ''):raise Stop('R75 image/native pins are not frozen; no device action permitted')
 p=root/'r75-package.json';m=json.loads(p.read_text(encoding='utf-8'))
 if m.get('schema')!=1 or m.get('product')!=PRODUCT or m.get('kernel')!=KERNEL or m.get('baseline_build')!=BASE_BUILD or m.get('test_build')!=TEST_BUILD:raise Stop('Package identity mismatch')
 if m.get('source_builds')!=list(SOURCE_BUILDS):raise Stop('Package permitted source builds mismatch')
 if m.get('image_pin_status')!='READY_REVIEWED_R75':raise Stop('R75 package is not frozen')
 if m.get('partition_bytes')!=PARTITION_BYTES:raise Stop('Package partition geometry mismatch')
 for name,path in [('test','test/vendor_boot.img'),('rollback','rollback/vendor_boot_r74.img')]:
  x=m.get('images',{}).get(name,{})
  if x.get('path')!=path or x.get('bytes')!=PARTITION_BYTES or not SHA_RE.fullmatch(x.get('sha256','')):raise Stop('Package image metadata invalid: '+name)
 if m['images']['rollback']['sha256']!=BASE_SHA:raise Stop('Rollback is not the known bootable R74 image')
 if m['images']['test']['sha256']!=TEST_SHA:raise Stop('Test image is not this reviewed R75 candidate')
 if m.get('native_contract_sha256')!=NATIVE_SHA or sha(root/'native-contract.json')!=NATIVE_SHA:raise Stop('Native contract SHA mismatch')
 return m

def verify_image(root,item):
 original=root/item['path']
 if original.is_symlink():raise Stop('Image cannot be a symlink')
 p=original.resolve()
 if not p.is_relative_to(root.resolve()) or not p.is_file() or p.is_symlink():raise Stop('Image missing/outside package')
 if p.stat().st_size!=item['bytes'] or sha(p)!=item['sha256']:raise Stop('Image size/SHA mismatch: '+item['path'])
 return p
class Runner:
    """Retain bounded stdout/stderr on disk, kill a stalled local adb client."""
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.records = []

    def run(self, label, argv, seconds=8, limit=1048576, extra=()):
        if not re.fullmatch(r'[a-z0-9_-]+', label) or seconds <= 0 or limit <= 0:
            raise ValueError('Invalid command limits/label')
        paths = [self.folder / ('%03d-%s%s' % (len(self.records), label, suffix))
                 for suffix in ('.txt', '.stderr.txt')]
        record = {'label': label, 'argv': [str(arg) for arg in argv],
                  'timeout_seconds': seconds, 'stream_limit_bytes': limit,
                  'files': [path.name for path in paths]}
        self.records.append(record)
        start, process = time.monotonic(), None
        try:
            if len(subprocess.list2cmdline(record['argv'])) > 24000:
                raise Stop('Command exceeds Windows length bound')
            with paths[0].open('xb') as out, paths[1].open('xb') as err:
                process = subprocess.Popen(record['argv'], stdin=subprocess.DEVNULL,
                                           stdout=out, stderr=err, shell=False)
                while process.poll() is None:
                    if time.monotonic() - start >= seconds:
                        record['error'] = 'timeout'
                        break
                    if any(path.exists() and path.stat().st_size > cap for path,cap in [(p,limit) for p in paths]+list(extra)):
                        record['error'] = 'output_limit'
                        break
                    time.sleep(0.03)
                if process.poll() is None:
                    process.kill()
                record['returncode'] = process.wait(timeout=2)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            record['error'] = str(error)
        except KeyboardInterrupt:
            record['error'] = 'operator_interrupt'
            raise
        finally:
            if process and process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=2)
                except (subprocess.TimeoutExpired, KeyboardInterrupt):
                    record['cleanup_error'] = 'local client killed; wait interrupted or incomplete'
            for path,cap in [(p,limit) for p in paths]+list(extra):
                if path.exists() and path.stat().st_size > cap:
                    with path.open('r+b') as stream:
                        stream.truncate(cap)
                    record['error'] = 'output_limit'
            record['elapsed_seconds'] = round(time.monotonic() - start, 3)
            record['ok'] = record.get('returncode') == 0 and not record.get('error')
            record['stdout'] = paths[0].read_text(encoding='utf-8', errors='replace') if paths[0].exists() else ''
            record['stderr'] = paths[1].read_text(encoding='utf-8', errors='replace') if paths[1].exists() else ''
        return record

    def must(self, *args, **kwargs):
        record = self.run(*args, **kwargs)
        if not record['ok']:
            raise Stop(record['label'] + ' failed: ' + record.get('error', 'exit ' + str(record.get('returncode'))))
        return record

    def summary(self):
        return [{key: value for key, value in record.items() if key not in ('stdout', 'stderr')}
                for record in self.records]

def bounded_shell(body, seconds):
    if not 1 <= seconds <= 60:
        raise ValueError('Invalid device timeout')
    return '/system/bin/toybox timeout -k 1 ' + str(seconds) + ' sh -c ' + shlex.quote(body)


def shell_guard(body, boot, seconds):
    if not BOOT_RE.fullmatch(boot):
        raise Stop('Invalid boot guard')
    guard = ('observed_boot=$(cat /proc/sys/kernel/random/boot_id); boot_rc=$?; '
             '[ "$boot_rc" = 0 ] && [ -n "$observed_boot" ] || '
             '{ echo R75_BOOT_UNAVAILABLE >&2; exit 88; }; '
             '[ "$observed_boot" = ' + shlex.quote(boot) + ' ] || '
             '{ echo R75_BOOT_CHANGED >&2; exit 89; }; ')
    return bounded_shell(guard + body + '\ncommand_rc=$?; ' + guard + 'exit "$command_rc"', seconds)
