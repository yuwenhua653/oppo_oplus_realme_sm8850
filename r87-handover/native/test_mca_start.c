#define MCA_UNIT_TEST
#define BUDGET_MS 40
#include "mca_start.c"
#include <assert.h>

static unsigned assertions;
#define CHECK(x) do { assertions++; if(!(x)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x);abort();} } while(0)
static unsigned calls, guard_calls;
static int fail_at, guard_fail_at;
static int fake_state(unsigned loaded){guard_calls++;CHECK(loaded<=ADDITION_COUNT);if(guard_fail_at>=0&&(int)loaded==guard_fail_at){errno=EBUSY;return -1;}return 0;}
static int fake_insert(int fd,const char*args,int flags){CHECK(fd==(int)(100+calls));CHECK(!strcmp(args,""));CHECK(flags==0);unsigned at=calls++;if((int)at==fail_at){errno=EIO;return -1;}return 0;}
static struct evidence prepared(void){struct evidence e={0};e.version=1;e.baseline_verified=BASELINE_COUNT;e.verified=ADDITION_COUNT;return e;}
static void reset(void){calls=guard_calls=0;fail_at=guard_fail_at=-1;log_fd=progress_fd=-1;log_bytes=0;state_guard_fn=fake_state;insert_fn=fake_insert;}
static void load_cases(void){
 int fds[ADDITION_COUNT];for(unsigned i=0;i<ADDITION_COUNT;i++)fds[i]=(int)(100+i);
 for(unsigned count=0;count<ADDITION_COUNT;count++){reset();struct evidence e=prepared();e.verified=count;CHECK(load_fixed(fds,&e)<0);CHECK(calls==0&&e.loaded==0);}
 reset();struct evidence e=prepared();e.baseline_verified--;CHECK(load_fixed(fds,&e)<0&&calls==0);
 reset();e=prepared();CHECK(load_fixed(fds,&e)==0);CHECK(calls==ADDITION_COUNT&&e.loaded==ADDITION_COUNT);CHECK(guard_calls==ADDITION_COUNT*2);CHECK(load_fixed(fds,&e)<0&&calls==ADDITION_COUNT);
 for(int i=0;i<ADDITION_COUNT;i++){
  reset();e=prepared();fail_at=i;CHECK(load_fixed(fds,&e)<0);CHECK(calls==(unsigned)i+1&&e.loaded==(unsigned)i);
 }
 reset();e=prepared();guard_fail_at=5;CHECK(load_fixed(fds,&e)<0);CHECK(calls==5&&e.loaded==5);
}
static void live_text(char*b,size_t cap,unsigned prefix){
 size_t n=0;for(unsigned i=0;i<BASELINE_COUNT+prefix;i++){const char*name=i<BASELINE_COUNT?baseline_names[i]:addition_names[i-BASELINE_COUNT];int r=snprintf(b+n,cap-n,"%s 123 0 - Live 0x0000000000000000 (OE)\n",name);CHECK(r>0&&(size_t)r<cap-n);n+=(size_t)r;}
}
static void loaded_cases(void){
 char b[131072];for(unsigned i=0;i<=ADDITION_COUNT;i++){live_text(b,sizeof(b),i);CHECK(parse_loaded(b,i)==0);}
 live_text(b,sizeof(b),0);strcat(b,"myron_bq_readonly 123 0 - Live 0x0\n");CHECK(parse_loaded(b,0)<0);
 live_text(b,sizeof(b),0);strcat(b,"myron_mca_readonly 123 0 - Live 0x0\n");CHECK(parse_loaded(b,0)<0);
 live_text(b,sizeof(b),0);strcat(b,"unexpected_owner 123 0 - Live 0x0\n");CHECK(parse_loaded(b,0)<0);
 live_text(b,sizeof(b),0);char*line=strchr(b,'\n');CHECK(line);char first[512];size_t length=(size_t)(line-b);CHECK(length+2<sizeof(first));memcpy(first,b,length);first[length]='\n';first[length+1]=0;strcat(b,first);CHECK(parse_loaded(b,0)<0);
 live_text(b,sizeof(b),0);char*state=strstr(b," Live ");CHECK(state);memcpy(state," Dead ",6);CHECK(parse_loaded(b,0)<0);
 live_text(b,sizeof(b),1);CHECK(parse_loaded(b,0)<0);
 live_text(b,sizeof(b),0);CHECK(parse_loaded(b,1)<0);CHECK(parse_loaded(b,ADDITION_COUNT+1)<0);
 CHECK(loaded_tail(" (OE)")==0);CHECK(loaded_tail(" (EO)")<0);CHECK(loaded_tail(" (OO)")<0);CHECK(loaded_tail(" garbage")<0);
}
/* Exercise the actual final_interfaces condition chain with observations
 * injected at its sysfs boundaries. USB/type is intentionally unavailable. */
