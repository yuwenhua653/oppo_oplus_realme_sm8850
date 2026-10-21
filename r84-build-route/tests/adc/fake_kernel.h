#ifndef ADC_LIFECYCLE_FAKE_KERNEL_H
#define ADC_LIFECYCLE_FAKE_KERNEL_H
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <stdarg.h>
#include <pthread.h>
#include <stdatomic.h>
#include <time.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef unsigned long gfp_t;
typedef int irqreturn_t;
typedef pthread_mutex_t spinlock_t;
#define BIT(n) (1U << (n))
#define GENMASK(h,l) (((~0U) << (l)) & (~0U >> (31 - (h))))
#define FIELD_PREP(mask,val) (((unsigned)(val) << __builtin_ctz(mask)) & (mask))
#define FIELD_GET(mask,val) (((unsigned)(val) & (mask)) >> __builtin_ctz(mask))
#define IRQ_HANDLED 1
#define IRQ_NONE 0
#define GFP_KERNEL 0
#define WQ_HIGHPRI 0
#define IIO_VAL_INT 1
#define IIO_CHAN_INFO_PROCESSED 1
#define IIO_CHAN_INFO_RAW 2
#define INDIO_DIRECT_MODE 0
#define THERMAL_TRIP_VIOLATED 1
#define PM_SUSPEND_MEM 3
#define EPROBE_DEFER 517
#define unlikely(x) (x)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define container_of(ptr,type,member) ((type *)((char *)(ptr)-offsetof(type,member)))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((long)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) > (uintptr_t)-4096)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
#define min(a,b) ((a)<(b)?(a):(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define lower_32_bits(x) ((u32)(x))
#define EXPORT_SYMBOL_GPL(x)
#define pr_err(...) ((void)0)
#define pr_err_ratelimited(...) ((void)0)
static void fake_log(const char *fmt,...) {(void)fmt;}
#define pr_debug(...) fake_log(__VA_ARGS__)
#define pr_warn(...) ((void)0)
#define dev_err(...) ((void)0)
#define dev_dbg(...) ((void)0)
#define dev_warn(...) ((void)0)
#define dev_err_probe(dev,err,...) (err)
#define scnprintf snprintf

struct list_head { struct list_head *next,*prev; };
#define LIST_HEAD(name) struct list_head name = { &(name), &(name) }
static void INIT_LIST_HEAD(struct list_head *h) { h->next=h;h->prev=h; }
static bool list_empty(const struct list_head *h) { return h->next==h; }
static void list_add_tail(struct list_head *n,struct list_head *h) { n->prev=h->prev;n->next=h;h->prev->next=n;h->prev=n; }
static void list_del(struct list_head *n) { n->prev->next=n->next;n->next->prev=n->prev;n->next=n->prev=NULL; }
static void list_del_init(struct list_head *n) { list_del(n);INIT_LIST_HEAD(n); }
#define list_entry(ptr,type,member) container_of(ptr,type,member)
#define list_for_each_entry(pos,head,member) for (pos=list_entry((head)->next,__typeof__(*pos),member); &(pos)->member!=(head);pos=list_entry((pos)->member.next,__typeof__(*pos),member))
#define list_for_each(pos,head) for (pos=(head)->next;pos!=(head);pos=pos->next)

struct mutex { pthread_mutex_t p; };
#define DEFINE_MUTEX(name) struct mutex name = { PTHREAD_MUTEX_INITIALIZER }
static _Thread_local struct mutex *held_mutexes[16];
static _Thread_local unsigned held_count;
static void (*mutex_before_lock)(struct mutex *);
static bool self_holds(struct mutex *m) { for(unsigned i=0;i<held_count;i++)if(held_mutexes[i]==m)return true;return false; }
static void mutex_init(struct mutex *m) { assert(!pthread_mutex_init(&m->p,NULL)); }
static void mutex_destroy(struct mutex *m) { assert(!self_holds(m));assert(!pthread_mutex_destroy(&m->p)); }
static void mutex_lock(struct mutex *m) { assert(!self_holds(m));if(mutex_before_lock)mutex_before_lock(m);assert(!pthread_mutex_lock(&m->p));held_mutexes[held_count++]=m; }
static void mutex_unlock(struct mutex *m) { assert(self_holds(m));for(unsigned i=0;i<held_count;i++)if(held_mutexes[i]==m){held_mutexes[i]=held_mutexes[--held_count];break;}assert(!pthread_mutex_unlock(&m->p)); }
static void spin_lock_init(spinlock_t *s) { assert(!pthread_mutex_init(s,NULL)); }
static void spin_lock(spinlock_t *s) { assert(!pthread_mutex_lock(s)); }
static void spin_unlock(spinlock_t *s) { assert(!pthread_mutex_unlock(s)); }
#define spin_lock_irqsave(s,f) do {(f)=0;spin_lock(s);} while(0)
#define spin_unlock_irqrestore(s,f) do {(void)(f);spin_unlock(s);} while(0)
#define lockdep_assert_held(x) assert(self_holds(x))
struct completion { unsigned done;pthread_mutex_t lock;pthread_cond_t cv; };
static void init_completion(struct completion *c) { c->done=0;assert(!pthread_mutex_init(&c->lock,NULL));assert(!pthread_cond_init(&c->cv,NULL)); }
static void reinit_completion(struct completion *c) { pthread_mutex_lock(&c->lock);c->done=0;pthread_mutex_unlock(&c->lock); }
static void complete(struct completion *c) { pthread_mutex_lock(&c->lock);c->done++;pthread_cond_broadcast(&c->cv);pthread_mutex_unlock(&c->lock); }
static unsigned long wait_for_completion_timeout(struct completion *c,unsigned long t) { struct timespec end;clock_gettime(CLOCK_REALTIME,&end);end.tv_nsec+=(long)t*1000000;end.tv_sec+=end.tv_nsec/1000000000;end.tv_nsec%=1000000000;pthread_mutex_lock(&c->lock);while(!c->done){int rc=pthread_cond_timedwait(&c->cv,&c->lock,&end);if(rc==ETIMEDOUT){pthread_mutex_unlock(&c->lock);return 0;}assert(!rc);}c->done--;pthread_mutex_unlock(&c->lock);return t; }
static unsigned long msecs_to_jiffies(unsigned long t) { return t; }
static unsigned int jiffies_to_msecs(unsigned long t) { return (unsigned)t; }

