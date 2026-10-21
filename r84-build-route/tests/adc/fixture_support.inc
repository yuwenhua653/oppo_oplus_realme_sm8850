#define ADC5_USR_DATA_CHECK 0x8000
#define ADC_TM_HIGH_LOW_THR_ENABLE 0
#define ADC_TM_HIGH_THR_ENABLE 1
#define ADC_TM_LOW_THR_ENABLE 2
#define ADC_TM_HIGH_LOW_THR_DISABLE 3
#define ADC_TM_HIGH_THR_DISABLE 4
#define ADC_TM_LOW_THR_DISABLE 5
#define ADC_TM_LOW_STATE 0
#define ADC_TM_HIGH_STATE 1
struct adc_tm_client_info {struct list_head list;struct adc_tm_param *param;int low_thr_requested,high_thr_requested;bool notify_low_thr,notify_high_thr,high_thr_set,low_thr_set;int state_request;};
static const struct iio_info adc5_gen3_info={0};
static struct adc5_chip *g_adc;
static struct iio_dev *g_iio;
static struct platform_device g_pdev;
static struct device g_parent;
static struct device_node g_node;
static struct regmap g_regmap;
static void *allocations[128];static unsigned n_alloc;
static struct thermal_zone_device *zones[8];static unsigned n_zones;
static irqreturn_t (*irq_fn[2])(int,void*);static void *irq_arg[2];static bool irq_live[2];
static unsigned irq_requests,irq_frees,zone_calls,ipc_create,ipc_destroy,queue_destroy;
static unsigned fail_irq,fail_zone,fail_alloc,alloc_calls;static bool fail_iio,fail_dt,fail_regmap;
static int inject_request,inject_zone;static bool inject_iio,inject_cancel,call_registration_callbacks;
static bool registration_complete;
static unsigned pending_status;
static atomic_uint scheduled,zone_updates,hardware_reads,hardware_writes,configures;
static struct work_struct *known_work[32];static unsigned n_work;
static pthread_mutex_t hw_lock=PTHREAD_MUTEX_INITIALIZER;
static u8 reg_status[2],reg_eoc[2],reg_fault[2],reg_high[2],reg_low[2],perph[2];
static pthread_mutex_t latch_lock=PTHREAD_MUTEX_INITIALIZER;static pthread_cond_t latch_cv=PTHREAD_COND_INITIALIZER;
static bool pause_status,paused_status,release_status,defer_eoc,conversion_started,quiesce_started,conversion_fence_attempted;
static atomic_bool conversion_data_read;
static unsigned cases;
static void lock_attempt_hook(struct mutex *m) {pthread_mutex_lock(&latch_lock);if(g_adc&&m==&g_adc->lock&&defer_eoc&&quiesce_started&&!atomic_load(&conversion_data_read)){conversion_fence_attempted=true;pthread_cond_broadcast(&latch_cv);}pthread_mutex_unlock(&latch_lock);}

