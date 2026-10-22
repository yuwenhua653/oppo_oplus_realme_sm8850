#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef int32_t s32;
#define BIT(n) (1U << (n))
#define PAGE_SIZE 4096
#define I2C_SMBUS_BLOCK_MAX 32
#define MCA_EVENT_TYPE_CP_INFO 1
#define MCA_EVENT_CP_VUSB_INSERT 2
#define MCA_EVENT_CP_VUSB_OUT 3
#define RANGE_MIN_MAX 2
struct work_struct { int dummy; };
struct delayed_work { struct work_struct work; };
struct device { int dummy; };
struct i2c_client { struct device dev; int addr; };
struct power_supply_desc { int dummy; };
struct notifier_block;
#define container_of(ptr,type,member) ((type *)((char *)(ptr)-offsetof(type,member)))
#define DEFINE_MUTEX(name) pthread_mutex_t name=PTHREAD_MUTEX_INITIALIZER
static pthread_mutex_t phase_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t phase_cond=PTHREAD_COND_INITIALIZER;
static _Thread_local int actor;
static int pause_read,first_read_paused,release_read,second_lock_attempt,second_finished;
static inline void fixture_mutex_lock(pthread_mutex_t *m) {if(actor==2){pthread_mutex_lock(&phase_lock);second_lock_attempt=1;pthread_cond_broadcast(&phase_cond);pthread_mutex_unlock(&phase_lock);}assert(!pthread_mutex_lock(m));}
#define mutex_lock(m) fixture_mutex_lock(m)
#define mutex_unlock(m) ((void)pthread_mutex_unlock(m))
static void log_stub(const char *fmt,...) {(void)fmt;}
#define mca_log_info(...) log_stub(__VA_ARGS__)
#define mca_log_err(...) log_stub(__VA_ARGS__)
#define mca_log_debug(...) log_stub(__VA_ARGS__)
static u8 regs[256];
static int bus_at,fail_at,fail_persistent,read_error,write_error,block_return,gate_readback_override;
static int reads,writes,block_reads,events,judges,gate_writes;
static int bus_failure(void) {bus_at++;return fail_at>0&&(bus_at==fail_at||(fail_persistent&&bus_at>=fail_at));}
static int i2c_smbus_read_byte_data(struct i2c_client *c,u8 reg) {(void)c;reads++;int value=read_error?read_error:(bus_failure()?-EREMOTEIO:(reg==0x0b&&gate_readback_override>=0?gate_readback_override:regs[reg]));if(actor==1&&pause_read){pthread_mutex_lock(&phase_lock);first_read_paused=1;pthread_cond_broadcast(&phase_cond);while(!release_read)pthread_cond_wait(&phase_cond,&phase_lock);pthread_mutex_unlock(&phase_lock);}return value;}
static int i2c_smbus_write_byte_data(struct i2c_client *c,u8 reg,u8 val) {(void)c;writes++;if(write_error)return write_error;if(bus_failure())return -EREMOTEIO;regs[reg]=val;return 0;}
static int i2c_smbus_read_i2c_block_data(struct i2c_client *c,u8 reg,unsigned short len,u8 *out) {(void)c;block_reads++;int ret=block_return>=0?block_return:len;if(block_return < -1)ret=block_return;if(ret>0)memcpy(out,regs+reg,(unsigned)ret<len?(unsigned)ret:len);else if(len)out[0]=0xcc;return ret;}
static void msleep(int ms) {(void)ms;}
static int mca_event_block_notify(int type,int event,void *data) {(void)type;(void)event;(void)data;events++;return 0;}

