#ifndef MYRON_TEST_FAKE_KERNEL_H
#define MYRON_TEST_FAKE_KERNEL_H
#include <assert.h>
#include <stdarg.h>
#include <stddef.h>
#include <sys/types.h>
#include <pthread.h>

#include <stdbool.h>
#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <asm-generic/errno.h>
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define GFP_KERNEL 0
#define I2C_FUNC_SMBUS_READ_WORD_DATA 0x80000
#define __init
#define __exit
#define module_init(x)
#define module_exit(x)
#define module_param(a,b,c)
#define MODULE_PARM_DESC(a,b)
#define MODULE_DEVICE_TABLE(a,b)
#define MODULE_DESCRIPTION(a)
#define MODULE_LICENSE(a)
#define dev_info(...) ((void)0)
#define dev_err_probe(dev,ret,...) (ret)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
typedef int16_t s16;
struct device { void *of_node; pthread_mutex_t lock; bool lock_held; };
static void device_lock(struct device *d){assert(!pthread_mutex_lock(&d->lock));assert(!d->lock_held);d->lock_held=true;}
static void device_unlock(struct device *d){assert(d->lock_held);d->lock_held=false;assert(!pthread_mutex_unlock(&d->lock));}
struct attribute { const char *name; unsigned int mode; };
struct device_attribute { struct attribute attr;ssize_t (*show)(struct device *,struct device_attribute *,char *);void *store; };
struct attribute_group { const char *name;struct attribute **attrs; };
#define DEVICE_ATTR_RO(name) struct device_attribute dev_attr_##name = { .attr={#name,0444}, .show=name##_show, .store=NULL }
#define to_power_supply(d) ((struct power_supply *)((char *)(d)-offsetof(struct power_supply,dev)))
static int sysfs_emit(char *buf,const char *fmt,...){va_list ap;va_start(ap,fmt);int n=vsnprintf(buf,4096,fmt,ap);va_end(ap);return n;}

