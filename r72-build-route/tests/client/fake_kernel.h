#ifndef MR_FAKE_KERNEL_H
#define MR_FAKE_KERNEL_H
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <pthread.h>
#include <time.h>
#include <stdatomic.h>
typedef uint32_t u32; typedef uint64_t u64; typedef uint8_t u8;
#define U32_MAX UINT32_MAX
#define __packed __attribute__((packed))
#define __init
#define __exit
#define GFP_KERNEL 0
#define EPROBE_DEFER 517
#define IS_ENABLED(x) 1
#define module_param(a,b,c)
#define MODULE_PARM_DESC(a,b)
#define MODULE_DESCRIPTION(a)
#define MODULE_LICENSE(a)
#define module_init(a)
#define module_exit(a)
#define PAGE_SIZE 4096
struct device_node { const char *full_name; };
struct kobject { int unused; };
struct device { void *data; struct device *parent; struct device_node *of_node; struct kobject kobj; };
struct platform_device { struct device dev; };
typedef pthread_mutex_t spinlock_t;
#define spin_lock_init(s) assert(!pthread_mutex_init((s),NULL))
#define spin_lock_irqsave(s,f) do{(f)=0;assert(!pthread_mutex_lock(s));}while(0)
#define spin_unlock_irqrestore(s,f) do{(void)(f);assert(!pthread_mutex_unlock(s));}while(0)
struct completion { pthread_mutex_t lock; pthread_cond_t cv; unsigned done; };
static inline void init_completion(struct completion *c){assert(!pthread_mutex_init(&c->lock,NULL));assert(!pthread_cond_init(&c->cv,NULL));c->done=0;}
static inline void reinit_completion(struct completion *c){assert(!pthread_mutex_lock(&c->lock));c->done=0;assert(!pthread_mutex_unlock(&c->lock));}
static inline void complete(struct completion *c){assert(!pthread_mutex_lock(&c->lock));c->done++;assert(!pthread_cond_broadcast(&c->cv));assert(!pthread_mutex_unlock(&c->lock));}
static inline unsigned long msecs_to_jiffies(unsigned long m){return m;}
static inline unsigned long wait_for_completion_timeout(struct completion *c,unsigned long ms){
 struct timespec t;int rc=0;assert(!clock_gettime(CLOCK_REALTIME,&t));t.tv_sec+=ms/1000;t.tv_nsec+=(ms%1000)*1000000;if(t.tv_nsec>=1000000000){t.tv_sec++;t.tv_nsec-=1000000000;}
 assert(!pthread_mutex_lock(&c->lock));while(!c->done&&rc!=ETIMEDOUT){rc=pthread_cond_timedwait(&c->cv,&c->lock,&t);assert(!rc||rc==ETIMEDOUT);}unsigned long done=c->done?1:0;if(c->done)c->done--;assert(!pthread_mutex_unlock(&c->lock));return done;
}
struct work_struct { void (*fn)(struct work_struct *); };
struct delayed_work { struct work_struct work; pthread_mutex_t lock; pthread_cond_t cv; bool queued,running; unsigned long delay; };
static inline void fake_init_work(struct delayed_work *w,void (*fn)(struct work_struct *)){w->work.fn=fn;assert(!pthread_mutex_init(&w->lock,NULL));assert(!pthread_cond_init(&w->cv,NULL));w->queued=w->running=false;}
#define INIT_DELAYED_WORK(w,fn) fake_init_work((w),(fn))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define to_delayed_work(p) container_of(p,struct delayed_work,work)
static inline bool schedule_delayed_work(struct delayed_work *w,unsigned long ms){assert(!pthread_mutex_lock(&w->lock));bool new=!w->queued;w->queued=true;w->delay=ms;assert(!pthread_mutex_unlock(&w->lock));return new;}
static inline bool cancel_delayed_work_sync(struct delayed_work *w){assert(!pthread_mutex_lock(&w->lock));bool old=w->queued;w->queued=false;while(w->running)assert(!pthread_cond_wait(&w->cv,&w->lock));w->queued=false;assert(!pthread_mutex_unlock(&w->lock));return old;}
static inline void *kzalloc(size_t size,int flags){(void)flags;return calloc(1,size);}
void kfree(void *p);
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define PTR_ERR(p) ((long)(p))
#define ERR_PTR(n) ((void *)(intptr_t)(n))
static inline void platform_set_drvdata(struct platform_device *p,void *d){p->dev.data=d;}
static inline void *platform_get_drvdata(struct platform_device *p){return p->dev.data;}
static inline void *dev_get_drvdata(struct device *p){return p->data;}
static atomic_uint_fast64_t fake_clock=1000000;
static inline u64 ktime_get_boottime_ns(void){return atomic_fetch_add(&fake_clock,1000000);}
static u32 random_seed=1000;
static inline u32 get_random_u32(void){return random_seed;}
struct attribute { const char *name; unsigned mode; };
struct device_attribute { struct attribute attr; ssize_t (*show)(struct device *,struct device_attribute *,char *); };
#define DEVICE_ATTR_RO(n) struct device_attribute dev_attr_##n={{#n,0444},n##_show}
struct attribute_group { const char *name; struct attribute **attrs; };
int sysfs_create_group(struct kobject *,const struct attribute_group *);
void sysfs_remove_group(struct kobject *,const struct attribute_group *);
int sysfs_emit(char *,const char *,...);
int sysfs_emit_at(char *,int,const char *,...);
struct of_device_id { const char *compatible; };
struct platform_driver { int (*probe)(struct platform_device *);void (*remove)(struct platform_device *);struct {const char *name;const struct of_device_id *of_match_table;bool suppress_bind_attrs;} driver; };
int platform_driver_register(struct platform_driver *);
void platform_driver_unregister(struct platform_driver *);
#endif
