#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <pthread.h>
#include <stdint.h>
struct task_struct;
#define current ((struct task_struct *)(uintptr_t)pthread_self())
#define EPROBE_DEFER 517
#define PAGE_SIZE 4096
#define GFP_KERNEL 0
#define FG_IC_MASTER 0
#define FG_IC_SLAVE 1
#define FG_SITE_MAX 2
#define CP_ROLE_MASTER 0
#define CP_ROLE_SLAVE 1
#define CountryCN 0
#define MCA_BATTERY_TYPE_SINGLE_NUM_MAX 0
#define BATT_PARA_MAX_GROUP 16
#define TEMP_PARA_MAX_GROUP 16
#define BATT_PARA_CC_NAME_LEN 64
#define BATT_PARA_CC_TEMP_23 23
#define BATT_PARA_CC_TEMP_30 30
#define BATT_PARA_CC_TEMP_40 40
enum { MCA_QUICK_CHG_BATT_ROLE, MCA_QUICK_CHG_BATT_ID, MCA_QUICK_CHG_TEMP_PARA_NAME, MCA_QUICK_CHG_BATT_PARA_MAX };
enum { MCA_QUICK_CHG_TEMP_LOW, MCA_QUICK_CHG_TEMP_HIGH, MCA_QUICK_CHG_LOW_TEMP_HYS, MCA_QUICK_CHG_HIGH_TEMP_HYS, MCA_QUICK_CHG_TEMP_MAX_CURRENT, MCA_QUICK_CHG_TEMP_NROMAL_FV, MCA_QUICK_CHG_TEMP_FFC_FV, MCA_QUICK_CHG_VOLT_PARA_NAME, MCA_QUICK_CHG_VOLT_FFC_PARA_NAME, MCA_QUICK_CHG_STAGE_PARA_NAME, MCA_QUICK_CHG_FFC_STAGE_PARA_NAME, MCA_QUICK_CHG_TEMP_PARA_MAX };
struct device_node { int kind; };
struct device { struct device_node *of_node; };
struct platform_device { struct device dev; };
struct notifier_block { int notifier_call; int priority; };
struct mca_hwid { int country_version; };
struct mca_quick_charge_volt_info { int volt_para_size; };
struct mca_quick_charge_temp_para_info {
    struct { int temp_low, temp_high, low_temp_hysteresis, high_temp_hysteresis, max_current, normal_max_fv, ffc_max_fv; } temp_para;
    struct mca_quick_charge_volt_info volt_info, volt_ffc_info;
};
struct mca_quick_charge_batt_para_info { int temp_para_size; struct mca_quick_charge_temp_para_info *temp_info; };
struct mca_quick_charge_info {
    struct device *dev;
    int cp_chip_vendor, batt_type, data_lock;
    bool has_gbl_batt_para, support_base_flip;
    int batt_para_cc_thr[2];
    struct mca_quick_charge_batt_para_info batt_para[2], base_flip_para[2];
    void *input_suspend_voter, *buck_input_voter, *buck_charge_curr_voter, *term_volt_voter, *flip_charge_curr_voter;
    int monitor_work, pps_ptf_work, vfc_work;
    struct notifier_block shutdown_notifier;
};
struct kernel_param {};
struct kernel_param_ops { int (*get)(char *, const struct kernel_param *); };
#define DEFINE_MUTEX(name) pthread_mutex_t name = PTHREAD_MUTEX_INITIALIZER
#define mutex_lock pthread_mutex_lock
#define mutex_unlock pthread_mutex_unlock
#define mutex_init(p) ((void)(p))
#define module_param_cb(name, ops, arg, mode) static const struct kernel_param_ops *const retained_ops = ops; enum { param_permissions = mode }
#define MODULE_PARM_DESC(a,b)
#define mca_log_info(...) ((void)0)
#define mca_log_err(...) ((void)0)
#define pr_err(...) ((void)0)
#define INIT_DELAYED_WORK(a,b) ((void)(a))
#define scnprintf snprintf
static ssize_t strscpy(char *dst, const char *src, size_t size) { size_t n=strlen(src); if(n>=size)n=size-1; memcpy(dst,src,n);dst[n]=0;return (ssize_t)n; }