struct i2c_client { struct device dev; unsigned int addr; void *adapter; void *data; };
static void i2c_set_clientdata(struct i2c_client *c,void *p){c->data=p;}
static void *i2c_get_clientdata(struct i2c_client *c){return c->data;}
struct of_device_id { const char *compatible; };
struct i2c_driver { struct { const char *name; const struct of_device_id *of_match_table; } driver;int (*probe)(struct i2c_client *);void (*remove)(struct i2c_client *); };
struct mutex { int held; };
static void mutex_init(struct mutex *m){m->held=0;}
static void mutex_lock(struct mutex *m){assert(!m->held);m->held=1;}
static void mutex_unlock(struct mutex *m){assert(m->held);m->held=0;}
enum power_supply_property { POWER_SUPPLY_PROP_STATUS,POWER_SUPPLY_PROP_HEALTH,POWER_SUPPLY_PROP_CAPACITY,POWER_SUPPLY_PROP_VOLTAGE_NOW,POWER_SUPPLY_PROP_TEMP,POWER_SUPPLY_PROP_PRESENT,POWER_SUPPLY_PROP_CURRENT_NOW,POWER_SUPPLY_PROP_MODEL_NAME,POWER_SUPPLY_PROP_ONLINE };
enum { POWER_SUPPLY_STATUS_UNKNOWN=0,POWER_SUPPLY_STATUS_CHARGING=1,POWER_SUPPLY_STATUS_DISCHARGING=2,POWER_SUPPLY_STATUS_NOT_CHARGING=3,POWER_SUPPLY_STATUS_FULL=4,POWER_SUPPLY_HEALTH_UNKNOWN=0,POWER_SUPPLY_TYPE_BATTERY=1 };
union power_supply_propval { int intval; const char *strval; };
struct power_supply;
struct power_supply_desc { const char *name;int type;enum power_supply_property *properties;size_t num_properties;int (*get_property)(struct power_supply *,enum power_supply_property,union power_supply_propval *);void *set_property,*property_is_writeable;void (*external_power_changed)(struct power_supply *);bool no_thermal; };
struct power_supply_config { void *drv_data,*of_node; const struct attribute_group **attr_grp; };
struct power_supply { struct device dev;void *drv_data;const struct power_supply_desc *desc;const struct attribute_group **groups;bool removing; };
struct resource { void *ptr;int type; };
static struct resource resources[8];static int nr;
static int values[5],reads,ports[128],fail_at,read_error;
static bool compatible,capable,alloc_fail,existing_psy,auto_attach;
static int monitored_form,register_error,refs,registrations,unregistrations,driver_adds,driver_dels,driver_error,probe_attempts,owner;
static int release_order[8],release_count;
static struct power_supply *active_psy;static struct power_supply prior_psy;
static struct power_supply usb_psy={.dev={.lock=PTHREAD_MUTEX_INITIALIZER}};
static bool usb_exists,usb_context_alive;
static const char *usb_model;
static int usb_status,usb_model_error,usb_status_error,usb_refs,usb_puts,usb_lookups,usb_model_calls,usb_status_calls,changed_calls;
static void (*property_hook)(enum power_supply_property);
static void (*changed_hook)(void);
static void assert_no_gauge_lock(void);
static struct i2c_driver *registered_driver;
static struct i2c_client client={.dev={.of_node=(void *)1},.addr=0x55,.adapter=(void *)1};
static int i2c_smbus_read_word_data(struct i2c_client *c,unsigned char reg){
 assert(c==&client);int i=reg==0x2c?0:reg==0x08?1:reg==0x06?2:reg==0x0c?3:reg==0x0a?4:-1;assert(i>=0);assert(reads<128);ports[reads++]=reg;
 if(reads==fail_at)return read_error;return values[i];
}
static bool of_device_is_compatible(void *node,const char *name){assert(!strcmp(name,"ti,bq27z561_master"));return compatible;}
static bool i2c_check_functionality(void *a,int flags){assert(flags==I2C_FUNC_SMBUS_READ_WORD_DATA);return capable;}
static bool device_property_present(struct device *d,const char *name){assert(!strcmp(name,"monitored-battery"));return monitored_form!=0;}
static void *devm_kzalloc(struct device *d,size_t size,int flags){if(alloc_fail)return NULL;void *p=calloc(1,size);assert(p);resources[nr++]=(struct resource){p,1};return p;}
static struct power_supply *power_supply_get_by_name(const char *name){
 if(!strcmp(name,"usb")){usb_lookups++;if(!usb_exists)return NULL;usb_refs++;return &usb_psy;}
 assert(!strcmp(name,"battery"));if(!existing_psy)return NULL;refs++;return &prior_psy;
}
static void power_supply_put(struct power_supply *p){
 if(p==&usb_psy){assert(usb_refs==1);usb_refs--;usb_puts++;return;}
 assert(p==&prior_psy&&refs==1);refs--;
}
static int power_supply_get_property(struct power_supply *p,enum power_supply_property prop,union power_supply_propval *v){
 assert(p==&usb_psy&&usb_refs==1&&p->dev.lock_held&&!p->removing&&usb_context_alive);assert_no_gauge_lock();
 if(property_hook)property_hook(prop);
 if(prop==POWER_SUPPLY_PROP_MODEL_NAME){usb_model_calls++;if(usb_model_error)return usb_model_error;v->strval=usb_model;return 0;}
 assert(prop==POWER_SUPPLY_PROP_STATUS);usb_status_calls++;if(usb_status_error)return usb_status_error;v->intval=usb_status;return 0;
}
static void power_supply_changed(struct power_supply *p){assert(p==active_psy&&p->dev.lock_held&&!p->removing);changed_calls++;if(changed_hook)changed_hook();}
static void *power_supply_get_drvdata(struct power_supply *p){return p->drv_data;}
static struct power_supply *devm_power_supply_register(struct device *d,const struct power_supply_desc *desc,const struct power_supply_config *cfg){
 assert(!cfg->of_node);assert(!active_psy);if(register_error)return ERR_PTR(register_error);
 struct power_supply *p=calloc(1,sizeof(*p));assert(p);assert(!pthread_mutex_init(&p->dev.lock,NULL));p->drv_data=cfg->drv_data;p->desc=desc;p->groups=cfg->attr_grp;
 /* Driver context must already be valid for registration-time callbacks. */
 union power_supply_propval v={.intval=-999};int ret=desc->get_property(p,POWER_SUPPLY_PROP_TEMP,&v);if(ret){free(p);return ERR_PTR(ret);}
 resources[nr++]=(struct resource){p,2};active_psy=p;registrations++;return p;
}
static void release_all(void){while(nr){struct resource r=resources[--nr];release_order[release_count++]=r.type;if(r.type==2){assert(active_psy==r.ptr&&nr==1&&resources[0].type==1);assert(!active_psy->dev.lock_held);assert(!pthread_mutex_destroy(&active_psy->dev.lock));active_psy=NULL;unregistrations++;free(r.ptr);}else free(r.ptr);}}
/* A bounded model of the driver core's existing-owner exclusion. The report
 * separately cites actual kernel code; this fixture is not the kernel itself.
 */
static int i2c_add_driver(struct i2c_driver *d){
 driver_adds++;if(driver_error)return driver_error;registered_driver=d;
 if(auto_attach&&!owner){probe_attempts++;int ret=d->probe(&client);if(!ret)owner=2;else release_all();}
 return 0;
}
static void i2c_del_driver(struct i2c_driver *d){assert(registered_driver==d);driver_dels++;if(owner==2){if(d->remove)d->remove(&client);release_all();owner=0;}registered_driver=NULL;}
#endif
