#ifndef R71_FAKE_KERNEL_H
#define R71_FAKE_KERNEL_H
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <time.h>
#include <unistd.h>
typedef uint32_t u32;
typedef uint8_t u8;
#define __packed __attribute__((packed))
#define GFP_KERNEL 0
#define EPROBE_DEFER 517
#define EXPORT_SYMBOL(x)
#define MODULE_DESCRIPTION(x)
#define MODULE_AUTHOR(x)
#define MODULE_LICENSE(x)
#define module_platform_driver(x)
#define mca_log_err(...) ((void)0)
#define mca_log_info(...) ((void)0)
struct device { void *data; };
struct platform_device { struct device dev; };
struct mutex { pthread_mutex_t v; };
static inline void mutex_init(struct mutex *m) { assert(!pthread_mutex_init(&m->v, NULL)); }
static inline void mutex_lock(struct mutex *m) { assert(!pthread_mutex_lock(&m->v)); }
static inline void mutex_unlock(struct mutex *m) { assert(!pthread_mutex_unlock(&m->v)); }
typedef pthread_mutex_t spinlock_t;
#define spin_lock_init(s) assert(!pthread_mutex_init((s), NULL))
#define spin_lock_irqsave(s, flags) do { (flags) = 0; assert(!pthread_mutex_lock(s)); } while (0)
#define spin_unlock_irqrestore(s, flags) do { (void)(flags); assert(!pthread_mutex_unlock(s)); } while (0)
struct completion { pthread_mutex_t lock; pthread_cond_t cv; unsigned done; };
static inline void init_completion(struct completion *c) { assert(!pthread_mutex_init(&c->lock,NULL)); assert(!pthread_cond_init(&c->cv,NULL)); c->done=0; }
static inline void reinit_completion(struct completion *c) { assert(!pthread_mutex_lock(&c->lock)); c->done=0; assert(!pthread_mutex_unlock(&c->lock)); }
static inline void complete(struct completion *c) { assert(!pthread_mutex_lock(&c->lock)); c->done++; assert(!pthread_cond_broadcast(&c->cv)); assert(!pthread_mutex_unlock(&c->lock)); }
static inline unsigned long msecs_to_jiffies(unsigned long x) { return x; }
static inline unsigned long wait_for_completion_timeout(struct completion *c, unsigned long ms) {
 struct timespec ts; int ret=0; assert(!clock_gettime(CLOCK_REALTIME,&ts));
 ts.tv_sec += ms/1000; ts.tv_nsec += (ms%1000)*1000000; if(ts.tv_nsec>=1000000000){ts.tv_sec++;ts.tv_nsec-=1000000000;}
 assert(!pthread_mutex_lock(&c->lock));
 while(!c->done && ret!=ETIMEDOUT) { ret=pthread_cond_timedwait(&c->cv,&c->lock,&ts); assert(!ret||ret==ETIMEDOUT); }
 unsigned long ok=c->done?1:0; if(c->done)c->done--; assert(!pthread_mutex_unlock(&c->lock)); return ok;
}
struct list_head { struct list_head *next,*prev; };
#define LIST_HEAD(name) struct list_head name={&(name),&(name)}
static inline void list_add(struct list_head *n,struct list_head *h) { n->next=h->next;n->prev=h;h->next->prev=n;h->next=n; }
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define list_for_each_entry(p,h,m) for(struct list_head *_it=(h)->next;_it!=(h) && ((p)=container_of(_it,__typeof__(*(p)),m),1);_it=_it->next)
struct work_struct { void (*fn)(struct work_struct *); };
#define INIT_WORK(w,f) ((w)->fn=(f))
static int system_wq;
static inline bool queue_work(void *wq,struct work_struct *w) { (void)wq;(void)w;return true; }
#define system_wq (&system_wq)
static inline void *kzalloc(size_t n,int flags) { (void)flags;return calloc(1,n); }
static inline void *devm_kzalloc(struct device *d,size_t n,int flags) { (void)d;return kzalloc(n,flags); }
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define PTR_ERR(p) ((long)(p))
static inline void platform_set_drvdata(struct platform_device *p,void *d) { p->dev.data=d; }
struct of_device_id { const char *compatible; };
struct platform_driver { struct { const char *name;const struct of_device_id *of_match_table; } driver;int (*probe)(struct platform_device *);void (*remove)(struct platform_device *); };
#define IS_ENABLED(x) 1
#endif