static struct { void *data; } g_strategy_quickchg_if_ops, g_quickchg_smartchg_if_ops;
#define STRATEGY_FUNC_TYPE_QUICK_CHARGE 1
#define mca_quick_charge_process_event 0
#define mca_quick_charge_get_status 0
#define mca_quick_charge_shutdown 0
static struct mca_quick_charge_info *last_info;
static struct device_node local_node={0}, global_node={1};
static struct platform_device pdev;
static struct mca_hwid hwid;
static int fg_ready, cp_vendor, cp_result, cp_master, cp_slave, missing_voter;
static int cell_error, slave_error, create_error, alloc_error, count_error, temp_error, integer_error;
static bool global_flag, hwid_missing, global_missing;
static const char *cell_name, *device_name;
static char trace[8192];
static size_t trace_len;
static int scenario;
static unsigned checks;
static void check(bool value, const char *message) { checks++; if(!value){fprintf(stderr,"case %d: %s\n",scenario,message);exit(41);} }
static void call(const char *fmt, ...) { va_list ap;va_start(ap,fmt);trace_len += vsnprintf(trace+trace_len,sizeof(trace)-trace_len,fmt,ap);va_end(ap);check(trace_len < sizeof(trace)-1,"trace overflow"); }
static void *allocs[256]; static bool freed[256]; static int alloc_count;
static void *host_alloc(size_t n) { void *p=calloc(1,n);check(p!=NULL,"host OOM");check(alloc_count<256,"allocation overflow");allocs[alloc_count]=p;freed[alloc_count++]=false;return p; }
static void kfree(void *p) { if(!p)return; for(int i=0;i<alloc_count;i++)if(allocs[i]==p && !freed[i]){free(p);freed[i]=true;return;} check(false,"unexpected free"); }
static void *kcalloc(size_t n,size_t sz,int flags) { (void)flags;call("temp_alloc;");return host_alloc(n*sz); }
static void *devm_kzalloc(struct device *dev,size_t n,int flags) { (void)dev;(void)flags;call("allocate;");if(alloc_error)return NULL;return host_alloc(n); }
static void platform_set_drvdata(struct platform_device *p,void *data) { (void)p; last_info=data;call("drvdata;"); }
static int strategy_class_fg_ops_is_init_ok(void) { call("fg;");return fg_ready; }
static int platform_class_cp_get_chip_vendor(int role,int *value) { (void)role;call("cp_vendor;");*value=cp_vendor;return cp_result; }
static int platform_class_cp_get_probe_ok(int role) { call("cp_probe:%d;",role);return role?cp_slave:cp_master; }
static void *mca_find_votable(const char *name) { static const char *names[]={"input_suspend","buck_input","buck_charge_curr","term_volt","flip_charge_curr"};call("voter:%s;",name);for(int i=0;i<5;i++)if(!strcmp(name,names[i])&&missing_voter==i)return NULL;return (void*)1; }
static const struct mca_hwid *mca_get_hwid_info(void) { call("hwid;");return hwid_missing?NULL:&hwid; }
static struct device_node *of_find_node_by_name(struct device_node *n,const char *name) { (void)n;call("node:%s;",name);return global_missing?NULL:&global_node; }
static int platform_fg_ops_get_batt_cell_info(int role,const char **out) { call("cell:%d;",role);if(role){if(!slave_error)*out="atl";return slave_error;}if(!cell_error)*out=cell_name;return cell_error; }
static int platform_fg_ops_get_device_name(int role,const char **out) { (void)role;call("device_name;");*out=device_name;return 0; }
static int mca_parse_dts_count_strings(struct device_node *n,const char *name,int max,int width) { (void)max;call("count:%d:%s;",n->kind,name);if(!strcmp(name,"batt_para"))return count_error?count_error:(n->kind?3:6);if(!strcmp(name,"base_flip_para"))return 3;if(temp_error)return temp_error;return width; }
static int mca_parse_dts_string_index(struct device_node *n,const char *name,int i,const char **out) {
    static const char *local[]={"0","atl","batt_para_atl","0","coslight","batt_para_cos"};
    static const char *temp[]={"23","35","0","0","4000","4510","4510","volt","ffc","stage","ffc_stage"};
    call("string:%s:%d;",name,i);
    if(!strcmp(name,"batt_para")||!strcmp(name,"base_flip_para")){(void)n;*out=local[i];}else *out=temp[i];return 0;
}
static int kstrtoint(const char *s,int base,int *out) { (void)base;call("integer:%s;",s);if(integer_error && !strcmp(s,"23"))return integer_error;char *end;long v=strtol(s,&end,10);if(*end)return -EINVAL;*out=(int)v;return 0; }
static int mca_quick_charge_parse_volt_para(struct device_node *n,const char *name,struct mca_quick_charge_volt_info *out) { (void)n;call("voltage:%s;",name);out->volt_para_size=1;return 0; }
static void mca_quick_charge_parse_stage_para(struct device_node *n,const char *name,struct mca_quick_charge_volt_info *out) { (void)n;(void)out;call("stage:%s;",name); }
static int mca_quick_charge_parse_dt(struct mca_quick_charge_info *info);
static int mca_quick_charge_create_voter(struct mca_quick_charge_info *info) { (void)info;call("create_voter;");return create_error; }
static void mca_quick_charge_init_data(struct mca_quick_charge_info *info) { (void)info;call("init_data;"); }
static void mca_quick_charge_create_group(struct device *dev) { (void)dev;call("create_group;"); }
static int mca_strategy_ops_register(int a,int b,int c,void *d,struct mca_quick_charge_info *e) { (void)a;(void)b;(void)c;(void)d;(void)e;call("strategy_register;");return 0; }
static void mca_charge_if_ops_register(void *p) { (void)p;call("charge_register;"); }
static void mca_smartchg_if_ops_register(void *p) { (void)p;call("smart_register;"); }
static int register_reboot_notifier(struct notifier_block *n) { (void)n;call("reboot_register;");return 0; }
