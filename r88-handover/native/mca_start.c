#define _GNU_SOURCE
/* R88 boot-only coherent MCA handover. No CLI controls, shell, property
 * changes, authentication override, reload, unbind or unload. Module probe
 * functions may perform their normal charging-control initialization. */
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/statvfs.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <sys/syscall.h>
#include <linux/capability.h>
#include <linux/magic.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <signal.h>
#include <poll.h>
#include <time.h>
#include <dirent.h>
#include <stdarg.h>
#include "mca_contract.h"
#include "sha256_fixed.h"
#define ARRAY_COUNT(a) (sizeof(a)/sizeof((a)[0]))
enum { BASELINE_COUNT=ARRAY_COUNT(baseline), ADDITION_COUNT=ARRAY_COUNT(additions), TOTAL_COUNT=BASELINE_COUNT+ADDITION_COUNT };
_Static_assert(BASELINE_COUNT==249,"Preserve exact normal249; do not load readonly owners");
_Static_assert(ARRAY_COUNT(baseline_names)==BASELINE_COUNT,"Names/files count mismatch");
_Static_assert(ADDITION_COUNT==45,"Full47 minus identical retained hwid/miev");
_Static_assert(ARRAY_COUNT(addition_names)==ADDITION_COUNT,"Addition names/files mismatch");
#define REPORT "/vendor_dlkm/r36-report"
#define MODEL "Qualcomm Technologies, Inc. Myron based on SM8850"
#define TARGET "/sys/bus/platform/devices/soc:pmic-glink:mca,adsp_glink"
#define TARGET_REAL "/sys/devices/platform/soc/soc:pmic-glink/soc:pmic-glink:mca,adsp_glink"
#define TARGET_DT "/sys/firmware/devicetree/base/soc/pmic-glink/mca,adsp_glink"
#define PARENT "/sys/bus/platform/devices/soc:pmic-glink"
#define MCA_ARGS "enable_readonly=1 enable_power_supply=1 enable_extra_diagnostics=1"
#define USB "/sys/class/power_supply/usb"
#ifndef MCA_UNIT_TEST
#define BUDGET_MS 120000
#else
#ifndef BUDGET_MS
#define BUDGET_MS 250
#endif
#endif
#define LOG_CAP 65536u
struct evidence {
 uint32_t version, done, ok, error, baseline_verified, verified, loaded, bound, usb_identity_verified, auth_interface_verified;
 int64_t worker_start_ms,worker_end_ms;
 char boot_id[40],stage[64];
};
static int64_t now_ms(void);
static int64_t boot_ms(void){struct timespec t;if(clock_gettime(CLOCK_BOOTTIME,&t))return -1;return (int64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
static int64_t helper_start_ms,helper_end_ms;
static int log_fd=-1,progress_fd=-1;
static size_t log_bytes;
static char expected_boot[40];
static int refused(void){errno=EINVAL;return -1;}
static int write_all(int fd,const void*p,size_t n){const char*b=p;while(n){ssize_t r=write(fd,b,n);if(r<0&&errno==EINTR)continue;if(r<=0)return -1;b+=r;n-=(size_t)r;}return 0;}
static int event(const char*fmt,...){
 char text[640];va_list ap;va_start(ap,fmt);int n=vsnprintf(text,sizeof(text),fmt,ap);va_end(ap);
 if(n<0||(size_t)n>=sizeof(text)||log_bytes+(size_t)n>LOG_CAP){errno=EOVERFLOW;return -1;}
 if(log_fd>=0&&write_all(log_fd,text,(size_t)n))return -1;
 log_bytes+=(size_t)n;return 0;
}
static int announce(struct evidence*e,const char*stage){
 snprintf(e->stage,sizeof(e->stage),"%s",stage);
 if(event("boottime_ms=%lld stage=%s loaded=%u baseline_verified=%u verified=%u\n",(long long)boot_ms(),stage,e->loaded,e->baseline_verified,e->verified))return -1;
 return progress_fd>=0?write_all(progress_fd,e,sizeof(*e)):0;
}
static int read_file(const char*p,char*b,size_t cap,size_t*out){
 int fd=open(p,O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return -1;
 size_t n=0;int rc=-1;while(n<cap){ssize_t r=read(fd,b+n,cap-n);if(r<0&&errno==EINTR)continue;if(r<0)goto end;if(!r){rc=0;break;}n+=(size_t)r;}
 if(n==cap){errno=EOVERFLOW;rc=-1;}if(!rc){b[n]=0;*out=n;}
 end:{int error=errno;if(close(fd)&&!rc){rc=-1;error=errno;}errno=error;}return rc;
}
static int exact_file(const char*p,const char*expected,int nul){char b[256];size_t n=0,e=strlen(expected);if(read_file(p,b,sizeof(b)-1,&n))return -1;return n==e+1&&!memcmp(b,expected,e)&&b[e]==(nul?0:'\n')?0:refused();}
static int valid_boot(char*b,size_t n){if(n!=37||b[36]!='\n')return refused();b[36]=0;for(unsigned i=0;i<36;i++){if(i==8||i==13||i==18||i==23){if(b[i]!='-')return refused();}else if(!((b[i]>='0'&&b[i]<='9')||(b[i]>='a'&&b[i]<='f')))return refused();}return 0;}
static int boot_read(char*b){size_t n=0;return read_file("/proc/sys/kernel/random/boot_id",b,39,&n)||valid_boot(b,n)?-1:0;}
static int same_boot(void){char b[40];return boot_read(b)||strcmp(b,expected_boot)?refused():0;}
static int path_is(const char*path,const char*expected){char*real=realpath(path,NULL);if(!real)return -1;int match=!strcmp(real,expected);free(real);return match?0:refused();}
static int readonly_payload(long type,unsigned long flags){return type==EXT4_SUPER_MAGIC&&(flags&(ST_RDONLY|ST_NOSUID|ST_NODEV))==(ST_RDONLY|ST_NOSUID|ST_NODEV)?0:refused();}
static int same_stat(const struct stat*a,const struct stat*b){return a->st_dev==b->st_dev&&a->st_ino==b->st_ino&&a->st_size==b->st_size&&a->st_mode==b->st_mode&&a->st_uid==b->st_uid&&a->st_gid==b->st_gid&&a->st_nlink==b->st_nlink;}
/* Hash and later finit_module use this same descriptor; it must be regular,
 * root-owned, non-writable by group/other and opened O_RDONLY. */
static int verify_fd_content(int fd,const struct pinned_file*pin){
 struct stat before,after;int flags=fcntl(fd,F_GETFL);unsigned char buf[16384];uint64_t count=0;struct sha hash;char hex[65];
 if(flags<0||(flags&O_ACCMODE)!=O_RDONLY||fstat(fd,&before)||!S_ISREG(before.st_mode)||before.st_uid||before.st_gid||
    (before.st_mode&0022)||before.st_nlink!=1||before.st_size<64||(uint64_t)before.st_size!=pin->bytes||lseek(fd,0,SEEK_SET)<0)return refused();
 sha_init(&hash);
 for(;;){ssize_t n=read(fd,buf,sizeof(buf));if(n<0&&errno==EINTR)continue;if(n<0)return -1;if(!n)break;
  if(!count&&(n<64||memcmp(buf,"\177ELF\002\001",6)||buf[16]!=1||buf[17]||buf[18]!=183||buf[19]))return refused();
  count+=(uint64_t)n;if(count>pin->bytes)return refused();sha_add(&hash,buf,(size_t)n);
 }
 sha_end(&hash,hex);if(count!=pin->bytes||strcmp(hex,pin->sha256)||fstat(fd,&after)||!same_stat(&before,&after)||lseek(fd,0,SEEK_SET)<0)return refused();return 0;
}
static int open_pinned(const struct pinned_file*pin){
 struct stat before,after;struct statfs fs;struct statvfs v;
 if(lstat(pin->path,&before)||!S_ISREG(before.st_mode))return -1;
 int fd=open(pin->path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK);if(fd<0)return -1;
 if(fstat(fd,&after)||!same_stat(&before,&after)||fstatfs(fd,&fs)||fstatvfs(fd,&v)||readonly_payload(fs.f_type,v.f_flag)||verify_fd_content(fd,pin)){int e=errno;close(fd);errno=e;return -1;}return fd;
}
/* Linux 6.12 module_flags() appends an optional parenthesized taint field.
 * Live modules have no Loading/Unloading +/- marker. Accept only the ordered,
 * nonrepeating per-module taint letters, not arbitrary trailing fields. */
static int loaded_tail(const char*tail){
 const char*order="PFCOEKXTN";unsigned count=0;
 tail+=strspn(tail," \t\r");
 if(!*tail)return 0;
 if(*tail++!='(')return refused();
 while(*tail&&*tail!=')'){
  const char*flag=strchr(order,*tail++);
  if(!flag)return refused();
  order=flag+1;count++;
 }
 if(!count||*tail++!=')')return refused();
 tail+=strspn(tail," \t\r");
 return !*tail?0:refused();
}
/* Exact set; each entry Live, no duplicates or unexpected owner module. */
static int parse_loaded(char*text,unsigned prefix){
 if(prefix>ADDITION_COUNT)return refused();
 unsigned char seen[TOTAL_COUNT]={0};unsigned count=0;char*save=NULL;
 for(char*line=strtok_r(text,"\n",&save);line;line=strtok_r(NULL,"\n",&save)){
  char name[128],deps[4096],state[32],addr[40];unsigned long long size,refs;int end=0;
  if(sscanf(line,"%127s %llu %llu %4095s %31s %39s%n",name,&size,&refs,deps,state,addr,&end)!=6||strcmp(state,"Live"))return refused();
  if(strncmp(addr,"0x",2))return refused();
  size_t hex=strspn(addr+2,"0123456789abcdefABCDEF");
  if(!hex||hex>16||addr[2+hex]||loaded_tail(line+end))return refused();
  unsigned idx=TOTAL_COUNT;for(unsigned i=0;i<BASELINE_COUNT;i++)if(!strcmp(name,baseline_names[i])){idx=i;break;}
  for(unsigned i=0;i<prefix;i++)if(!strcmp(name,addition_names[i]))idx=BASELINE_COUNT+i;
  if(idx==TOTAL_COUNT||seen[idx])return refused();
  seen[idx]=1;count++;
 }
 return count==BASELINE_COUNT+prefix?0:refused();
}
static int loaded_set(unsigned prefix){char text[131072];size_t n=0;return read_file("/proc/modules",text,sizeof(text)-1,&n)||parse_loaded(text,prefix)?-1:0;}
static int cap_module(void){
 struct __user_cap_header_struct h={_LINUX_CAPABILITY_VERSION_3,0};struct __user_cap_data_struct d[2]={{0}};
 if(syscall(SYS_capget,&h,d))return -1;
 if(event("cap_effective=%08x%08x required=CAP_SYS_MODULE\n",d[1].effective,d[0].effective))return -1;
 if(!(d[CAP_SYS_MODULE/32].effective&(1u<<(CAP_SYS_MODULE%32)))){errno=EPERM;return -1;}return 0;
}
static int check_native(void){
 int fd=open(REPORT"/probe.log",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)return -1;
 FILE*f=fdopen(fd,"r");if(!f){close(fd);return -1;}char line[2048],boot[80];unsigned bytes=0,found=0;int rc=-1;
 snprintf(boot,sizeof(boot)," boot_id=%s ",expected_boot);
 while(fgets(line,sizeof(line),f)){bytes+=(unsigned)strlen(line);if(bytes>8u*1024u*1024u)goto end;
  if(strstr(line," stage=boot-id ")&&strstr(line,boot)){
   if(strncmp(line,"R36_PROBE build_id=" BUILD_ID " ",sizeof("R36_PROBE build_id=" BUILD_ID " ")-1))goto end;
   found++;
  }
 }
 if(!ferror(f)&&found==1)rc=0;
 end:if(fclose(f)&&!rc)rc=-1;if(rc)errno=EINVAL;return rc;
}

static int absent_path(const char *path){struct stat s;if(!lstat(path,&s)){errno=EEXIST;return -1;}return errno==ENOENT?0:-1;}
static int exact_u32(const char*path,uint32_t value){char b[8];size_t n=0;if(read_file(path,b,sizeof(b)-1,&n))return -1;uint32_t got=n==4?((uint32_t)(unsigned char)b[0]<<24)|((uint32_t)(unsigned char)b[1]<<16)|((uint32_t)(unsigned char)b[2]<<8)|(unsigned char)b[3]:~value;return n==4&&got==value?0:refused();}
static int no_old_owners(void){return absent_path("/sys/module/myron_bq_readonly")||absent_path("/sys/module/myron_mca_readonly")?-1:0;}
static int initial_identity(void){
 struct statfs fs;
 if(statfs("/sys",&fs)||fs.f_type!=SYSFS_MAGIC||
    path_is("/sys/bus/i2c/devices/5-0055/of_node","/sys/firmware/devicetree/base/soc/qcom,qupv3_1_geni_se@ac0000/i2c@a94000/bq27z561_standlone@55")||
    exact_file("/sys/bus/i2c/devices/5-0055/of_node/compatible","ti,bq27z561_master",1)||
    exact_file("/sys/bus/i2c/devices/5-0055/of_node/status","ok",1)||
    exact_u32("/sys/bus/i2c/devices/5-0055/of_node/ic_role",0)||
    absent_path("/sys/bus/i2c/devices/5-0055/of_node/co_by_gpio")||
    absent_path("/sys/bus/i2c/devices/5-0055/of_node/batt_ctl")||
    exact_file("/sys/bus/i2c/devices/5-006e/of_node/compatible","sc8585_master",1)||
    exact_file("/sys/bus/i2c/devices/5-006e/of_node/status","ok",1)||
    exact_u32("/sys/bus/platform/devices/soc:strategy-fg/of_node/fg_type",0)||
    exact_u32("/sys/bus/platform/devices/soc:strategy-fg/of_node/adapt_power",100)||
    path_is(PARENT "/driver","/sys/bus/platform/drivers/pmic_glink")||
    path_is(PARENT "/driver/module","/sys/module/qti_pmic_glink")||
    absent_path("/sys/bus/i2c/devices/5-0055/driver")||
    absent_path("/sys/bus/i2c/devices/5-006e/driver")||absent_path(TARGET "/driver")||
    absent_path("/sys/class/power_supply/battery")||absent_path(USB)||
    absent_path(REPORT "/r70-gauge.claim")||absent_path(REPORT "/r75-mca.claim"))return -1;
 return 0;
}
static int state_guard(unsigned loaded){
 if(loaded>ADDITION_COUNT||same_boot()||cap_module()||exact_file("/proc/sys/kernel/modules_disabled","0",0)||loaded_set(loaded)||no_old_owners())return -1;
 return loaded?0:initial_identity();
}
static int (*state_guard_fn)(unsigned)=state_guard;
static int plain_insert(int fd,const char*params,int flags){return (int)syscall(SYS_finit_module,fd,params,flags);}
static int (*insert_fn)(int,const char*,int)=plain_insert;
static int bind_is(const char*device,const char*driver,const char*module){char p[512];int n=snprintf(p,sizeof(p),"%s/driver",device);if(n<0||(size_t)n>=sizeof(p)||path_is(p,driver))return -1;n=snprintf(p,sizeof(p),"%s/driver/module",device);return n<0||(size_t)n>=sizeof(p)||path_is(p,module)?-1:0;}
/* Host tests replace only the final identity observations. Production builds
 * retain direct calls to the same binding, canonical-path and metadata guards. */
#ifdef MCA_UNIT_TEST
static int (*final_bind_fn)(const char*,const char*,const char*)=bind_is;
static int (*final_path_fn)(const char*,const char*)=path_is;
static int (*final_exact_fn)(const char*,const char*,int)=exact_file;
static int (*final_lstat_fn)(const char*,struct stat*)=lstat;
#else
#define final_bind_fn bind_is
#define final_path_fn path_is
#define final_exact_fn exact_file
#define final_lstat_fn lstat
#endif
static const char*const interface_bindings[][3]={
 {"/sys/bus/i2c/devices/5-0055","/sys/bus/i2c/drivers/bq27z561","/sys/module/bq27z561"},
 {"/sys/bus/i2c/devices/5-006e","/sys/bus/i2c/drivers/sc8581_charger_pump","/sys/module/sc8581"},
 {TARGET,"/sys/bus/platform/drivers/mca_adsp_glink","/sys/module/mca_adsp_glink"},
 {"/sys/bus/platform/devices/soc:strategy-fg","/sys/bus/platform/drivers/strategy_fg","/sys/module/mca_strategy_fg_comp"},
 {"/sys/bus/platform/devices/soc:mca_business_battery","/sys/bus/platform/drivers/business_battery","/sys/module/mca_business_battery_comp"},
 {"/sys/bus/platform/devices/soc:mca_business_charger","/sys/bus/platform/drivers/business_charger","/sys/module/mca_business_charger_comp"},
 {"/sys/bus/platform/devices/soc:mca_strategy_quick_charge","/sys/bus/platform/drivers/strtategy-quick-charge","/sys/module/mca_strategy_quickchg"}
};
static const char*const interface_paths[][2]={
 {"/sys/class/power_supply/battery","/sys/devices/platform/soc/soc:mca_business_battery/power_supply/battery"},
 {USB,"/sys/devices/platform/soc/soc:mca_business_charger/power_supply/usb"},
 {"/sys/class/xm_power/fuelgauge/strategy_fg","/sys/devices/platform/soc/soc:strategy-fg"}
};
static const char*const interface_auth_names[]={"authentic","slave_authentic","verify_slave_flag","verify_digest","batt_power_match"};
static int final_auth_metadata(unsigned i){
 struct stat s;char path[512];
 if(i>=ARRAY_COUNT(interface_auth_names))return refused();
 int n=snprintf(path,sizeof(path),"%s/%s",interface_paths[2][0],interface_auth_names[i]);
 if(n<0||(size_t)n>=sizeof(path))return refused();
 if(final_lstat_fn(path,&s))return -1;
 return S_ISREG(s.st_mode)&&(s.st_mode&0777)==0664?0:refused();
}
static int final_interfaces(void){
 for(unsigned i=0;i<ARRAY_COUNT(interface_bindings);i++)
  if(final_bind_fn(interface_bindings[i][0],interface_bindings[i][1],interface_bindings[i][2]))return -1;
 for(unsigned i=0;i<2;i++)if(final_path_fn(interface_paths[i][0],interface_paths[i][1]))return -1;
 if(final_exact_fn("/sys/class/power_supply/battery/type","Battery",0)||
    final_path_fn(interface_paths[2][0],interface_paths[2][1]))return -1;
 for(unsigned i=0;i<ARRAY_COUNT(interface_auth_names);i++)if(final_auth_metadata(i))return -1;
 /* Presence/binding only. Never read digest or write an authentication flag. */
 return 0;
}
/* On final failure inspect every gate once. A first missing FG binding must
 * not conceal a second missing quick-charge binding or auth metadata. This
 * uses the same observations as completion and reads no authentication data. */
static unsigned final_diagnostics(void){
 unsigned missing=0;
 for(unsigned i=0;i<ARRAY_COUNT(interface_bindings);i++){
  if(final_bind_fn(interface_bindings[i][0],interface_bindings[i][1],interface_bindings[i][2])){
   int error=errno?errno:EIO;missing++;(void)event("interface_missing kind=binding path=%s module=%s errno=%d\n",interface_bindings[i][0],interface_bindings[i][2],error);
  }
 }
 for(unsigned i=0;i<ARRAY_COUNT(interface_paths);i++){
  if(final_path_fn(interface_paths[i][0],interface_paths[i][1])){
   int error=errno?errno:EIO;missing++;(void)event("interface_missing kind=canonical_path path=%s errno=%d\n",interface_paths[i][0],error);
  }
 }
 if(final_exact_fn("/sys/class/power_supply/battery/type","Battery",0)){
  int error=errno?errno:EIO;missing++;(void)event("interface_missing kind=battery_type path=/sys/class/power_supply/battery/type errno=%d\n",error);
 }
 for(unsigned i=0;i<ARRAY_COUNT(interface_auth_names);i++){
  if(final_auth_metadata(i)){
   int error=errno?errno:EIO;missing++;(void)event("interface_missing kind=auth_metadata name=%s errno=%d\n",interface_auth_names[i],error);
  }
 }
 (void)event("interface_diagnostics missing=%u auth_contents_read=0\n",missing);
 return missing;
}
static int (*interfaces_fn)(void)=final_interfaces;
static int load_fixed(int fds[ADDITION_COUNT],struct evidence*e){
 if(e->verified!=ADDITION_COUNT||e->baseline_verified!=BASELINE_COUNT||e->loaded)return refused();
 for(unsigned i=0;i<ADDITION_COUNT;i++){
  if(announce(e,"pre_insert_guard")||state_guard_fn(i))return -1;
  if(event("insert index=%u name=%s path=%s sha256=%s flags=0 arguments=empty\n",i,addition_names[i],additions[i].path,additions[i].sha256))return -1;
  errno=0;int rc=insert_fn(fds[i],"",0);int error=errno;
  if(!rc)e->loaded=i+1;
  if(event("insert_result index=%u result=%d errno=%d\n",i,rc,error))return -1;
  if(rc){errno=error?error:EIO;return -1;}
  if(state_guard_fn(e->loaded)||announce(e,"insert_returned_success"))return -1;
 }
 return 0;
}
static void evidence_worker(struct evidence*e){
 struct utsname u;int fds[ADDITION_COUNT];for(unsigned i=0;i<ADDITION_COUNT;i++)fds[i]=-1;
 memset(e,0,sizeof(*e));e->version=1;e->worker_start_ms=boot_ms();
 if(e->worker_start_ms<0||announce(e,"identity"))goto fail;
 if(getuid()||geteuid()||getgid()||getegid()){errno=EPERM;goto fail;}
 if(uname(&u)||strcmp(u.release,KERNEL)||boot_read(expected_boot)){errno=EINVAL;goto fail;}
 memcpy(e->boot_id,expected_boot,40);
 if(exact_file("/sys/firmware/devicetree/base/model",MODEL,1)||check_native()||state_guard_fn(0))goto fail;
 if(announce(e,"verify_baseline_files"))goto fail;
 for(unsigned i=0;i<BASELINE_COUNT;i++){int fd=open_pinned(&baseline[i]);if(fd<0)goto fail;if(close(fd))goto fail;e->baseline_verified=i+1;}
 if(announce(e,"verify_all_45_before_any_insert"))goto fail;
 for(unsigned i=0;i<ADDITION_COUNT;i++){fds[i]=open_pinned(&additions[i]);if(fds[i]<0)goto fail;e->verified=i+1;}
 if(load_fixed(fds,e)||state_guard_fn(ADDITION_COUNT))goto fail;
 if(announce(e,"wait_binding_interfaces"))goto fail;
 int ready=0;
 for(unsigned attempt=0;attempt<200;attempt++){
  if(!interfaces_fn()){ready=1;break;}
  struct timespec delay={0,25000000};if(nanosleep(&delay,NULL)&&errno!=EINTR)goto fail;
 }
 if(!ready){(void)final_diagnostics();errno=ENODEV;goto fail;}
 if(state_guard_fn(ADDITION_COUNT))goto fail;
 e->bound=1;e->usb_identity_verified=1;e->auth_interface_verified=1;e->ok=1;snprintf(e->stage,sizeof(e->stage),"complete");goto done;
 fail:e->error=errno?errno:EIO;
 done:for(unsigned i=0;i<ADDITION_COUNT;i++)if(fds[i]>=0)(void)close(fds[i]);
 e->done=1;e->worker_end_ms=boot_ms();(void)event("finished status=%s stage=%s errno=%u loaded=%u\n",e->ok?"complete":"partial",e->stage,e->error,e->loaded);
}
static void (*worker_fn)(struct evidence*)=evidence_worker;
static int64_t now_ms(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return -1;return (int64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
static int valid_evidence(const struct evidence*e){
 if(e->version!=1||e->done>1||e->ok>1||e->baseline_verified>BASELINE_COUNT||e->verified>ADDITION_COUNT||e->loaded>e->verified||e->bound>1||e->usb_identity_verified>1||e->auth_interface_verified>1||e->worker_start_ms<0||e->worker_end_ms<0||!memchr(e->stage,0,sizeof(e->stage))||!memchr(e->boot_id,0,sizeof(e->boot_id)))return 0;
 if(e->loaded&&(e->verified!=ADDITION_COUNT||e->baseline_verified!=BASELINE_COUNT))return 0;
 if(e->bound&&(e->loaded!=ADDITION_COUNT||e->verified!=ADDITION_COUNT||e->baseline_verified!=BASELINE_COUNT))return 0;
 if((e->usb_identity_verified||e->auth_interface_verified)&&!e->bound)return 0;
 if(e->ok&&(!e->done||e->error||e->baseline_verified!=BASELINE_COUNT||e->verified!=ADDITION_COUNT||e->loaded!=ADDITION_COUNT||!e->bound||!e->usb_identity_verified||!e->auth_interface_verified))return 0;
 return 1;
}
static int supervise(struct evidence*e){
 int p[2];if(pipe2(p,O_CLOEXEC|O_NONBLOCK))return -1;pid_t child=fork();if(child<0){int er=errno;close(p[0]);close(p[1]);errno=er;return -1;}
 if(!child){close(p[0]);progress_fd=p[1];(void)fcntl(p[1],F_SETFL,0);struct evidence result;worker_fn(&result);int rc=write_all(p[1],&result,sizeof(result));close(p[1]);_exit(rc?2:0);}
 close(p[1]);int rc=-1;size_t used=0;struct evidence packet;int64_t start=now_ms(),end=start+BUDGET_MS;if(start<0)goto end;
 for(;;){int64_t now=now_ms();if(now<0)goto end;if(now>=end){errno=ETIMEDOUT;goto end;}
  struct pollfd v={p[0],POLLIN,0};int r=poll(&v,1,(int)(end-now));if(r<0&&errno==EINTR)continue;if(r<=0){if(!r)errno=ETIMEDOUT;goto end;}
  ssize_t n=read(p[0],(char*)&packet+used,sizeof(packet)-used);if(n<0&&(errno==EINTR||errno==EAGAIN))continue;if(n<=0){errno=EIO;goto end;}used+=(size_t)n;
  if(used==sizeof(packet)){if(!valid_evidence(&packet)){errno=EPROTO;goto end;}*e=packet;used=0;if(e->done){rc=0;goto end;}}
 }
 end:{int er=errno;close(p[0]);if(rc)kill(child,SIGKILL);(void)waitpid(child,NULL,WNOHANG);errno=er;}return rc;
}
static int open_report(void){
 int fd=open(REPORT,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return -1;struct stat s,p;struct statfs f;struct statvfs v;
 if(fstat(fd,&s)||fstatfs(fd,&f)||fstatvfs(fd,&v)||!S_ISDIR(s.st_mode)||s.st_uid||s.st_gid||(s.st_mode&07777)!=0755||f.f_type!=TMPFS_MAGIC||
    (v.f_flag&(ST_RDONLY|ST_NOSUID|ST_NODEV|ST_NOEXEC))!=(ST_NOSUID|ST_NODEV|ST_NOEXEC)||fstatat(fd,"probe.log",&p,AT_SYMLINK_NOFOLLOW)||!S_ISREG(p.st_mode)||p.st_uid||p.st_gid||(p.st_mode&07777)!=0644||p.st_dev!=s.st_dev){close(fd);return refused();}return fd;
}
static int create_file(int dir,const char*name){return openat(dir,name,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0644);}
static int persist(int dir,const struct evidence*e,int supervision_error){
 int fd=create_file(dir,"r88-mca.status");if(fd<0)return -1;
 char text[2400];int n=snprintf(text,sizeof(text),"protocol=1\nhelper=%s\nstatus=%s\nboot_id=%s\nkernel=%s\ncontract_sha256=%s\nstage=%s\nerrno=%d\nbaseline_verified=%u\nfiles_verified=%u\ninsert_returned_success=%u\nbound=%u\nusb_identity_verified=%u\nauth_interface_verified=%u\nworker_budget_ms=%d\nmodule_state_after_timeout=unknown_no_retry_no_unload\nclock=CLOCK_BOOTTIME\nhelper_start_ms=%lld\nhelper_end_ms=%lld\nworker_start_ms=%lld\nworker_end_ms=%lld\ncharging_control=full_MCA_source_policy_may_run\nauthentication_success=not_asserted\nfast_charging_success=not_asserted\ncompletion_scope=hash_Live_binding_battery_usb_and_auth_interface_presence_only\n",BUILD_ID,(!supervision_error&&e->ok)?"complete":"partial",e->boot_id[0]?e->boot_id:"unavailable",KERNEL,CONTRACT_SHA,e->stage[0]?e->stage:"supervision",supervision_error?supervision_error:(int)e->error,e->baseline_verified,e->verified,e->loaded,e->bound,e->usb_identity_verified,e->auth_interface_verified,BUDGET_MS,(long long)helper_start_ms,(long long)helper_end_ms,(long long)e->worker_start_ms,(long long)e->worker_end_ms);
 int rc=(n<0||(size_t)n>=sizeof(text)||write_all(fd,text,(size_t)n))?-1:0;if(close(fd))rc=-1;return rc;
}
static int helper_error(const char*stage,int error){fprintf(stderr,"R88_MCA helper=%s stage=%s errno=%d no_retry=1\n",BUILD_ID,stage,error?error:EIO);return 1;}
static int run_claimed_helper(int dir){
 int claim=create_file(dir,"r88-mca.claim");if(claim<0){int er=errno;close(dir);return helper_error("claim",er);}
 const char marker[]=BUILD_ID " attempted once this report-tmpfs boot; no retry or unload\n";
 int claim_error=write_all(claim,marker,sizeof(marker)-1)?(errno?errno:EIO):0;if(close(claim)&&!claim_error)claim_error=errno?errno:EIO;
 if(claim_error){close(dir);return helper_error("claim_write",claim_error);}
 log_fd=create_file(dir,"r88-mca.log");if(log_fd<0){int er=errno;close(dir);return helper_error("log_setup",er);}
 struct evidence e={0};helper_start_ms=boot_ms();int error=supervise(&e)?(errno?errno:EIO):0;helper_end_ms=boot_ms();
 int saved=persist(dir,&e,error)?(errno?errno:EIO):0;int log_error=close(log_fd)?(errno?errno:EIO):0;log_fd=-1;int dir_error=close(dir)?(errno?errno:EIO):0;
 int failed=0;if(error)failed=helper_error("supervision",error);if(saved)failed=helper_error("persist",saved);if(log_error)failed=helper_error("log_close",log_error);if(dir_error)failed=helper_error("report_close",dir_error);
 if(!e.ok||!e.bound||!e.usb_identity_verified||!e.auth_interface_verified)failed=helper_error(e.stage[0]?e.stage:"worker_incomplete",e.error);
 return failed;
}
static int run_helper(int argc,char**argv){
 (void)argv;if(argc!=1){(void)helper_error("arguments",EINVAL);return 2;}
 if(!RUNTIME_FROZEN){(void)helper_error("draft_contract_no_activation",EPERM);return 2;}
 if(getuid()||geteuid()||getgid()||getegid()){(void)helper_error("identity",EPERM);return 2;}
 umask(022);int dir=open_report();if(dir<0)return helper_error("report_open",errno);return run_claimed_helper(dir);
}
#ifndef MCA_UNIT_TEST
int main(int argc,char**argv){return run_helper(argc,argv);}
#endif