struct work_struct { bool initialized,queued,running; void (*fn)(struct work_struct *);pthread_mutex_t lock;pthread_cond_t cv; };
struct workqueue_struct { bool destroyed; };
static void INIT_WORK(struct work_struct *w,void (*fn)(struct work_struct *)) { assert(!w->queued);w->initialized=true;w->fn=fn;assert(!pthread_mutex_init(&w->lock,NULL));assert(!pthread_cond_init(&w->cv,NULL)); }
static bool schedule_work(struct work_struct *w);
static bool queue_work(struct workqueue_struct *q,struct work_struct *w);
static bool cancel_work_sync(struct work_struct *w);
static void destroy_workqueue(struct workqueue_struct *q);
static struct workqueue_struct *alloc_workqueue(const char *name,unsigned flags,int max);

enum vadc_generation { ADC5_GEN3,ADC5_GEN4 };
enum vadc_scale_fn_type { SCALE_HW_CALIB_DEFAULT };
enum adc_tm_rscale_fn_type { SCALE_RSCALE_NONE };
struct adc5_data { int unused; };
struct adc_tm_config { int high_thr_temp,low_thr_temp; int64_t high_thr_voltage,low_thr_voltage; };
struct adc_tm_param { uintptr_t id; int low_thr,high_thr,state_request,channel; void (*threshold_notification)(int,void*);void *btm_ctx; };
struct device_node { int id; };
struct regmap { int unused; };
struct device { struct device *parent; struct device_node *of_node; void *drvdata; };
struct platform_device { struct device dev; const char *name; };
struct iio_chan_spec { unsigned address,channel; const char *datasheet_name,*extend_name; long info_mask_separate; int type; };
struct iio_info { int unused; };
struct iio_dev { struct device dev; const struct iio_info *info; const char *name; int modes,num_channels; struct iio_chan_spec *channels; unsigned char priv[2048] __attribute__((aligned(16))); };
struct thermal_zone_device;
struct thermal_zone_device_ops { int (*get_temp)(struct thermal_zone_device *,int *); int (*set_trips)(struct thermal_zone_device *,int,int); };
struct thermal_zone_device { void *priv; const struct thermal_zone_device_ops *ops; bool unregistered; };
static inline void *thermal_zone_device_priv(struct thermal_zone_device *t) { assert(t&&!t->unregistered);return t->priv; }
static void *iio_priv(struct iio_dev *d) { return d->priv; }
static void platform_set_drvdata(struct platform_device *d,void *p) { d->dev.drvdata=p; }
static void *platform_get_drvdata(struct platform_device *d) { return d->dev.drvdata; }
static void *dev_get_drvdata(struct device *d) { return d->drvdata; }
static struct platform_device *to_platform_device(struct device *d) { return container_of(d,struct platform_device,dev); }
static struct regmap *dev_get_regmap(struct device *d,const char *name);
static struct iio_dev *devm_iio_device_alloc(struct device *d,size_t size);
static void *devm_kcalloc(struct device *d,size_t count,size_t size,gfp_t flags);
static char *devm_kstrdup(struct device *d,const char *s,gfp_t flags);
static int of_property_count_u32_elems(struct device_node *n,const char *key);
static int of_property_read_u32_index(struct device_node *n,const char *key,int i,u32 *v);
static int of_property_read_u32(struct device_node *n,const char *key,u32 *v);
static int of_irq_get_byname(struct device_node *n,const char *name);
static int devm_request_irq(struct device *d,int irq,irqreturn_t (*fn)(int,void*),unsigned long flags,const char *name,void *p);
static void devm_free_irq(struct device *d,int irq,void *p);
static void disable_irq(int irq);
static void enable_irq(int irq);
static void synchronize_irq(int irq);
static int devm_iio_device_register(struct device *d,struct iio_dev *i);
static struct thermal_zone_device *devm_thermal_of_zone_register(struct device *d,int channel,void *p,const struct thermal_zone_device_ops *ops);
static int devm_add_action_or_reset(struct device *d,void (*fn)(void*),void *p);
static void devm_remove_action(struct device *d,void (*fn)(void*),void *p);
static void *ipc_log_context_create(int pages,const char *name,int flags);
static void ipc_log_context_destroy(void *p);
static void ipc_log_string(void *p,const char *fmt,...) { (void)p;(void)fmt; }
static void thermal_zone_device_update(struct thermal_zone_device *t,int why);
static int qcom_adc5_hw_scale(enum vadc_scale_fn_type scale,unsigned prescale,const struct adc5_data *d,u16 code,int *out) { (void)scale;(void)prescale;(void)d;*out=code;return 0; }
static void adc_tm_scale_therm_voltage_100k_gen3(struct adc_tm_config *c,const struct adc5_data *d) { (void)d;c->low_thr_voltage=100;c->high_thr_voltage=200; }
static int pm_suspend_target_state;
#endif