static unsigned final_bind_calls,final_path_calls,final_exact_calls,final_stat_calls;
static int final_fail_bind,final_fail_path,final_fail_exact,final_fail_stat,final_bad_mode,final_bad_kind;
static const char*usb_reported_type;
static const char*const final_bindings[][3]={
 {"/sys/bus/i2c/devices/5-0055","/sys/bus/i2c/drivers/bq27z561","/sys/module/bq27z561"},
 {"/sys/bus/i2c/devices/5-006e","/sys/bus/i2c/drivers/sc8581_charger_pump","/sys/module/sc8581"},
 {TARGET,"/sys/bus/platform/drivers/mca_adsp_glink","/sys/module/mca_adsp_glink"},
 {"/sys/bus/platform/devices/soc:strategy-fg","/sys/bus/platform/drivers/strategy_fg","/sys/module/mca_strategy_fg_comp"},
 {"/sys/bus/platform/devices/soc:mca_business_battery","/sys/bus/platform/drivers/business_battery","/sys/module/mca_business_battery_comp"},
 {"/sys/bus/platform/devices/soc:mca_business_charger","/sys/bus/platform/drivers/business_charger","/sys/module/mca_business_charger_comp"},
 {"/sys/bus/platform/devices/soc:mca_strategy_quick_charge","/sys/bus/platform/drivers/strtategy-quick-charge","/sys/module/mca_strategy_quickchg"}
};
static const char*const final_paths[][2]={
 {"/sys/class/power_supply/battery","/sys/devices/platform/soc/soc:mca_business_battery/power_supply/battery"},
 {USB,"/sys/devices/platform/soc/soc:mca_business_charger/power_supply/usb"},
 {"/sys/class/xm_power/fuelgauge/strategy_fg","/sys/devices/platform/soc/soc:strategy-fg"}
};
static const char*const final_auth_names[]={"authentic","slave_authentic","verify_slave_flag","verify_digest","batt_power_match"};
static int fake_final_bind(const char*device,const char*driver,const char*module){
 unsigned at=final_bind_calls++;CHECK(at<ARRAY_COUNT(final_bindings));CHECK(!strcmp(device,final_bindings[at][0]));CHECK(!strcmp(driver,final_bindings[at][1]));CHECK(!strcmp(module,final_bindings[at][2]));
 if((int)at==final_fail_bind){errno=ENODEV;return -1;}return 0;
}
static int fake_final_path(const char*path,const char*expected){
 unsigned at=final_path_calls++;CHECK(at<ARRAY_COUNT(final_paths));CHECK(!strcmp(path,final_paths[at][0]));CHECK(!strcmp(expected,final_paths[at][1]));
 if((int)at==final_fail_path){errno=ENOENT;return -1;}return 0;
}
static int fake_final_exact(const char*path,const char*expected,int nul){
 final_exact_calls++;
 if(!strcmp(path,USB "/type")){CHECK(usb_reported_type);return strcmp(expected,usb_reported_type)?refused():0;}
 CHECK(!strcmp(path,"/sys/class/power_supply/battery/type"));CHECK(!strcmp(expected,"Battery")&&nul==0);
 return final_fail_exact?refused():0;
}
static int fake_final_lstat(const char*path,struct stat*s){
 unsigned at=final_stat_calls++;char expected[512];CHECK(at<ARRAY_COUNT(final_auth_names));
 snprintf(expected,sizeof(expected),"/sys/class/xm_power/fuelgauge/strategy_fg/%s",final_auth_names[at]);CHECK(!strcmp(path,expected));
 if((int)at==final_fail_stat){errno=ENOENT;return -1;}memset(s,0,sizeof(*s));
 s->st_mode=((int)at==final_bad_kind?S_IFLNK:S_IFREG)|((int)at==final_bad_mode?0644:0664);return 0;
}
static void reset_final(void){
 final_bind_calls=final_path_calls=final_exact_calls=final_stat_calls=0;
 final_fail_bind=final_fail_path=final_fail_stat=final_bad_mode=final_bad_kind=-1;final_fail_exact=0;usb_reported_type=NULL;
 final_bind_fn=fake_final_bind;final_path_fn=fake_final_path;final_exact_fn=fake_final_exact;final_lstat_fn=fake_final_lstat;
}
static void interface_cases(void){
 /* Every adapter-dependent type, including absent type, keeps the same owner. */
 const char*types[]={NULL,"Unknown","USB","USB_DCP","USB_PD","USB_CDP","USB_ACA"};
 for(unsigned i=0;i<ARRAY_COUNT(types);i++){reset_final();usb_reported_type=types[i];CHECK(final_interfaces()==0);CHECK(final_bind_calls==ARRAY_COUNT(final_bindings)&&final_path_calls==3&&final_exact_calls==1&&final_stat_calls==5);}
 for(unsigned i=0;i<ARRAY_COUNT(final_bindings);i++){reset_final();final_fail_bind=i;CHECK(final_interfaces()<0);CHECK(final_bind_calls==(unsigned)i+1&&final_path_calls==0&&final_exact_calls==0&&final_stat_calls==0);}
 for(int i=0;i<3;i++){reset_final();final_fail_path=i;CHECK(final_interfaces()<0);CHECK(final_path_calls==(unsigned)i+1&&final_stat_calls==0);}
 reset_final();final_fail_exact=1;CHECK(final_interfaces()<0);CHECK(final_path_calls==2&&final_exact_calls==1&&final_stat_calls==0);
 for(int i=0;i<5;i++){
  reset_final();final_fail_stat=i;CHECK(final_interfaces()<0);CHECK(final_stat_calls==(unsigned)i+1);
  reset_final();final_bad_mode=i;CHECK(final_interfaces()<0);CHECK(final_stat_calls==(unsigned)i+1);
  reset_final();final_bad_kind=i;CHECK(final_interfaces()<0);CHECK(final_stat_calls==(unsigned)i+1);
 }
 final_bind_fn=bind_is;final_path_fn=path_is;final_exact_fn=exact_file;final_lstat_fn=lstat;
}
static struct evidence complete(void){struct evidence e=prepared();e.done=e.ok=e.bound=e.usb_identity_verified=e.auth_interface_verified=1;e.loaded=ADDITION_COUNT;snprintf(e.stage,sizeof(e.stage),"complete");snprintf(e.boot_id,sizeof(e.boot_id),"00000000-0000-0000-0000-000000000000");return e;}
static void packet_cases(void){
 struct evidence e=complete();CHECK(valid_evidence(&e));e.loaded--;CHECK(!valid_evidence(&e));e=complete();e.verified--;CHECK(!valid_evidence(&e));e=complete();e.baseline_verified--;CHECK(!valid_evidence(&e));e=complete();e.error=EIO;CHECK(!valid_evidence(&e));e=complete();e.done=0;CHECK(!valid_evidence(&e));e=complete();memset(e.stage,'X',sizeof(e.stage));CHECK(!valid_evidence(&e));
 e=prepared();e.bound=1;e.loaded=1;CHECK(!valid_evidence(&e));
}
static void fake_complete(struct evidence*e){*e=complete();}
static void fake_hang(struct evidence*e){*e=prepared();e->stage[0]=0;(void)announce(e,"mock_insert_blocked");for(;;)pause();}
static void supervision_cases(void){
 struct evidence e={0};worker_fn=fake_complete;CHECK(supervise(&e)==0&&e.ok&&e.loaded==ADDITION_COUNT);
 memset(&e,0,sizeof(e));worker_fn=fake_hang;int64_t start=now_ms();CHECK(supervise(&e)<0&&errno==ETIMEDOUT);CHECK(now_ms()-start<1000);CHECK(!e.ok&&e.loaded==0);
}
static void claim_cases(void){
 char dir[]="/tmp/r87-native-claim-XXXXXX";CHECK(mkdtemp(dir));int fd=open(dir,O_DIRECTORY|O_RDONLY);CHECK(fd>=0);worker_fn=fake_complete;CHECK(run_claimed_helper(fd)==0);
 fd=open(dir,O_DIRECTORY|O_RDONLY);CHECK(fd>=0);CHECK(run_claimed_helper(fd)!=0);
 char path[512];for(const char**n=(const char*[]){"r87-mca.claim","r87-mca.log","r87-mca.status",NULL};*n;n++){snprintf(path,sizeof(path),"%s/%s",dir,*n);CHECK(unlink(path)==0);}CHECK(rmdir(dir)==0);
 char*argv[]={"helper",NULL};CHECK(run_helper(2,argv)==2);if(!RUNTIME_FROZEN)CHECK(run_helper(1,argv)==2);
}
int main(void){load_cases();loaded_cases();interface_cases();packet_cases();supervision_cases();claim_cases();printf("PASS native handover assertions=%u\n",assertions);return 0;}
