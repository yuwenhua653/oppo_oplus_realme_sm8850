#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
struct mutex { int held; };
typedef int atomic_t;
static void mutex_lock(struct mutex *m) { assert(!m->held); m->held=1; }
static void mutex_unlock(struct mutex *m) { assert(m->held); m->held=0; }
static int atomic_read(const atomic_t *a) { return *a; }
struct i2c_adapter { int unused; };
struct i2c_client { int addr; struct i2c_adapter *adapter; };
struct i2c_msg { int addr,flags,len; u8 *buf; };
struct bq_fg_chip { struct i2c_client *client; u8 regs[2]; struct mutex data_lock,i2c_rw_lock; atomic_t pm_suspend; int fg_vendor,batt_temp; };
#define BQ_FG_REG_ALT_MAC 0
#define BQ_FG_REG_MAC_CHKSUM 1
#define I2C_M_RD 1
#define FG_I2C_RETRY_CNT 5
#define GFP_KERNEL 0
#define BLOCK_LENGTH_MAX 64
#define BATTERY_RANDOM_LEN 64
#define REG_BLOCK_LENGTH 32
#define BQ27Z561_DEFUALT_TERM -200
#define BQ27Z561_DEFUALT_FFC_TERM -680
#define BQ27Z561_DEFUALT_RECHARGE_VOL 4380
static unsigned groups,cases;
static void fake_log(const char *s,...) { (void)s; }
#define mca_log_err fake_log
#define mca_log_info fake_log
#define mca_log_debug fake_log
#define scnprintf snprintf
static int alloc_fail,live_allocations;
static void *kzalloc(size_t n,int flags) { (void)flags;if(alloc_fail)return NULL;void *p=calloc(1,n);if(p)live_allocations++;return p; }
static void kfree(void *p) { if(p){assert(live_allocations>0);live_allocations--;free(p);} }
static int sleep4,sleep100;
static void usleep_range(int a,int b) { assert(a==4000&&b==4100);sleep4++; }
static void msleep(int n) { assert(n==100);sleep100++; }
static u8 response[36];
static int read_result=2,write_result=1,write_fail_after=-1,write_after_result;
static int read_first_result=2;
static int calls,reads,writes;
struct captured_write { int len;u8 bytes[256]; };
static struct captured_write captured[32];
static int i2c_transfer(struct i2c_adapter *a,struct i2c_msg *m,int n)
{
 assert(a);calls++;
 if(n==2){
  assert(m[0].addr==0x55&&m[1].addr==0x55&&m[0].flags==0&&m[1].flags==I2C_M_RD&&m[0].len==1);
  assert(m[1].len>0&&m[1].len<=255);
  memset(m[1].buf,0xd7,(size_t)m[1].len);
  memcpy(m[1].buf,response,(size_t)(m[1].len<36?m[1].len:36));
  int ret=(reads==0&&read_first_result!=2)?read_first_result:read_result;
  reads++;return ret;
 }
 assert(n==1&&m[0].addr==0x55&&m[0].flags==0&&m[0].len>=1&&m[0].len<=256&&writes<32);
 captured[writes].len=m[0].len;memcpy(captured[writes].bytes,m[0].buf,(size_t)m[0].len);
 int ret=write_fail_after>=0&&writes>=write_fail_after?write_after_result:write_result;
 writes++;return ret;
}
static int fg_read_volt(struct bq_fg_chip *bq,int *v) { (void)bq;*v=4300;return 0; }
