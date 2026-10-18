#ifndef R72_FAKE_KERNEL_H
#define R72_FAKE_KERNEL_H
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <stdatomic.h>
#include <time.h>
#include <unistd.h>
typedef uint32_t u32; typedef uint8_t u8;
#define GFP_KERNEL 0
#define EPROBE_DEFER 517
#define IS_ENABLED(x) 1
#define EXPORT_SYMBOL(x)
#define pr_err(...) ((void)0)
#define pr_info(...) ((void)0)
#define pmic_glink_dbg(...) ((void)0)
#define BUG_ON(x) assert(!(x))
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((long)(intptr_t)(p))
struct task_struct { char unused; }; static _Thread_local struct task_struct fake_task;
#define current (&fake_task)
struct list_head {struct list_head *next,*prev;};
#define LIST_HEAD(name) struct list_head name={&(name),&(name)}
#define INIT_LIST_HEAD(h) do{(h)->next=(h);(h)->prev=(h);}while(0)
static inline void list_add(struct list_head*n,struct list_head*h){n->next=h->next;n->prev=h;h->next->prev=n;h->next=n;}
static inline void list_add_tail(struct list_head*n,struct list_head*h){n->next=h;n->prev=h->prev;h->prev->next=n;h->prev=n;}
static inline void list_del(struct list_head*n){n->prev->next=n->next;n->next->prev=n->prev;n->next=n->prev=NULL;}
static inline bool list_empty(struct list_head*h){return h->next==h;}
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define list_for_each_entry(p,h,m) for(struct list_head*_it=(h)->next;_it!=(h)&&((p)=container_of(_it,__typeof__(*(p)),m),1);_it=_it->next)
#define list_for_each_entry_safe(p,tmp,h,m) for(struct list_head*_it=(h)->next,*_next;_it!=(h)&&(_next=_it->next,(p)=container_of(_it,__typeof__(*(p)),m),(tmp)=_next==(h)?NULL:container_of(_next,__typeof__(*(tmp)),m),1);_it=_next)
struct mutex {pthread_mutex_t lock;};
#define DEFINE_MUTEX(name) struct mutex name={PTHREAD_MUTEX_INITIALIZER}
static void (*mutex_hook)(struct mutex *);
static inline void mutex_init(struct mutex*m){assert(!pthread_mutex_init(&m->lock,NULL));}
static inline void mutex_lock(struct mutex*m){if(mutex_hook)mutex_hook(m);assert(!pthread_mutex_lock(&m->lock));}
static inline void mutex_unlock(struct mutex*m){assert(!pthread_mutex_unlock(&m->lock));}
typedef pthread_mutex_t spinlock_t;
#define DEFINE_SPINLOCK(name) spinlock_t name=PTHREAD_MUTEX_INITIALIZER
#define spin_lock_irqsave(s,f) do{(f)=0;assert(!pthread_mutex_lock(s));}while(0)
#define spin_unlock_irqrestore(s,f) do{(void)(f);assert(!pthread_mutex_unlock(s));}while(0)
struct rw_semaphore {pthread_rwlock_t lock;};
static inline void init_rwsem(struct rw_semaphore*s){assert(!pthread_rwlock_init(&s->lock,NULL));}
static inline void down_read(struct rw_semaphore*s){assert(!pthread_rwlock_rdlock(&s->lock));}
static inline void up_read(struct rw_semaphore*s){assert(!pthread_rwlock_unlock(&s->lock));}
typedef atomic_int atomic_t;
#define atomic_set(a,v) atomic_store((a),(v))
#define atomic_read(a) atomic_load(a)
typedef atomic_uint refcount_t;
static inline void refcount_set(refcount_t*r,unsigned n){atomic_store(r,n);}
static inline void refcount_inc(refcount_t*r){unsigned n=atomic_fetch_add(r,1);assert(n&&n<UINT_MAX);}
static inline bool refcount_dec_and_test(refcount_t*r){unsigned n=atomic_fetch_sub(r,1);assert(n);return n==1;}
struct completion {pthread_mutex_t lock;pthread_cond_t cv;unsigned done;};
static void (*wait_hook)(struct completion *);
static inline void init_completion(struct completion*c){assert(!pthread_mutex_init(&c->lock,NULL));assert(!pthread_cond_init(&c->cv,NULL));c->done=0;}
static inline void complete(struct completion*c){assert(!pthread_mutex_lock(&c->lock));c->done++;assert(!pthread_cond_broadcast(&c->cv));assert(!pthread_mutex_unlock(&c->lock));}
static inline void wait_for_completion(struct completion*c){if(wait_hook)wait_hook(c);assert(!pthread_mutex_lock(&c->lock));while(!c->done)assert(!pthread_cond_wait(&c->cv,&c->lock));c->done--;assert(!pthread_mutex_unlock(&c->lock));}
struct idr {void *p[32];int id[32];};
static void (*idr_remove_hook)(void *);
static inline void idr_init(struct idr*i){memset(i,0,sizeof(*i));}
static inline void *idr_find(struct idr*i,int id){for(unsigned n=0;n<32;n++)if(i->p[n]&&i->id[n]==id)return i->p[n];return NULL;}
static inline int idr_alloc(struct idr*i,void*p,int start,int end,int flags){(void)flags;if(start<0||end<=start)return -EINVAL;if(idr_find(i,start))return -ENOSPC;for(unsigned n=0;n<32;n++)if(!i->p[n]){i->p[n]=p;i->id[n]=start;return start;}return -ENOSPC;}
static inline void idr_remove(struct idr*i,int id){for(unsigned n=0;n<32;n++)if(i->p[n]&&i->id[n]==id){void*p=i->p[n];i->p[n]=NULL;if(idr_remove_hook)idr_remove_hook(p);return;}}
static inline void *idr_get_next(struct idr*i,int*id){void*p=NULL;int best=INT_MAX;for(unsigned n=0;n<32;n++)if(i->p[n]&&i->id[n]>=*id&&(!p||i->id[n]<best)){p=i->p[n];best=i->id[n];}if(p)*id=best;return p;}
struct device {struct device *parent;};
struct rpmsg_device {void*ept;}; struct dentry; struct work_struct {int dummy;};struct workqueue_struct;struct notifier_block {int dummy;};
static inline void pm_stay_awake(struct device*d){(void)d;}
static inline void pm_relax(struct device*d){(void)d;}
static inline void *kzalloc(size_t n,int flags){(void)flags;return calloc(1,n);}
static inline char *kstrdup(const char*s,int flags){(void)flags;return strdup(s);}
static inline void kfree(const void*p){free((void*)p);}
static inline void usleep_range(unsigned a,unsigned b){(void)a;(void)b;}
static atomic_uint write_count;
static inline int rpmsg_send(void*ept,void*data,size_t len){assert(ept&&data&&len>=12);atomic_fetch_add(&write_count,1);return 0;}
#endif
