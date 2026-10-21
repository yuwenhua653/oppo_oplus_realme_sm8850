#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
#define EPROBE_DEFER 517
#define GFP_KERNEL 0
#define REG_BLOCK_LENGTH 32
#define PROBE_CNT_MAX 50
#define FG_FAKE_TEMP_NONE -999
#define FG_RM_FCC_DEFAULT_TH 2500
#define DEFUALT_FULL_DESIGN 5000
#define FG_IC_SOH_TH_DEFAUL 92
#define FG_IC_CYCLE_TH_DEFAUL 400
#define FG_IC_CYCLE_STEP_DEFAUL 50
#define FG_IC_RESISTANCE_ID_DEFAUL 100000
#define BATTERY_UNSEAL_KEY_LEN 4
#define NUM_REGS 8
#define FG_MAC_CMD_MANU_NAME 0x004c
#define FG_MAC_CMD_TERM_CURRENTS 0x456e
#define MCA_CHARGE_LOG_ID_FG_MASTER_IC 1
#define MCA_CHARGE_LOG_ID_FG_SLAVE_IC 2
#define STRATEGY_FUNC_TYPE_FG 1
#define MCA_EVENT_BQ_FG_ERROR 2
#define mca_log_err(...) ((void)0)
#define mca_log_info(...) ((void)0)
enum fg_vendor { BQ27Z561,NFG1000A,NFG1000B,MPC8011B,MPC7012,MPC7021,
 BQ30Z55,BQ40Z50,BQ27Z746,TIBQ28Z610,MAX1789,RAA241200,SC58561,SC58511,
 SC58520,VENDOR_INVALID };
enum { FG_FW_INIT,FG_FW_ERROR,FG_FW_SUCCESS,FG_FW_INVALID };
struct device_node { int present; };
struct device { struct device_node *of_node; };
struct i2c_client { struct device dev; void *data; };
struct mutex { bool live; };
typedef int atomic_t;
struct bq_fg_chip {
 struct device *dev;struct i2c_client *client;int ui_soh,fake_temp,batt_fcc;
 enum fg_vendor fg_vendor;struct mutex i2c_rw_lock,data_lock;
 atomic_t pm_suspend,digest_in_process;int update_fw_status;
 char fake_device_name[32];int *dec_rate_seq;int dec_rate_len;
 int batt_dc,soh_th,cycle_th,cycle_step,resistance_id;unsigned int dev_role;
 u8 key[4];bool support_voltage_record_level;u8 version_number,start_byte_address,byte_length;
 u8 *record_voltage;bool support_version_compatible;int support_nvt1000_ota;
 bool support_co_by_gpio;int co_gpio;u8 regs[NUM_REGS];void *sysfs_dev;
};
static const u8 bq27z561_regs[NUM_REGS]={0,1,2,3,4,5,6,7};
static int g_bq_fg_ops,g_bq27z516_log_ops;
static bool myron_readonly_diag;
static int alloc_call,alloc_fail_at,live_mutexes,dt_size,dt_read_error,gpio_number,
 gpio_request_error,gpio_direction_error,gpio_requests,gpio_directions;
static bool gpio_enabled;
static int variable_error,actual_length,term_error,term_writes,fast_error,fast_calls,
 optional_error[5],optional_calls,wakeup_error,wakeup_on,wakeup_off,registered,
 register_error,sysfs_calls,log_calls,diag_error,diag_calls,variable_calls,legacy_calls;