static void remember(void *p) {assert(n_alloc<ARRAY_SIZE(allocations));allocations[n_alloc++]=p;}
static void *allocation(size_t n) {alloc_calls++;if(fail_alloc==alloc_calls)return NULL;void *p=calloc(1,n);assert(p);remember(p);return p;}
static void *devm_kcalloc(struct device *d,size_t n,size_t z,gfp_t flags) {(void)d;(void)flags;return allocation(n*z);}
static char *devm_kstrdup(struct device *d,const char *s,gfp_t f) {char *p=devm_kcalloc(d,strlen(s)+1,1,f);if(p)strcpy(p,s);return p;}
static struct iio_dev *devm_iio_device_alloc(struct device *d,size_t n) {(void)d;assert(n<=sizeof(g_iio->priv));g_iio=allocation(sizeof(*g_iio));if(g_iio)g_adc=iio_priv(g_iio);return g_iio;}
static struct regmap *dev_get_regmap(struct device *d,const char *name) {(void)d;(void)name;return fail_regmap?NULL:&g_regmap;}
static int of_property_count_u32_elems(struct device_node *n,const char *key) {(void)n;(void)key;return 2;}
static int of_property_read_u32_index(struct device_node *n,const char *key,int i,u32 *v) {(void)n;(void)key;*v=0x9000+i*0x100;return 0;}
static int of_property_read_u32(struct device_node *n,const char *key,u32 *v) {(void)n;(void)key;(void)v;return -EINVAL;}
static int of_irq_get_byname(struct device_node *n,const char *name) {(void)n;return 10+(name[strlen(name)-1]-'0');}
static struct workqueue_struct *alloc_workqueue(const char *name,unsigned f,int max) {(void)name;(void)f;(void)max;return allocation(sizeof(struct workqueue_struct));}
static void destroy_workqueue(struct workqueue_struct *q) {assert(q&&!q->destroyed);assert(!self_holds(&g_adc->lock));q->destroyed=true;queue_destroy++;}
static int adc5_get_dt_data(struct adc5_chip *a,struct device_node *n) {(void)n;a->nchannels=4;if(fail_dt)return -ENOMEM;a->chan_props=devm_kcalloc(a->dev,4,sizeof(*a->chan_props),0);if(!a->chan_props)return -ENOMEM;a->iio_chans=devm_kcalloc(a->dev,4,sizeof(*a->iio_chans),0);if(!a->iio_chans)return -ENOMEM;a->n_tm_channels=3;for(unsigned i=0;i<4;i++){struct adc5_channel_prop *p=&a->chan_props[i];p->chip=a;p->channel=i;p->adc_tm=i==0?ADC_TM_NONE:i==3?ADC_TM_NON_THERMAL:ADC_TM;p->sdam_index=i==3?1:0;p->tm_chan_index=i==3?1:i;p->timer=MEAS_INT_1S;p->generation=ADC5_GEN4;p->datasheet_name="fixture";p->high_thr_en=p->low_thr_en=1;INIT_LIST_HEAD(&p->thr_list);a->iio_chans[i].address=i;if(i==3){p->req_wq=alloc_workqueue("test",0,0);if(!p->req_wq)return -ENOMEM;INIT_WORK(&p->work,notify_adc_tm_fn);}}return 0;}
static void inject_irq(unsigned i,u8 high,u8 low,u8 fault,bool immediate) {assert(i<2&&irq_live[i]);pthread_mutex_lock(&hw_lock);reg_high[i]|=high;reg_low[i]|=low;reg_fault[i]=fault;reg_status[i]=(fault?ADC5_GEN3_STATUS1_CONV_FAULT:0)|(immediate?ADC5_GEN3_STATUS1_EOC:0);reg_eoc[i]=immediate?BIT(0):0;pthread_mutex_unlock(&hw_lock);irq_fn[i](10+i,irq_arg[i]);}
static int devm_request_irq(struct device *d,int irq,irqreturn_t (*fn)(int,void*),unsigned long flags,const char *name,void *p) {(void)d;(void)flags;(void)name;unsigned i=irq-10;assert(i<2&&!irq_live[i]);irq_requests++;if(fail_irq==irq_requests)return -EIO;irq_fn[i]=fn;irq_arg[i]=p;irq_live[i]=true;if(inject_request==(int)irq_requests)inject_irq(i,BIT(1),0,0,false);return 0;}
static void devm_free_irq(struct device *d,int irq,void *p) {(void)d;(void)p;unsigned i=irq-10;assert(i<2&&irq_live[i]);assert(!self_holds(&g_adc->lock));if(defer_eoc)assert(atomic_load(&conversion_data_read)&&"completion IRQ freed before conversion drained");irq_live[i]=false;irq_frees++;}
static void disable_irq(int irq) {unsigned i=irq-10;assert(irq_live[i]);irq_live[i]=false;}
static void enable_irq(int irq) {unsigned i=irq-10;assert(!irq_live[i]);irq_live[i]=true;}
static void synchronize_irq(int irq) {(void)irq;}
static bool schedule_work(struct work_struct *w) {assert(w->initialized&&"work queued before INIT_WORK");assert(registration_complete&&"TM queued before all thermal zones and IIO publication");pthread_mutex_lock(&w->lock);bool old=w->queued;w->queued=true;pthread_mutex_unlock(&w->lock);if(!old)atomic_fetch_add(&scheduled,1);bool known=false;for(unsigned i=0;i<n_work;i++)if(known_work[i]==w)known=true;if(!known){assert(n_work<ARRAY_SIZE(known_work));known_work[n_work++]=w;}return !old;}
static bool queue_work(struct workqueue_struct *q,struct work_struct *w) {assert(q&&!q->destroyed);return schedule_work(w);}
static bool cancel_work_sync(struct work_struct *w) {assert(w->initialized);assert(!self_holds(&g_adc->lock));pthread_mutex_lock(&latch_lock);if(pause_status||defer_eoc){quiesce_started=true;pthread_cond_broadcast(&latch_cv);}pthread_mutex_unlock(&latch_lock);if(inject_cancel&&irq_live[0]){inject_cancel=false;unsigned old=atomic_load(&scheduled);inject_irq(0,BIT(1),0,BIT(2),false);assert(atomic_load(&scheduled)==old);}pthread_mutex_lock(&w->lock);bool old=w->queued;w->queued=false;while(w->running)pthread_cond_wait(&w->cv,&w->lock);w->queued=false;pthread_mutex_unlock(&w->lock);return old;}
static bool run_one(struct work_struct *w) {pthread_mutex_lock(&w->lock);if(!w->queued){pthread_mutex_unlock(&w->lock);return false;}w->queued=false;w->running=true;pthread_mutex_unlock(&w->lock);w->fn(w);pthread_mutex_lock(&w->lock);w->running=false;pthread_cond_broadcast(&w->cv);pthread_mutex_unlock(&w->lock);return true;}
static void drain(void) {for(unsigned iter=0;iter<50;iter++){bool any=false;for(unsigned i=0;i<n_work;i++)any|=run_one(known_work[i]);if(!any)return;}assert(!"work did not settle");}
static int adc5_read(struct adc5_chip *a,unsigned s,u16 off,u8 *d,int n) {(void)a;assert(s<2);atomic_fetch_add(&hardware_reads,1);pthread_mutex_lock(&hw_lock);memset(d,0,n);if(off==ADC5_GEN3_EOC_STS)d[0]=reg_eoc[s];else if(off==ADC5_GEN3_STATUS1)d[0]=reg_status[s];else if(off==ADC5_GEN3_CONV_ERROR_STS)d[0]=reg_fault[s];else if(off==ADC5_GEN3_TM_HIGH_STS){d[0]=reg_high[s];if(n>1)d[1]=reg_low[s];}else if(off==ADC5_GEN3_CH0_DATA0){if(n==2)atomic_store(&conversion_data_read,true);for(int i=0;i<n;i++)d[i]=(i%2)?0x12:0x34;}pthread_mutex_unlock(&hw_lock);return 0;}
static int adc5_write(struct adc5_chip *a,unsigned s,u16 off,u8 *d,int n) {(void)a;assert(s<2);atomic_fetch_add(&hardware_writes,1);bool immediate=false;pthread_mutex_lock(&hw_lock);if(off==ADC5_GEN3_SID){perph[s]=d[1];atomic_fetch_add(&configures,1);}else if(off==ADC5_GEN3_PERPH_CH)perph[s]=d[0];else if(off==ADC5_GEN3_TM_HIGH_STS_CLR){reg_high[s]&=~d[0];if(n>1)reg_low[s]&=~d[1];}else if(off==ADC5_GEN3_CONV_ERR_CLR){reg_fault[s]&=~d[0];reg_status[s]&=~ADC5_GEN3_STATUS1_CONV_FAULT;}else if(off==ADC5_GEN3_CONV_REQ&&d[0]&&perph[s]==ADC5_GEN3_CHAN_CONV_REQ)immediate=true;pthread_mutex_unlock(&hw_lock);if(off==ADC5_GEN3_TM_HIGH_STS_CLR){pthread_mutex_lock(&latch_lock);if(pause_status){paused_status=true;pthread_cond_broadcast(&latch_cv);while(!release_status)pthread_cond_wait(&latch_cv,&latch_lock);}pthread_mutex_unlock(&latch_lock);}if(immediate&&irq_live[s]){pthread_mutex_lock(&latch_lock);conversion_started=true;pthread_cond_broadcast(&latch_cv);bool defer=defer_eoc;pthread_mutex_unlock(&latch_lock);if(!defer)inject_irq(s,0,0,0,true);}return 0;}
static int adc5_gen3_poll_wait_hs(struct adc5_chip *a,unsigned s) {(void)a;(void)s;return 0;}
static void adc5_gen3_dump_regs_debug(struct adc5_chip *a) {(void)a;}
static int adc_tm_gen3_manage_thresholds(struct adc5_channel_prop *p) {(void)p;return 0;}
static struct thermal_zone_device *devm_thermal_of_zone_register(struct device *d,int channel,void *p,const struct thermal_zone_device_ops *ops) {(void)d;(void)channel;zone_calls++;if(fail_zone==zone_calls)return ERR_PTR(-EIO);struct thermal_zone_device *t=allocation(sizeof(*t));if(!t)return ERR_PTR(-ENOMEM);t->priv=p;t->ops=ops;zones[n_zones++]=t;if(call_registration_callbacks){int temp;assert(ops->get_temp(t,&temp)==0);if(ops->set_trips)assert(ops->set_trips(t,1000,50000)==0);}if(inject_zone==(int)zone_calls)inject_irq(0,BIT(1)|BIT(2),0,BIT(2),false);return t;}
static int devm_iio_device_register(struct device *d,struct iio_dev *i) {(void)d;(void)i;if(inject_iio)inject_irq(0,BIT(1)|BIT(2),0,0,false);if(fail_iio)return -EIO;registration_complete=true;return 0;}
static int devm_add_action_or_reset(struct device *d,void(*fn)(void*),void *p) {(void)d;(void)fn;(void)p;return 0;}
static void devm_remove_action(struct device *d,void(*fn)(void*),void *p) {(void)d;(void)fn;(void)p;}
static void *ipc_log_context_create(int pages,const char *name,int flags) {(void)pages;(void)name;(void)flags;ipc_create++;return (void*)0x1234;}
static void ipc_log_context_destroy(void *p) {assert(p==(void*)0x1234);assert(ipc_destroy<ipc_create);ipc_destroy++;}
static void thermal_zone_device_update(struct thermal_zone_device *t,int why) {(void)why;assert(t&&!t->unregistered&&registration_complete);for(unsigned i=1;i<=2;i++)assert(g_adc->chan_props[i].tzd);atomic_fetch_add(&zone_updates,1);}
static void release_devm(void) {for(unsigned i=0;i<n_zones;i++){int temp;unsigned before=atomic_load(&hardware_reads)+atomic_load(&hardware_writes);assert(zones[i]->ops->get_temp(zones[i],&temp)==-ENODEV);assert(before==atomic_load(&hardware_reads)+atomic_load(&hardware_writes));zones[i]->unregistered=true;}for(unsigned i=0;i<2;i++)if(irq_live[i])devm_free_irq(&g_pdev.dev,10+i,g_adc);for(unsigned i=0;i<n_alloc;i++)free(allocations[i]);n_alloc=0;g_adc=NULL;g_iio=NULL;}
static void reset_fixture(void) {assert(n_alloc==0);memset(&g_pdev,0,sizeof(g_pdev));g_pdev.name="fixture";g_pdev.dev.parent=&g_parent;g_pdev.dev.of_node=&g_node;memset(irq_live,0,sizeof(irq_live));memset(reg_status,0,sizeof(reg_status));memset(reg_eoc,0,sizeof(reg_eoc));memset(reg_fault,0,sizeof(reg_fault));memset(reg_high,0,sizeof(reg_high));memset(reg_low,0,sizeof(reg_low));memset(perph,0,sizeof(perph));n_zones=n_work=0;irq_requests=irq_frees=zone_calls=ipc_create=ipc_destroy=queue_destroy=0;fail_irq=fail_zone=fail_alloc=alloc_calls=0;fail_iio=fail_dt=fail_regmap=false;inject_request=inject_zone=0;inject_iio=inject_cancel=call_registration_callbacks=registration_complete=false;pause_status=paused_status=release_status=defer_eoc=conversion_started=quiesce_started=conversion_fence_attempted=false;mutex_before_lock=lock_attempt_hook;pending_status=0;atomic_store(&scheduled,0);atomic_store(&zone_updates,0);atomic_store(&hardware_reads,0);atomic_store(&hardware_writes,0);atomic_store(&configures,0);atomic_store(&conversion_data_read,false);INIT_LIST_HEAD(&adc_tm_device_list);}
