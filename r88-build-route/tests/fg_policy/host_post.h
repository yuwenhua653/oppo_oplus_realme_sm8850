enum { MCA_EVENT_USB_CONNECT=1, MCA_EVENT_WIRELESS_CONNECT, MCA_EVENT_USB_DISCONNECT,
 MCA_EVENT_WIRELESS_DISCONNECT, MCA_EVENT_IS_EU_MODEL, MCA_EVENT_CHARGE_TYPE_CHANGE,
 MCA_EVENT_BQ_FG_ERROR };
enum { STRATEGY_FUNC_TYPE_FG=1, MCA_EVENT_TYPE_PANEL, MCA_EVENT_TYPE_THERMAL_TEMP,
 STRATEGY_FUNC_TYPE_QUICK_CHARGE, STRATEGY_STATUS_TYPE_QC_CHARGE_STS,
 STRATEGY_STATUS_TYPE_QC_IBAT_MAX, STRATEGY_STATUS_TYPE_QC_TERM_CURR,
 STRATEGY_STATUS_TYPE_QC_TERM_VOLT, MCA_QUICK_CHG_STS_CHARGING,
 XM_CHARGER_TYPE_SDP };
static int parse_error, storage_error, allocation_error, registration_error;
static bool storage_value, storage_scribble;
static int storage_reads, registrations, auth_groups, monitor_schedules, ota_schedules;
static int schedule_count, cancel_count, recharge_count, reset_count, qbg_calls;
static int optional_result[9], optional_calls[9], parse_ota, parse_qbg;
static int64_t now_ms;
static struct strategy_fg *current;
static int temperature=250, smart_limit;
struct vote_record { void *voter; const char *name; bool enabled; int value; };
static struct vote_record votes[64];
static int vote_count;
static int g_strategy_fg_ops;
static void *system_wq;
static void reset_host(void) {
 parse_error=storage_error=allocation_error=registration_error=0;
 storage_value=storage_scribble=false;storage_reads=registrations=auth_groups=0;
 monitor_schedules=ota_schedules=schedule_count=cancel_count=recharge_count=reset_count=qbg_calls=0;
 vote_count=parse_ota=parse_qbg=0;current=NULL;now_ms=100000;temperature=250;smart_limit=0;
 memset(optional_calls,0,sizeof(optional_calls));
 for (unsigned i=0;i<ARRAY_SIZE(optional_result);i++) optional_result[i]=1;
}
static int dev_err_probe(struct device *d,int error,const char *format,...) { (void)d;(void)format;return error; }
static void *devm_kzalloc(struct device *d,size_t n,int flags) {
 (void)d;(void)flags;if(allocation_error)return NULL;return calloc(1,n);
}
static void platform_set_drvdata(struct platform_device *p,void *data) { p->data=data;current=data; }
static int strategy_fg_parse_dt(struct strategy_fg *fg) {
 fg->cfg.support_nvt1000_ota=parse_ota;fg->cfg.support_qbg=parse_qbg;
 return parse_error;
}
static int charger_partition_get_eu_model(bool *value) {
 storage_reads++;if(!storage_error || storage_scribble)*value=storage_value;return storage_error;
}
static int platform_fg_ops_has_optional_op(int role,enum mca_fg_optional_op op) {
 CHECK(role==FG_IC_MASTER);CHECK((unsigned)op<ARRAY_SIZE(optional_result));
 optional_calls[op]++;return optional_result[op];
}
static struct power_supply *power_supply_get_by_name(const char *name) { static struct power_supply p;CHECK(!strcmp(name,"battery"));return &p; }
#define INIT_DELAYED_WORK(w,fn) ((void)(w))
static int callback(struct notifier_block *nb,unsigned long event,void *data) { (void)nb;(void)event;(void)data;return 0; }
#define strategy_fg_panel_notifier_cb callback
#define strategy_fg_thermal_notifier_cb callback
#define mca_strategy_fg_shutdown_cb callback
#define strategy_fg_get_status callback
static void strategy_fg_init_voter(struct strategy_fg *fg) {
 fg->en_voter=(void *)(uintptr_t)1;fg->charge_limit_voter=(void *)(uintptr_t)2;
 fg->iterm_voter=(void *)(uintptr_t)3;fg->vterm_voter=(void *)(uintptr_t)4;fg->voter_ok=true;
}
static int strategy_class_fg_ops_register(struct strategy_fg *fg,const void *ops) { CHECK(fg==current);CHECK(ops==&g_strategy_fg_ops);registrations++;return registration_error; }
static void strategy_fg_auth_create_group(struct device *dev) { (void)dev;auth_groups++; }
#define mca_strategy_ops_register(...) 0
#define mca_event_block_notify_register(...) ((void)0)
#define register_reboot_notifier(...) ((void)0)
static int queue_delayed_work(void *queue,struct delayed_work *work,int delay) {
 (void)queue;(void)delay;schedule_count++;if(current&&work==&current->ota_update_work)ota_schedules++;return 1;
}
static int mca_queue_delayed_work(struct delayed_work *work,int delay) {
 (void)delay;if(current&&work==&current->monitor_work)monitor_schedules++;return 1;
}
static int schedule_delayed_work(struct delayed_work *work,int delay) { return queue_delayed_work(NULL,work,delay); }
static int mca_mod_delayed_work(struct delayed_work *work,int delay) { return mca_queue_delayed_work(work,delay); }
static void cancel_delayed_work_sync(struct delayed_work *work) { (void)work;cancel_count++; }
static int mca_vote(struct mca_votable *voter,const char *name,bool enabled,int value) {
 CHECK(vote_count<(int)ARRAY_SIZE(votes));votes[vote_count++]=(struct vote_record){voter,name,enabled,value};return 0;
}
static int votes_named(const char *name,int enabled) { int n=0;for(int i=0;i<vote_count;i++)if(!strcmp(votes[i].name,name)&&votes[i].enabled==enabled)n++;return n; }
static int mca_get_effective_result(struct mca_votable *voter) { (void)voter;return 4480; }
static void mca_strategy_start_recharging(struct strategy_fg *fg) { recharge_count++;fg->recharging=true; }
static int strategy_class_fg_ops_get_temperature(int *value) { *value=temperature;return 0; }
static void strategy_fg_reset_co_to_default(struct strategy_fg *fg) { (void)fg;reset_count++; }
static int64_t ktime_get(void) { return now_ms; }
static int64_t ktime_sub(int64_t a,int64_t b) { return a-b; }
static int64_t ktime_to_ms(int64_t t) { return t; }
static int64_t ktime_get_boottime_seconds(void) { return now_ms/1000; }
static int platform_fg_ops_get_ota_update_flag(int role,int *value) { (void)role;*value=0;return 0; }
static int fg_update_status(struct strategy_fg *fg,bool jump) { (void)fg;(void)jump;return 0; }
static int mca_strategy_func_get_status(int type,int status,int *value) { (void)type;(void)status;*value=0;return 0; }
static int platform_fg_ops_qbg_send_chg_data(int role) { CHECK(role==FG_IC_MASTER);qbg_calls++;return 0; }
static int mca_smartchg_get_limit_soc(void) { return smart_limit; }
static int shutdown_checks;
static void mca_battery_shutdown_check_shutdown_delay(struct strategy_fg *fg,int *soc) { (void)fg;(void)soc;shutdown_checks++; }