static unsigned char discriminator;
static unsigned int role;
static bool wakeup_state;
static void *allocated[16];static int allocated_count;
static char events[512];static unsigned event_count;
static void event(char x){assert(event_count+1<sizeof(events));events[event_count++]=x;events[event_count]=0;}
static void reset(void){
 for(int i=0;i<allocated_count;i++)free(allocated[i]);allocated_count=0;
 alloc_call=alloc_fail_at=live_mutexes=dt_size=dt_read_error=0;
 gpio_number=5;gpio_request_error=gpio_direction_error=gpio_requests=gpio_directions=0;gpio_enabled=false;
 variable_error=term_error=term_writes=fast_error=fast_calls=optional_calls=0;
 wakeup_error=wakeup_on=wakeup_off=registered=register_error=sysfs_calls=log_calls=0;
 diag_error=diag_calls=variable_calls=legacy_calls=0;actual_length=16;discriminator='7';role=0;
 memset(optional_error,0,sizeof(optional_error));wakeup_state=false;myron_readonly_diag=false;
 memset(events,0,sizeof(events));event_count=0;
}
static void *devm_kzalloc(struct device *d,size_t n,int f){
 (void)d;(void)f;if(++alloc_call==alloc_fail_at)return NULL;
 void *p=calloc(1,n);assert(p);assert(allocated_count<16);allocated[allocated_count++]=p;return p;
}
static void mutex_init(struct mutex *m){assert(!m->live);m->live=true;live_mutexes++;}
static void mutex_destroy(struct mutex *m){assert(m->live);m->live=false;live_mutexes--;}
static void atomic_set(atomic_t *a,int v){*a=v;}
static void i2c_set_clientdata(struct i2c_client *c,void *v){c->data=v;}
static void *of_get_property(struct device_node *n,const char *k,int *s){
 (void)n;assert(!strcmp(k,"bq,soc_decimal_rate"));event('D');*s=dt_size;return dt_size?(void *)&dt_size:NULL;
}
static int of_property_read_u32_array(struct device_node *n,const char *k,void *p,int len){
 (void)n;(void)k;for(int i=0;i<len;i++)((int *)p)[i]=i;return dt_read_error;
}
static int mca_parse_dts_u32(struct device_node *n,const char *k,void *p,int fallback){
 (void)n;int v=!strcmp(k,"ic_role")?(int)role:fallback;memcpy(p,&v,sizeof(v));return 0;
}
static int mca_parse_dts_u8_array(struct device_node *n,const char *k,u8 *p,int len){
 (void)n;(void)k;memset(p,0,(size_t)len);return 0;
}
static int mca_parse_dts_u8(struct device_node *n,const char *k,u8 *p,int fallback){
 (void)n;(void)k;*p=(u8)fallback;return 0;
}
static bool of_property_read_bool(struct device_node *n,const char *k){(void)n;return !strcmp(k,"co_by_gpio")&&gpio_enabled;}
static int of_property_count_u8_elems(struct device_node *n,const char *k){(void)n;(void)k;return -ENOENT;}
static int of_get_named_gpio(struct device_node *n,const char *k,int i){(void)n;(void)k;(void)i;return gpio_number;}
static const char *dev_name(struct device *d){(void)d;return "fixture";}
static int devm_gpio_request(struct device *d,int n,const char *k){(void)d;(void)n;(void)k;gpio_requests++;event('G');return gpio_request_error;}
static void *gpio_to_desc(int n){return n>=0?&gpio_number:NULL;}
static int gpiod_direction_output_raw(void *d,int v){assert(d);assert(v==0);gpio_directions++;event('g');return gpio_direction_error;}
static int gpiod_get_raw_value(void *d){assert(d);return 0;}
static int fg_mac_read_block_variable(struct bq_fg_chip *b,unsigned short cmd,u8 *out,u8 cap,u8 min,u8 *actual){
 (void)b;assert(cmd==FG_MAC_CMD_MANU_NAME&&cap==32&&min==3);variable_calls++;event('V');
 if(variable_error)return variable_error;
 memset(out,0,cap);out[0]='M';out[1]='I';out[2]=discriminator;*actual=(u8)actual_length;return 0;
}
static int fg_mac_read_block(struct bq_fg_chip *b,unsigned short cmd,void *raw,u8 len){
 u8 *out=raw;(void)b;assert(cmd==FG_MAC_CMD_MANU_NAME);legacy_calls++;event('v');
 if(variable_error)return variable_error;
 memset(out,0,len);out[0]='M';out[1]='I';out[2]=discriminator;return 2;
}
static int fg_mac_write_block(struct bq_fg_chip *b,unsigned short cmd,u8 *data,u8 len){
 assert(cmd==FG_MAC_CMD_TERM_CURRENTS&&len==2&&data[0]==220&&data[1]==5);
 assert(b->fg_vendor==BQ27Z561);term_writes++;event('T');return term_error;
}
static int fg_set_fastcharge_mode(struct bq_fg_chip *b,bool en){assert(!en);assert(b->fg_vendor!=VENDOR_INVALID);fast_calls++;event('F');return fast_error;}
static int fg_get_manufacture_data(struct bq_fg_chip *b){(void)b;optional_calls++;event('m');return optional_error[0];}
static int fg_read_cell_vendor(struct bq_fg_chip *b){(void)b;optional_calls++;event('c');return optional_error[1];}
static int fg_read_pack_vendor(struct bq_fg_chip *b){(void)b;optional_calls++;event('p');return optional_error[2];}
static int fg_read_fw_version(struct bq_fg_chip *b){(void)b;optional_calls++;event('w');return optional_error[3];}
static int fg_read_eeprom_version(struct bq_fg_chip *b){(void)b;optional_calls++;event('e');return optional_error[4];}
static void nfg1000_boot_app_judge(struct bq_fg_chip *b){(void)b;event('J');}
static int device_init_wakeup(struct device *d,bool en){(void)d;if(en){wakeup_on++;event('W');if(wakeup_error)return wakeup_error;wakeup_state=true;}else{wakeup_off++;wakeup_state=false;event('x');}return 0;}
static int fg_read_one_probe_ok(void *,bool *);
static int platform_fg_ic_ops_register_v2(unsigned int r,void *b,void *ops,size_t n){
 assert(r==role&&ops==&g_bq_fg_ops&&n==sizeof(g_bq_fg_ops));event('R');
 if(register_error)return register_error;
 struct bq_fg_chip *fg=b;assert(fg->fg_vendor!=VENDOR_INVALID);assert(fast_calls==1);
 bool ok=false;assert(fg_read_one_probe_ok(b,&ok)==0&&ok);registered++;return 0;
}
static void fg_force_sim_soh_if_needed(struct bq_fg_chip *b){(void)b;event('S');}
static void fg_sysfs_create_group(struct bq_fg_chip *b){(void)b;sysfs_calls++;event('Y');}
static void mca_log_charge_log_register(int id,void *ops,void *b){assert(ops==&g_bq27z516_log_ops&&b);assert(id==MCA_CHARGE_LOG_ID_FG_MASTER_IC||id==MCA_CHARGE_LOG_ID_FG_SLAVE_IC);log_calls++;event('L');}
static int bq_myron_diag_probe(struct i2c_client *c){(void)c;diag_calls++;return diag_error;}
static void mca_strategy_func_process(int a,int b,int c){(void)a;(void)b;(void)c;}
static int dev_err_probe(struct device *d,int err,const char *s){(void)d;(void)s;assert(err<0);return err;}

