#ifndef R92_PROVIDER_TEST_SHIM_H
#define R92_PROVIDER_TEST_SHIM_H
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <stddef.h>
#include <errno.h>
typedef uint32_t u32;
typedef uint8_t u8;
typedef int spinlock_t;
#define spin_lock_init(lock) (*(lock)=0)
typedef unsigned long ulong;
#define PAGE_SIZE 4096
#define GFP_KERNEL 0
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define DEFINE_SPINLOCK(x) int x
static unsigned mock_lock_depth;
#define spin_lock_irqsave(lock,flags) do {assert(!*(lock));*(lock)=1;++mock_lock_depth;(flags)=0;} while(0)
#define spin_unlock_irqrestore(lock,flags) do {assert(*(lock));*(lock)=0;assert(mock_lock_depth);--mock_lock_depth;(void)(flags);} while(0)
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define MODULE_DEVICE_TABLE(a,b)
#define MODULE_DESCRIPTION(a)
#define MODULE_AUTHOR(a)
#define MODULE_LICENSE(a)
#define MODULE_PARM_DESC(a,b)
#define module_param_cb(name,ops,arg,mode) _Static_assert((mode)==0444, "diagnostics must be read only")
#define module_platform_driver(driver)
#define pr_info(...) mock_log(__VA_ARGS__)
#define mca_log_info(...) mock_log(__VA_ARGS__)
#define mca_log_err(...) mock_log(__VA_ARGS__)
struct notifier_block { int (*notifier_call)(struct notifier_block *,unsigned long,void *); };
struct device { int unused; };
struct platform_device { struct device dev; void *data; };
struct of_device_id { const char *compatible; };
struct platform_driver {
 struct { const char *name; const struct of_device_id *of_match_table; } driver;
 int (*probe)(struct platform_device *);
 void (*remove)(struct platform_device *);
 void (*shutdown)(struct platform_device *);
};
struct kernel_param { int unused; };
struct kernel_param_ops { int (*get)(char *, const struct kernel_param *); };
static int allocation_fail;
static void *devm_kzalloc(struct device *d,size_t n,int f) {(void)d;(void)f;return allocation_fail?NULL:calloc(1,n);}
static void platform_set_drvdata(struct platform_device *p,void *d) {p->data=d;}
static void *platform_get_drvdata(struct platform_device *p) {return p->data;}
static u32 swab32(u32 x) {return __builtin_bswap32(x);}
static int scnprintf(char *b,size_t n,const char *f,...) {va_list ap;va_start(ap,f);int r=vsnprintf(b,n,f,ap);va_end(ap);return r<0?r:(r>=(int)n?(int)n-1:r);}
static long strscpy(char *b,const char *s,size_t n) {if(!n)return -E2BIG;snprintf(b,n,"%s",s);return strlen(b);}
static void mock_log(const char *f,...) {(void)f;}
#endif
