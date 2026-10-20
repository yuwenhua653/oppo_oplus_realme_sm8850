#!/usr/bin/env python3
"""Compile actual patched functions with fault-injection stubs, plus old-source counterchecks."""
import hashlib,json,os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REL=Path('drivers/input/touchscreen/xiaomi')
BASE=ROOT/'fixtures'
COMMON=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include "xiaomi_touch_type_common.h"
#define LOG_ERROR(...) ((void)0)
#define LOG_INFO(...) ((void)0)
#define LOG_DEBUG(...) ((void)0)
#define LOG_ALWAYS(...) ((void)0)
#define LOG_VERBOSE(...) ((void)0)
#define LOG_WARNING(...) ((void)0)
#define __user
#define PAGE_SHIFT 12
#define PAGE_SIZE (1UL << PAGE_SHIFT)
'''
TESTS={}
TESTS['publication']={'file':'xiaomi_touch_operations.c','functions':['xiaomi_touch_dev_open','xiaomi_touch_operation_init'],'before':r'''
typedef struct { int use_count; } xiaomi_touch_t;
typedef struct { int touch_id,poll_wait_queue_head,poll_wait_queue_head_for_cmd,poll_wait_queue_head_for_frame,poll_wait_queue_head_for_raw; } private_data_t;
struct inode {int unused;}; struct file {void *private_data;};
static xiaomi_touch_t *xiaomi_touch;
static int misc_dev, register_error, allocation_error, calls;
static int xiaomi_touch_dev_open(struct inode *,struct file *);
static void *kzalloc_retry(size_t n,int retries) { (void)retries; return allocation_error?NULL:calloc(1,n); }
static void init_waitqueue_head(int *p) { *p=1; }
static int misc_register(int *p) {
 struct file file={0}; (void)p; calls++;
 assert(xiaomi_touch != NULL); /* actual publication-before-open race */
 if(register_error) return register_error;
 assert(xiaomi_touch_dev_open(NULL,&file)==0);
 assert(((private_data_t *)file.private_data)->touch_id==-1);
 free(file.private_data);return 0;
}
''','after':r'''
int main(void) {
 xiaomi_touch_t state={0}; struct file f={0};
 assert(xiaomi_touch_operation_init(NULL)==-EINVAL && calls==0);
 assert(xiaomi_touch_dev_open(NULL,&f)==-ENODEV);
 register_error=-EBUSY;assert(xiaomi_touch_operation_init(&state)==-EBUSY && xiaomi_touch==NULL);
 register_error=0;assert(xiaomi_touch_operation_init(&state)==0 && xiaomi_touch==&state && state.use_count==1);
 puts("PASS misc publication ordering, null state and registration errno");return 0;
}
'''}
TESTS['mmap_bounds']={'file':'xiaomi_touch_operations.c','functions':['xiaomi_touch_dev_mmap'],'before':r'''
typedef unsigned long dma_addr_t;
typedef struct {int touch_id; unsigned char mmap_area;} private_data_t;
typedef struct {unsigned long frame_data_mmap_phy_base,raw_data_mmap_phy_base; unsigned int frame_data_size,raw_data_size;unsigned char frame_data_buf_size,raw_data_buf_size;} xiaomi_touch_data_t;
typedef struct {unsigned long input_event_time_line_phy_base;} xiaomi_touch_t;
struct file {void *private_data;};
struct vm_area_struct {unsigned long vm_start,vm_end,vm_pgoff,vm_page_prot;};
static xiaomi_touch_data_t data={0x100000,0x200000,PAGE_SIZE,PAGE_SIZE,2,3};
static xiaomi_touch_t state={0x300000},*xiaomi_touch=&state;
static int maps,remap_error;static unsigned long seen_page,seen_size,seen_prot;
#define PAGE_SHARED 0
static xiaomi_touch_data_t *get_xiaomi_touch_data(int id){return id==0?&data:NULL;}
static dma_addr_t get_report_point_info_phy_addr(void){return 0x400000;}
static int remap_pfn_range(struct vm_area_struct *v,unsigned long s,unsigned long p,unsigned long n,unsigned long prot){(void)v;(void)s;maps++;seen_page=p;seen_size=n;seen_prot=prot;return remap_error;}
''','after':r'''
int main(void){
 private_data_t client={0,1};struct file f={&client};struct vm_area_struct v={0x10000,0x11000,0,0x55};
 assert(xiaomi_touch_dev_mmap(&f,&v)==0&&maps==1&&seen_page==0x100&&seen_prot==0x55);
 v.vm_pgoff=1;assert(xiaomi_touch_dev_mmap(&f,&v)==0&&seen_page==0x101);
 maps=0;v.vm_end+=PAGE_SIZE;assert(xiaomi_touch_dev_mmap(&f,&v)==-EINVAL&&maps==0);
 v.vm_end-=PAGE_SIZE;v.vm_pgoff=2;assert(xiaomi_touch_dev_mmap(&f,&v)==-EINVAL&&maps==0);
 v.vm_pgoff=ULONG_MAX;assert(xiaomi_touch_dev_mmap(&f,&v)==-EINVAL&&maps==0);
 v.vm_pgoff=0;v.vm_end=v.vm_start;assert(xiaomi_touch_dev_mmap(&f,&v)==-EINVAL&&maps==0);
 v.vm_end=v.vm_start-1;assert(xiaomi_touch_dev_mmap(&f,&v)==-EINVAL&&maps==0);
 v.vm_end=v.vm_start+PAGE_SIZE;client.mmap_area=0;assert(xiaomi_touch_dev_mmap(&f,&v)==-EINVAL);
 client.mmap_area=1;client.touch_id=-1;assert(xiaomi_touch_dev_mmap(&f,&v)==-ENODEV);
 client.touch_id=0;data.frame_data_mmap_phy_base=0;assert(xiaomi_touch_dev_mmap(&f,&v)==-ENODEV);
 for(int area=2;area<=4;area++){client.mmap_area=area;assert(xiaomi_touch_dev_mmap(&f,&v)==0);}
 client.mmap_area=2;remap_error=-EAGAIN;assert(xiaomi_touch_dev_mmap(&f,&v)==-EAGAIN);
 puts("PASS allocation-bound mmap, overflow/invalid rejection, permission and errno propagation");return 0;
}
'''}
TESTS['mode_validation']={'file':'xiaomi_touch_mode.c','functions':['xiaomi_touch_mode'],'before':r'''
typedef struct {int touch_id;} private_data_t;
typedef struct { struct {int (*htc_ic_setModeValue)(common_data_t *);int (*htc_ic_getModeValue)(common_data_t *);} hardware_operation;} xiaomi_touch_driver_param_t;
static xiaomi_touch_driver_param_t backend;static int locks,queued,callback_calls,callback_error,copy_error;
static int ioctl_operation_mutex;
static void mutex_lock(int *p){(void)p;assert(locks==0);locks++;}
static void mutex_unlock(int *p){(void)p;assert(locks==1);locks--;}
static int copy_from_user(void *d,const void *s,size_t n){if(copy_error)return 1;memcpy(d,s,n);return 0;}
static int copy_to_user(void *d,const void *s,size_t n){memcpy(d,s,n);return 0;}
static xiaomi_touch_driver_param_t *get_xiaomi_touch_driver_param(int id){return id==0?&backend:NULL;}
static void add_common_data_to_buf(int id,int cmd,int mode,int len,int *v){(void)id;(void)cmd;(void)mode;(void)v;assert(len<=CMD_DATA_BUF_SIZE);queued++;}
static int hw(common_data_t *c){(void)c;callback_calls++;return callback_error;}
static void noop(common_data_t *c){(void)c;}
#define update_get_ic_current_value noop
#define xiaomi_touch_set_mode_value noop
#define xiaomi_touch_get_mode_value noop
#define xiaomi_touch_reset_mode noop
#define xiaomi_touch_get_mode_all noop
#define xiaomi_touch_set_mode_long_value noop
#define update_palm_sensor_value(x) ((void)(x))
#define update_palm_sensor_value_second_panel(x) ((void)(x))
#define sendnlmsg(x) ((void)(x))
''','after':r'''
int main(void){
 private_data_t client={0};common_data_t c={.touch_id=0,.cmd=SET_CMD_FOR_THP,.mode=27,.data_len=257};
 assert(xiaomi_touch_mode(&client,sizeof(c),(unsigned long)&c)==-EINVAL&&queued==0&&locks==0);
 c.data_len=65535;assert(xiaomi_touch_mode(&client,sizeof(c),(unsigned long)&c)==-EINVAL&&queued==0);
 c.data_len=256;assert(xiaomi_touch_mode(&client,sizeof(c),(unsigned long)&c)==0&&queued==1);
 c.cmd=SET_CUR_VALUE;c.data_len=0;assert(xiaomi_touch_mode(&client,sizeof(c),(unsigned long)&c)==-EINVAL);
 c.cmd=SET_THP_IC_CUR_VALUE;c.data_len=1;c.mode=3001;
 assert(xiaomi_touch_mode(&client,sizeof(c),(unsigned long)&c)==-EOPNOTSUPP&&callback_calls==0&&locks==0);
 backend.hardware_operation.htc_ic_setModeValue=hw;callback_error=-EIO;
 assert(xiaomi_touch_mode(&client,sizeof(c),(unsigned long)&c)==-EIO&&callback_calls==1&&locks==0);
 callback_error=0;assert(xiaomi_touch_mode(&client,sizeof(c),(unsigned long)&c)==0&&callback_calls==2&&locks==0);
 c.touch_id=1;assert(xiaomi_touch_mode(&client,sizeof(c),(unsigned long)&c)<0&&callback_calls==2);
 assert(xiaomi_touch_mode(&client,sizeof(c)-1,(unsigned long)&c)==-EINVAL);
 puts("PASS real v3 common_data layout, oversized/empty rejection, unsupported callback and hardware errno");return 0;
}
'''}
TESTS['probe_unwind']={'file':'xiaomi_touch_core.c','functions':['xiaomi_touch_probe'],'before':r'''
typedef struct {int unused;} xiaomi_touch_t;static xiaomi_touch_t xiaomi_touch;
struct platform_device {int unused;};
static int fail_stage,steps,active[6],undo_count,next_undo;
#define XIAOMI_TOUCH_VERSION "fixture"
static int init(int n){steps++;if(fail_stage==n)return n==3?1:-100-n;active[n]=1;return 0;}
static void undo(int n){assert(active[n]&&n==--next_undo);active[n]=0;undo_count++;}
static int xiaomi_touch_sys_init(void){return init(1);}
static int xiaomi_touch_operation_init(xiaomi_touch_t *p){(void)p;for(int n=1;n<=4;n++)assert(active[n]);return init(5);}
static int xiaomi_register_power_supply_event(xiaomi_touch_t *p){(void)p;return init(2);}
static int netlink_init(void){return init(3);}
static int xiaomi_touch_evdev_init(xiaomi_touch_t *p){(void)p;return init(4);}
static void xiaomi_touch_evdev_remove(void){undo(4);}
static void netlink_exit(void){undo(3);}
static void xiaomi_unregister_power_supply_event(void){undo(2);}
static void xiaomi_touch_operation_remove(void){undo(5);}
static void xiaomi_touch_sys_remove(void){undo(1);}
''','after':r'''
int main(void){
 for(int n=1;n<=5;n++){fail_stage=next_undo=n;steps=undo_count=0;memset(active,0,sizeof(active));int ret=xiaomi_touch_probe(NULL);assert(ret==(n==3?-ENOMEM:-100-n));assert(steps==n&&undo_count==n-1);for(int k=1;k<=5;k++)assert(!active[k]);}
 fail_stage=0;steps=0;assert(xiaomi_touch_probe(NULL)==0&&steps==5);for(int n=1;n<=5;n++)assert(active[n]);
 puts("PASS all five probe failures propagated, no false-bound missing node, exact reverse unwind");return 0;
}
'''}
TESTS['sysfs_errors']={'file':'xiaomi_touch_sys.c','functions':['xiaomi_touch_sys_init'],'before':r'''
struct class {int unused;};struct device{int kobj;};struct attrs{void *attrs;};
static struct class c,*xiaomi_touch_class;static struct device d,*xiaomi_touch_dev;
static struct attrs xiaomi_touch_attrs;static void *touch_attr_group;
static int fail_stage,destroys,classes;
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
static struct class *class_create(const char *s){(void)s;return fail_stage==1?(void *)(intptr_t)-ENOMEM:&c;}
static struct device *device_create(struct class *p,void *parent,int devt,void *data,const char *s){(void)parent;(void)devt;(void)data;(void)s;assert(p==&c);return fail_stage==2?(void *)(intptr_t)-ENODEV:&d;}
static int sysfs_create_group(int *p,struct attrs *a){(void)a;assert(p==&d.kobj);return fail_stage==3?-EIO:0;}
static void device_destroy(struct class *p,int devt){(void)devt;assert(p==&c);destroys++;}
static void class_destroy(struct class *p){assert(p==&c);classes++;}
''','after':r'''
int main(void){
 for(int n=1;n<=3;n++){fail_stage=n;destroys=classes=0;xiaomi_touch_class=NULL;xiaomi_touch_dev=NULL;int ret=xiaomi_touch_sys_init();assert(ret==(n==1?-ENOMEM:n==2?-ENODEV:-EIO));assert(xiaomi_touch_class==NULL&&xiaomi_touch_dev==NULL);assert(classes==(n>=2)&&destroys==(n==3));}
 fail_stage=0;assert(xiaomi_touch_sys_init()==0&&xiaomi_touch_class==&c&&xiaomi_touch_dev==&d);
 puts("PASS ERR_PTR class/device failures and sysfs rollback");return 0;
}
'''}
TESTS['queue_bounds']={'file':'xiaomi_touch_core.c','functions':['add_common_data_to_buf'],'before':r'''
#define COMMON_DATA_BUF_SIZE 10
#define COMMON_DATA_NOTIFY 0
typedef struct {int common_data_buf_index,common_data_buf_lock;common_data_t common_data_buf[10];} xiaomi_touch_data_t;
static xiaomi_touch_data_t state;static int notifications;
static xiaomi_touch_data_t *get_xiaomi_touch_data(int id){return id==0?&state:NULL;}
static int atomic_read(int *p){return *p;}static void atomic_inc(int *p){++*p;}static void atomic_set(int *p,int n){*p=n;}
static void mutex_lock(int *p){(void)p;}static void mutex_unlock(int *p){(void)p;}
static void notify_xiaomi_touch(xiaomi_touch_data_t *p,int what){(void)p;(void)what;notifications++;}
''','after':r'''
int main(void){
 int v[257];for(int i=0;i<257;i++)v[i]=i;
 add_common_data_to_buf(0,SET_CUR_VALUE,DATA_MODE_27,257,v);assert(notifications==0&&state.common_data_buf_index==0);
 add_common_data_to_buf(0,SET_CUR_VALUE,DATA_MODE_27,-1,v);assert(notifications==0);
 add_common_data_to_buf(0,SET_CUR_VALUE,DATA_MODE_27,1,NULL);assert(notifications==0);
 add_common_data_to_buf(0,SET_CUR_VALUE,DATA_MODE_27,256,v);assert(notifications==1&&state.common_data_buf[0].data_buf[255]==255);
 state.common_data_buf_index=0;add_common_data_to_buf(0,SET_CUR_VALUE,DATA_MODE_27,1,v);assert(state.common_data_buf[0].data_buf[255]==0);
 add_common_data_to_buf(0,SET_CUR_VALUE,DATA_MODE_27,0,NULL);assert(notifications==3);
 puts("PASS exact maximum queue length, invalid lengths, null source and stale-tail clearing");return 0;
}
'''}
TESTS['evdev_unwind']={'file':'xiaomi_touch_evdev.c','functions':['xiaomi_touch_evdev_init'],'before':r'''
typedef struct {int unused;} xiaomi_touch_t;static xiaomi_touch_t *xiaomi_touch;
static int xiaomitouch_input_handler,last_touch_events_seq_ops;
static struct last_touch_event {int unused;} last_touch_events;
static void *last_touch_events_pde;
static int register_result,proc_result=1,register_calls,proc_calls,unregister_calls;
static int input_register_handler(int *h){assert(h==&xiaomitouch_input_handler);register_calls++;return register_result;}
static void input_unregister_handler(int *h){assert(h==&xiaomitouch_input_handler);unregister_calls++;}
static void *proc_create_seq(const char *name,int mode,void *parent,int *ops){(void)name;(void)mode;(void)parent;(void)ops;proc_calls++;return proc_result?&last_touch_events_seq_ops:NULL;}
''','after':r'''
int main(void){
 xiaomi_touch_t state={0};register_result=-EIO;
 assert(xiaomi_touch_evdev_init(&state)==-EIO&&register_calls==1&&proc_calls==0&&unregister_calls==0);
 register_result=0;proc_result=0;
 assert(xiaomi_touch_evdev_init(&state)==-ENOMEM&&proc_calls==1&&unregister_calls==1);
 proc_result=1;assert(xiaomi_touch_evdev_init(&state)==0&&xiaomi_touch==&state&&last_touch_events_pde);
 puts("PASS evdev registration failure and proc failure unwind");return 0;
}
'''}

def extract(path,name):
    s=path.read_text();pos=s.index(name+'(');start=s.rfind('\n',0,pos)+1;end=s.index('\n}\n',pos)+3
    return s[start:end]
def main():
    results=[]
    with tempfile.TemporaryDirectory(prefix='touch-host-',dir=ROOT) as temp:
        work=Path(temp);(work/'linux').mkdir()
        (work/'linux/types.h').write_text('#include <stdint.h>\ntypedef uint8_t u8;typedef int8_t s8;typedef uint16_t u16;typedef uint32_t u32;typedef int32_t s32;typedef uint64_t u64;\n')
        header=(BASE/'xiaomi_touch_type_common.h').read_bytes();(work/'xiaomi_touch_type_common.h').write_bytes(header)
        for name,test in TESTS.items():
            row={'name':name,'functions':test['functions']}
            for version in ['payload','preimage']:
                body='\n'.join(extract(ROOT/version/REL/test['file'],fn) for fn in test['functions'])
                src=work/(name+'-'+version+'.c');binary=work/(name+'-'+version)
                src.write_text(COMMON+test['before']+'\n'+body+'\n'+test['after'])
                p=subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-function','-Wno-unused-variable','-Wno-sign-compare','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie','-I'+str(work),str(src),'-o',str(binary)],capture_output=True)
                if p.returncode:raise RuntimeError(name+' '+version+' compile failed\n'+p.stderr.decode())
                p=subprocess.run([str(binary)],capture_output=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:abort_on_error=1','UBSAN_OPTIONS':'halt_on_error=1'},timeout=10)
                row[version]={'returncode':p.returncode,'stdout':p.stdout.decode(),'stderr':p.stderr.decode()[:2500]}
                if version=='payload' and p.returncode:raise RuntimeError(name+' patched source failed\n'+p.stderr.decode())
                if version=='preimage' and not p.returncode:raise RuntimeError(name+' did not detect original defect')
            results.append(row)
            print('PASS',name,'; old source rejected')
        report={'schema':1,'status':'PASS_HOST_EXTRACTED_PRODUCTION_FUNCTION_TESTS','scope':'Actual patched functions, real preserved Xiaomi common UAPI header, fault-injection host stubs; not a complete kernel build or a THP hardware test.','uapi_header_sha256':hashlib.sha256(header).hexdigest(),'test_groups':results,'runtime_activation_approved':False,'issues':[]}
        (ROOT/'HOST-TESTS.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