/* PRODUCTION_FUNCTIONS */

static struct device_node node={1};
static struct i2c_client client(void){return (struct i2c_client){.dev={.of_node=&node},.data=NULL};}
static unsigned cases;
static void no_publication(struct i2c_client *c,int expected){
 assert(bq_fg_probe(c)==expected);assert(!c->data);assert(!registered&&!sysfs_calls&&!log_calls);assert(live_mutexes==0);assert(!wakeup_state);cases++;
}
static int mapped(unsigned char v){switch(v){case'4':return NFG1000B;case'5':return NFG1000A;case'6':return MPC8011B;case'7':return MPC7012;case'8':return MPC7021;case'C':return BQ27Z561;default:return -1;}}
static void test_vendor(void){
 for(unsigned i=0;i<256;i++){
  reset();struct bq_fg_chip b={.fg_vendor=VENDOR_INVALID};discriminator=(u8)i;int r=fg_read_vendor(&b),want=mapped((u8)i);
  if(want<0)assert(r==-EOPNOTSUPP&&b.fg_vendor==VENDOR_INVALID);else assert(r==0&&(int)b.fg_vendor==want);
  assert(variable_calls==1&&!legacy_calls);cases++;
 }
 const int errors[]={-EIO,-EREMOTEIO,-ETIMEDOUT,-EPROBE_DEFER,-EPROTO,-EBADMSG};
 for(unsigned i=0;i<sizeof(errors)/sizeof(errors[0]);i++){
  reset();struct bq_fg_chip b={.fg_vendor=MPC7012};variable_error=errors[i];assert(fg_read_vendor(&b)==errors[i]&&b.fg_vendor==MPC7012);cases++;
 }
 const int bad_lengths[]={0,1,2,33,255};
 for(unsigned i=0;i<sizeof(bad_lengths)/sizeof(bad_lengths[0]);i++){
  reset();struct bq_fg_chip b={.fg_vendor=VENDOR_INVALID};actual_length=bad_lengths[i];assert(fg_read_vendor(&b)==-EPROTO&&b.fg_vendor==VENDOR_INVALID);cases++;
 }
 reset();struct bq_fg_chip b={.fg_vendor=VENDOR_INVALID};actual_length=3;assert(fg_read_vendor(&b)==0&&b.fg_vendor==MPC7012);cases++;
 reset();b=(struct bq_fg_chip){.fg_vendor=VENDOR_INVALID};actual_length=32;assert(fg_read_vendor(&b)==0&&b.fg_vendor==MPC7012);cases++;
}
static void test_probe(void){
 const unsigned char ids[]={'4','5','6','7','8','C'};
 for(unsigned i=0;i<sizeof(ids);i++){
  reset();discriminator=ids[i];struct i2c_client c=client();assert(bq_fg_probe(&c)==0);struct bq_fg_chip *b=c.data;
  assert(b&&(int)b->fg_vendor==mapped(ids[i]));assert(term_writes==(ids[i]=='C'));assert(registered==1&&sysfs_calls==1&&log_calls==1);assert(wakeup_on==1&&!wakeup_off&&wakeup_state);assert(optional_calls==5);assert(variable_calls==1&&!legacy_calls);assert(strchr(events,'V')<strchr(events,'F'));if(ids[i]=='C')assert(strchr(events,'V')<strchr(events,'T'));assert(strchr(events,'R')<strchr(events,'Y'));cases++;
 }
 reset();struct i2c_client c=client();alloc_fail_at=1;no_publication(&c,-ENOMEM);
 reset();c=client();c.dev.of_node=NULL;no_publication(&c,-EINVAL);
 reset();c=client();dt_size=4;no_publication(&c,-EINVAL);
 reset();c=client();dt_size=-1;no_publication(&c,-EINVAL);
 reset();c=client();dt_size=8;alloc_fail_at=2;no_publication(&c,-ENOMEM);
 reset();c=client();dt_size=8;dt_read_error=-EIO;no_publication(&c,-EINVAL);
 reset();c=client();dt_size=8;assert(bq_fg_probe(&c)==0&&((struct bq_fg_chip *)c.data)->dec_rate_len==2);cases++;
 reset();c=client();gpio_enabled=true;gpio_number=-EPROBE_DEFER;no_publication(&c,-EPROBE_DEFER);assert(!gpio_requests&&!gpio_directions);
 reset();c=client();gpio_enabled=true;gpio_request_error=-EBUSY;no_publication(&c,-EBUSY);assert(gpio_requests==1&&!gpio_directions);
 reset();c=client();gpio_enabled=true;gpio_direction_error=-EIO;no_publication(&c,-EIO);assert(gpio_requests==1&&gpio_directions==1);
 reset();c=client();gpio_enabled=true;assert(bq_fg_probe(&c)==0&&gpio_requests==1&&gpio_directions==1);assert(strchr(events,'V')<strchr(events,'G')&&strchr(events,'G')<strchr(events,'F'));cases++;
 reset();c=client();gpio_enabled=true;discriminator='C';assert(bq_fg_probe(&c)==0&&term_writes==1);assert(strchr(events,'V')<strchr(events,'G')&&strchr(events,'G')<strchr(events,'T')&&strchr(events,'T')<strchr(events,'F'));cases++;
 const int errors[]={-EIO,-EREMOTEIO,-ETIMEDOUT,-EPROBE_DEFER,-EPROTO,-EBADMSG};
 for(unsigned i=0;i<sizeof(errors)/sizeof(errors[0]);i++){reset();c=client();variable_error=errors[i];no_publication(&c,errors[i]);assert(!term_writes&&!fast_calls&&!optional_calls);}
 reset();c=client();discriminator='X';no_publication(&c,-EOPNOTSUPP);assert(!term_writes&&!fast_calls);
 reset();c=client();discriminator='X';gpio_enabled=true;no_publication(&c,-EOPNOTSUPP);assert(!gpio_requests&&!gpio_directions&&!term_writes&&!fast_calls);
 reset();c=client();discriminator='C';term_error=-EIO;no_publication(&c,-EIO);assert(term_writes==1&&!fast_calls);
 reset();c=client();fast_error=-ETIMEDOUT;no_publication(&c,-ETIMEDOUT);assert(fast_calls==1&&!optional_calls);
 reset();c=client();wakeup_error=-ENOMEM;no_publication(&c,-ENOMEM);assert(wakeup_on==1&&wakeup_off==1);
 const int reg_errors[]={-ENOMEM,-EBUSY,-EINVAL};
 for(unsigned i=0;i<sizeof(reg_errors)/sizeof(reg_errors[0]);i++){reset();c=client();register_error=reg_errors[i];no_publication(&c,reg_errors[i]);assert(wakeup_on==1&&wakeup_off==1);}
 for(int i=0;i<5;i++){reset();c=client();optional_error[i]=-EIO;assert(bq_fg_probe(&c)==0&&registered==1&&sysfs_calls==1&&log_calls==1);cases++;}
 reset();c=client();for(int i=0;i<5;i++)optional_error[i]=-EIO;assert(bq_fg_probe(&c)==0&&registered==1&&sysfs_calls==1&&log_calls==1&&optional_calls==5);cases++;
 reset();c=client();myron_readonly_diag=true;diag_error=-EPROBE_DEFER;assert(bq_fg_probe(&c)==-EPROBE_DEFER&&diag_calls==1&&!alloc_call&&!variable_calls&&!sysfs_calls&&!registered);cases++;
 reset();c=client();myron_readonly_diag=true;assert(bq_fg_probe(&c)==0&&diag_calls==1&&!alloc_call&&!variable_calls);cases++;
 reset();bool ok=false;assert(fg_read_one_probe_ok(NULL,&ok)==-EINVAL&&!ok);assert(fg_read_one_probe_ok(&c,NULL)==-EINVAL);assert(fg_read_one_probe_ok(&c,&ok)==0&&ok);cases+=3;
}
static int original_negative(void){
 reset();struct bq_fg_chip b={.fg_vendor=VENDOR_INVALID};discriminator='X';int r=fg_read_vendor(&b);assert(r>=0&&b.fg_vendor==MPC8011B);puts("PROVEN_ORIGINAL_UNKNOWN_VENDOR_FALLBACK");
 reset();struct i2c_client c=client();assert(bq_fg_probe(&c)==0);assert(((struct bq_fg_chip *)c.data)->fg_vendor==MPC7012&&term_writes==1);puts("PROVEN_ORIGINAL_TI_TERM_BEFORE_MPC7012_IDENTITY");
 reset();c=client();register_error=-EBUSY;assert(bq_fg_probe(&c)==0&&sysfs_calls==1&&log_calls==1);puts("PROVEN_ORIGINAL_FAILED_PROVIDER_RETURNS_SUCCESS_AND_PUBLISHES");
 reset();c=client();dt_size=4;assert(bq_fg_probe(&c)==0&&registered==1);puts("PROVEN_ORIGINAL_IGNORED_PARSE_FAILURE");
 reset();puts("PASS_4_ORIGINAL_NEGATIVE_SCENARIOS");return 0;
}
int main(int argc,char **argv){
 if(argc==2&&!strcmp(argv[1],"--original-negative"))return original_negative();
 test_vendor();test_probe();reset();printf("PASS_PRODUCTION_VENDOR_PROBE_CASES=%u\n",cases);return 0;
}
