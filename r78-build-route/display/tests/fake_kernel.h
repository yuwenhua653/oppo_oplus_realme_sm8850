#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <limits.h>
#define CONFIG_COMPAT 1
#define __user
#define GFP_KERNEL 0
#define MISC_DYNAMIC_MINOR 255
#define THIS_MODULE NULL
#define EPOLLIN 1
#define EPOLLRDNORM 64
#define EPOLLHUP 16
#define EPOLLERR 8
#define READ_ONCE(x) (x)
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define pr_info(...) ((void)0)
typedef uint32_t u32;
typedef unsigned int __poll_t;
typedef int poll_table;
struct mutex { int locked; };
#define DEFINE_MUTEX(n) struct mutex n
static void mutex_init(struct mutex*m){m->locked=0;}
static void mutex_lock(struct mutex*m){assert(!m->locked);m->locked=1;}
static int mutex_lock_interruptible(struct mutex*m){mutex_lock(m);return 0;}
static void mutex_unlock(struct mutex*m){assert(m->locked);m->locked=0;}
struct kref{int count;};
static void kref_init(struct kref*r){r->count=1;}
static void kref_get(struct kref*r){assert(r->count>0);r->count++;}
static void kref_put(struct kref*r,void(*f)(struct kref*)){assert(r->count>0);if(!--r->count)f(r);}
struct list_head {struct list_head*next,*prev;};
#define INIT_LIST_HEAD(h) ((h)->next=(h),(h)->prev=(h))
static void list_add_tail(struct list_head*n,struct list_head*h){n->prev=h->prev;n->next=h;h->prev->next=n;h->prev=n;}
static void list_del(struct list_head*n){n->prev->next=n->next;n->next->prev=n->prev;}
#define list_for_each_entry(p,h,m) for(p=container_of((h)->next,__typeof__(*p),m);&p->m!=(h);p=container_of(p->m.next,__typeof__(*p),m))
typedef struct{int wakes;}wait_queue_head_t;
static void init_waitqueue_head(wait_queue_head_t*w){w->wakes=0;}
static void wake_up_interruptible(wait_queue_head_t*w){w->wakes++;}
#define wait_event_interruptible(w,c) ((c)?0:-EINTR)
struct cdev;
struct inode{struct cdev*i_cdev;};
struct file{void*private_data;int f_flags;};
struct file_operations{void*owner;int(*open)(struct inode*,struct file*);int(*release)(struct inode*,struct file*);long(*unlocked_ioctl)(struct file*,unsigned int,unsigned long);long(*compat_ioctl)(struct file*,unsigned int,unsigned long);__poll_t(*poll)(struct file*,poll_table*);ssize_t(*read)(struct file*,char*,size_t,loff_t*);void*llseek;};
#define no_llseek NULL
static void poll_wait(struct file*f,wait_queue_head_t*w,poll_table*p){}
static void*compat_ptr(unsigned long x){return (void*)x;}
static int bad_copy;
static int copy_to_user(void*d,const void*s,size_t n){if(bad_copy)return 1;memcpy(d,s,n);return 0;}
static int copy_from_user(void*d,const void*s,size_t n){if(bad_copy)return 1;memcpy(d,s,n);return 0;}
static int alloc_fail, allocated_blocks;
static void*kzalloc(size_t n,int flags){if(alloc_fail)return NULL;allocated_blocks++;return calloc(1,n);}
static void kfree(void*p){if(p){allocated_blocks--;free(p);}}
struct class;
struct device {void*data;void(*release)(struct device*);struct class*class;dev_t devt;};
struct attribute{int dummy;};
struct device_attribute {struct attribute attr;};
#define DEVICE_ATTR_RO(n) struct device_attribute dev_attr_##n
#define DEVICE_ATTR_RW(n) struct device_attribute dev_attr_##n
#define ATTRIBUTE_GROUPS(n) static void*n##_groups
static void*dev_get_drvdata(struct device*d){return d->data;}
static int sysfs_emit(char*b,const char*f,...){va_list a;va_start(a,f);int r=vsprintf(b,f,a);va_end(a);return r;}
static int kstrtou32(const char*s,int b,u32*v){char*e;unsigned long n;if(*s=='-')return -EINVAL;errno=0;n=strtoul(s,&e,b);if(e==s||(*e&&strcmp(e,"\n")))return -EINVAL;if(errno||n>UINT32_MAX)return -ERANGE;*v=n;return 0;}
struct class {int dummy;};
static int failure_stage,classes,devices,miscdevices;
static struct class*class_create(const char*n){if(failure_stage==1)return ERR_PTR(-EEXIST);classes++;return calloc(1,sizeof(struct class));}
static void class_destroy(struct class*c){classes--;free(c);}
static struct device*device_create_with_groups(struct class*c,struct device*p,int n,void*d,void*g,const char*f){if(failure_stage==2)return ERR_PTR(-ENOMEM);struct device*r=calloc(1,sizeof(*r));r->data=d;devices++;return r;}
static void device_unregister(struct device*d){devices--;free(d);}
struct cdev{void*owner;};
static int regions;
static int alloc_chrdev_region(dev_t*d,int base,int count,const char*n){if(failure_stage==4)return -ENOMEM;regions++;*d=1;return 0;}
static void unregister_chrdev_region(dev_t d,int count){regions--;}
static void device_initialize(struct device*d){}
static int dev_set_name(struct device*d,const char*n){if(failure_stage==5)return -ENOMEM;return 0;}
static void put_device(struct device*d){d->release(d);}
static void cdev_init(struct cdev*c,const struct file_operations*f){}
static int cdev_device_add(struct cdev*c,struct device*d){if(failure_stage==3)return -EBUSY;miscdevices++;return 0;}
static void cdev_device_del(struct cdev*c,struct device*d){miscdevices--;}
struct device_node{int present,count;u32 maximum;};
static void*of_find_property(struct device_node*n,const char*p,void*x){return n->present?n:NULL;}
static int of_property_count_u32_elems(struct device_node*n,const char*p){return n->count;}
static int of_property_read_u32(struct device_node*n,const char*p,u32*v){*v=n->maximum;return 0;}
struct dsi_panel{struct device_node*panel_of_node;const char*name;};
struct platform_device{struct device dev;};
struct dsi_display{struct dsi_panel*panel;struct device_node*panel_node;const char*display_type;struct platform_device*pdev;};
