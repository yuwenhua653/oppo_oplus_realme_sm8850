#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <stdarg.h>
typedef uint32_t u32;
#define GFP_KERNEL 0
#define FG_IC_MASTER 0
#define FG_IC_SLAVE 1
#define BATT_PARA_CC_NAME_LEN 50
#define BATT_PARA_CC_TEMP_23 23
#define BATT_PARA_CC_TEMP_30 30
#define BATT_PARA_CC_TEMP_40 40
#define mca_log_info(...) ((void)0)
#define mca_log_err(...) ((void)0)
#define mca_log_debug(...) ((void)0)
/* PRODUCTION_TYPES */
struct property { const char *name; const char **strings; int count; const u32 *numbers; int number_count; };
struct device_node { struct property *properties; int count; };
struct mca_quick_charge_info {
 bool support_base_flip; int batt_para_cc_thr[2];
 struct mca_quick_charge_batt_para_info batt_para[2], base_flip_para[2];
};
static int alloc_calls, live, alloc_fail, string_calls, string_fail, integer_calls, integer_fail, u32_calls, u32_fail;
static int diag_errno; static const char *diag_stage; static unsigned checks, scenarios;
static struct device_node *cc_node;
static void check(bool ok, const char *why) { checks++; if (!ok) { fprintf(stderr,"scenario %u check %u: %s\n",scenarios,checks,why); exit(21); } }
struct allocation { void *p; bool live; };
static struct allocation allocations[4096]; static int allocation_count;
static void *kcalloc(size_t n, size_t size, int flags) {
 (void)flags; if (++alloc_calls==alloc_fail) return NULL;
 void *p=calloc(n,size); check(p!=NULL,"host allocation"); check(allocation_count<4096,"allocation inventory");
 allocations[allocation_count++]=(struct allocation){p,true};live++;return p;
}
static void kfree(void *p) {
 if(!p)return;
 for(int i=allocation_count-1;i>=0;i--)if(allocations[i].p==p && allocations[i].live){allocations[i].live=false;live--;free(p);return;}
 check(false,"double or unknown free");
}
static void reset(void) {
 check(live==0,"all previous allocations released"); scenarios++; allocation_count=alloc_calls=string_calls=integer_calls=u32_calls=0;
 alloc_fail=string_fail=integer_fail=u32_fail=0;diag_errno=0;diag_stage=NULL;cc_node=NULL;
}
static struct property *property(const struct device_node *n, const char *name) {
 if(!n || !name)return NULL;for(int i=0;i<n->count;i++)if(!strcmp(name,n->properties[i].name))return &n->properties[i];return NULL;
}
static int of_property_count_strings(const struct device_node *n,const char *name) { struct property *p=property(n,name);return p&&p->strings?p->count:-EINVAL; }
static int of_property_read_string_index(const struct device_node *n,const char *name,int i,const char **out) {
 if(++string_calls==string_fail)return -EIO;struct property *p=property(n,name);if(!p||!p->strings||i<0||i>=p->count)return -EINVAL;*out=p->strings[i];return 0;
}
static int of_property_read_u32_array(const struct device_node *n,const char *name,u32 *out,u32 len) {
 if(++u32_calls==u32_fail)return -EIO;struct property *p=property(n,name);if(!p||!p->numbers||p->number_count<(int)len)return -EINVAL;memcpy(out,p->numbers,len*sizeof(*out));return 0;
}
static struct device_node *of_find_node_by_name(struct device_node *n,const char *name) { (void)n;check(!strcmp(name,"mca_parallel_cyclecount_para"),"expected CC node");return cc_node; }
static int kstrtoint(const char *s,int base,int *out) {
 if(++integer_calls==integer_fail)return -ERANGE;char *end;errno=0;long v=strtol(s,&end,base);if(errno||*end||end==s||v<INT_MIN||v>INT_MAX)return -EINVAL;*out=(int)v;return 0;
}
static void mca_quick_charge_diag_note(struct mca_quick_charge_info *info,const char *stage,int error) { (void)info;diag_stage=stage;diag_errno=error; }
