#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sched.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef atomic_int atomic_t;
struct mutex { pthread_mutex_t impl; int kind; };
struct i2c_adapter { int unused; };
struct i2c_client { unsigned short addr; struct i2c_adapter *adapter; };
struct i2c_msg { unsigned short addr, flags, len; u8 *buf; };
struct bq_fg_chip { struct i2c_client *client; u8 regs[8]; struct mutex data_lock,i2c_rw_lock; atomic_t pm_suspend,digest_in_process; bool fast_mode; int fg_vendor; u8 digest[32]; };
#define atomic_read(x) atomic_load(x)
#define atomic_set(x,y) atomic_store((x),(y))
#define I2C_M_RD 1
#define GFP_KERNEL 0
#define FG_I2C_RETRY_CNT 3
#define BQ_FG_REG_ALT_MAC 0
#define BQ_FG_REG_MAC_CHKSUM 1
#define BQ_FG_REG_MAC_DATA 2
#define FG_MAC_CMD_UI_SOH 0x77
#define FG_MAC_CMD_CLEAR_COUNT_DATA 0x78
#define FG_MAC_CMD_FASTCHARGE_EN 0x3e
#define FG_MAC_CMD_FASTCHARGE_DIS 0x3f
#define MPC7021 5
#define BATTERY_DIGEST_LEN 32
#define BATTERY_RANDOM_LEN 64
#define mca_log_err(...) ((void)0)
#define mca_log_info(...) ((void)0)
#define scnprintf snprintf
#define kzalloc(n,f) calloc(1,(n))
#define kfree free
static pthread_mutex_t phase_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t phase_cond=PTHREAD_COND_INITIALIZER;
static _Thread_local int actor;
static int auth_pause,auth_paused,auth_release,waiters;
static u8 reply[36],digest_reply[32];
static int returns[16],return_n,return_at,wire_n;
static struct { int actor,read,reg; u8 payload[40]; int length; } wires[128];
static void mutex_lock(struct mutex *m) {
 if(actor>=2){pthread_mutex_lock(&phase_mutex);waiters++;pthread_cond_broadcast(&phase_cond);pthread_mutex_unlock(&phase_mutex);}
 assert(!pthread_mutex_lock(&m->impl));
}
static void mutex_unlock(struct mutex *m){assert(!pthread_mutex_unlock(&m->impl));}
static void usleep_range(int a,int b){(void)a;(void)b;}
static void msleep(int n){
 if(n==400&&actor==1&&auth_pause){pthread_mutex_lock(&phase_mutex);auth_paused=1;pthread_cond_broadcast(&phase_cond);while(!auth_release)pthread_cond_wait(&phase_cond,&phase_mutex);pthread_mutex_unlock(&phase_mutex);}
}
static int i2c_transfer(struct i2c_adapter *a,struct i2c_msg *m,int n){
 (void)a;assert(wire_n<128);int at=wire_n++;wires[at].actor=actor;wires[at].read=n==2;wires[at].reg=m[0].buf[0];
 if(n==1){wires[at].length=m[0].len-1;memcpy(wires[at].payload,m[0].buf+1,m[0].len-1);}
 int r=return_at<return_n?returns[return_at++]:n;
 if(n==2){assert(m[1].len<=36);if(r==2)memcpy(m[1].buf,m[0].buf[0]==0x40?digest_reply:reply,m[1].len);else if(m[1].len)m[1].buf[0]=0xcc;}
 return r;
}
static void reset(void){memset(wires,0,sizeof(wires));wire_n=return_n=return_at=0;actor=0;auth_pause=auth_paused=auth_release=waiters=0;}
static struct i2c_adapter adapter;
static struct i2c_client client={.addr=0x55,.adapter=&adapter};
static void init_chip(struct bq_fg_chip *bq){
 memset(bq,0,sizeof(*bq));bq->client=&client;bq->regs[0]=0x3e;bq->regs[1]=0x60;bq->regs[2]=0x40;
 assert(!pthread_mutex_init(&bq->data_lock.impl,NULL));assert(!pthread_mutex_init(&bq->i2c_rw_lock.impl,NULL));atomic_init(&bq->pm_suspend,0);atomic_init(&bq->digest_in_process,0);
}
static void finish_chip(struct bq_fg_chip *bq){assert(!pthread_mutex_destroy(&bq->data_lock.impl));assert(!pthread_mutex_destroy(&bq->i2c_rw_lock.impl));}
