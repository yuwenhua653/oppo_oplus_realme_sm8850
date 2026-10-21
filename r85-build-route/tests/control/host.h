#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef _Atomic int atomic_t;
#define atomic_read(p) atomic_load(p)
#define atomic_set(p,v) atomic_store((p),(v))
#define mca_log_info(...) ((void)0)
#define mca_log_err(...) ((void)0)
#define CHECK(v) do { if (!(v)) { fprintf(stderr,"CHECK FAILED line %d: %s\n",__LINE__,#v);abort(); } } while (0)
#define BATTERY_DIGEST_LEN 32
#define BATTERY_RANDOM_LEN 64
#define MPC7021 5
#define MPC7012 4
#define FG_MAC_CMD_FASTCHARGE_EN 0x003e
#define FG_MAC_CMD_FASTCHARGE_DIS 0x003f
#define BQ_FG_REG_ALT_MAC 0
#define BQ_FG_REG_MAC_DATA 1
struct mutex { pthread_mutex_t raw; unsigned bit; };
struct bq_fg_chip;
struct i2c_client { void *adapter; struct bq_fg_chip *owner; };
struct bq_fg_chip {
 struct mutex data_lock,i2c_rw_lock;
 struct i2c_client *client;
 atomic_t digest_in_process,pm_suspend;
 bool fast_mode;
 int fg_vendor;
 u8 regs[2],digest[32];
};
static _Thread_local unsigned held,actor;
static pthread_mutex_t state_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t state_cond=PTHREAD_COND_INITIALIZER;
static bool pause_armed,pause_entered,pause_release;
static unsigned attempted,finished;
static int write_result=1,read_result=2,mode_result;
static bool require_locked_sleep=true;
static unsigned write_calls,read_calls,mode_calls,sleep_calls,wire_count;
static unsigned wire_actor[32],wire_kind[32];
static u16 last_mode_cmd;
static u8 last_mode_len,last_mode_data[2],last_challenge[36],digest_seed;
static unsigned groups;
static void lock_state(void) { CHECK(pthread_mutex_lock(&state_lock)==0); }
static void unlock_state(void) { CHECK(pthread_mutex_unlock(&state_lock)==0); }
static void mutex_lock(struct mutex *m) {
 CHECK(!(held&m->bit));
 CHECK(m->bit!=1 || !(held&2));
 lock_state();
 if(pause_entered && actor>=11) { attempted|=1u<<actor;CHECK(pthread_cond_broadcast(&state_cond)==0); }
 unlock_state();
 CHECK(pthread_mutex_lock(&m->raw)==0);held|=m->bit;
}
static void mutex_unlock(struct mutex *m) { CHECK(held&m->bit);held&=~m->bit;CHECK(pthread_mutex_unlock(&m->raw)==0); }
static void wire(unsigned kind) {
 CHECK(held&2);lock_state();CHECK(wire_count<32);wire_actor[wire_count]=actor;wire_kind[wire_count++]=kind;unlock_state();
}
static int __fg_write_block(struct i2c_client *c,u8 reg,u8 *data,u8 len) {
 CHECK(c && c->owner && data);CHECK(held&2);write_calls++;wire(len==36?1:3);
 if(len==36) { CHECK(reg==0x3e);memcpy(last_challenge,data,36);digest_seed=data[2]^0xa5; }
 return write_result;
}
static int __fg_read_block(struct i2c_client *c,u8 reg,u8 *data,u8 len) {
 CHECK(c && c->owner && data);CHECK(held&2);CHECK(reg==0x40);CHECK(len==32);read_calls++;wire(2);
 /* An unsuccessful adapter read is permitted to dirty the output buffer. */
 for(unsigned i=0;i<len;i++) data[i]=(u8)(digest_seed+i);
 return read_result;
}
static int fg_write_block(struct bq_fg_chip *b,u8 reg,u8 *data,u8 len) {
 int r;mutex_lock(&b->i2c_rw_lock);r=__fg_write_block(b->client,reg,data,len);mutex_unlock(&b->i2c_rw_lock);return r;
}
static int fg_read_block(struct bq_fg_chip *b,u8 reg,u8 *data,u8 len) {
 int r;mutex_lock(&b->i2c_rw_lock);r=__fg_read_block(b->client,reg,data,len);mutex_unlock(&b->i2c_rw_lock);return r;
}
/* Exact dependency boundary, not a replacement implementation of the MAC core. */
static int fg_mac_write_block_locked(struct bq_fg_chip *b,u16 cmd,u8 *data,u8 len) {
 CHECK(held&1);mutex_lock(&b->i2c_rw_lock);mode_calls++;wire(4);last_mode_cmd=cmd;last_mode_len=len;
 CHECK(len==0 || len==2);last_mode_data[0]=data[0];last_mode_data[1]=data[1];
 mutex_unlock(&b->i2c_rw_lock);return mode_result;
}
static int fg_mac_write_block(struct bq_fg_chip *b,u16 cmd,u8 *data,u8 len) {
 int r;mutex_lock(&b->data_lock);r=fg_mac_write_block_locked(b,cmd,data,len);mutex_unlock(&b->data_lock);return r;
}
static void msleep(unsigned ms) {
 CHECK(ms==400);if(require_locked_sleep) CHECK(held==3);sleep_calls++;
 lock_state();
 if(pause_armed) { pause_armed=false;pause_entered=true;CHECK(pthread_cond_broadcast(&state_cond)==0);while(!pause_release) CHECK(pthread_cond_wait(&state_cond,&state_lock)==0); }
 unlock_state();
}
static size_t strlcat(char *dst,const char *src,size_t cap) {
 size_t a=strnlen(dst,cap),b=strlen(src);if(a<cap) { size_t n=b<cap-a-1?b:cap-a-1;memcpy(dst+a,src,n);dst[a+n]=0; }return a+b;
}
static long strscpy(char *dst,const void *src,size_t cap) {
 size_t n=strnlen(src,cap);if(!cap)return -E2BIG;size_t m=n<cap?n:cap-1;memcpy(dst,src,m);dst[m]=0;return n<cap?(long)n:-E2BIG;
}
static void init_chip(struct bq_fg_chip *b,struct i2c_client *c) {
 memset(b,0,sizeof(*b));CHECK(pthread_mutex_init(&b->data_lock.raw,NULL)==0);b->data_lock.bit=1;
 CHECK(pthread_mutex_init(&b->i2c_rw_lock.raw,NULL)==0);b->i2c_rw_lock.bit=2;c->adapter=c;c->owner=b;b->client=c;
 atomic_init(&b->digest_in_process,0);atomic_init(&b->pm_suspend,0);b->fg_vendor=MPC7012;b->regs[0]=0x3e;b->regs[1]=0x40;memset(b->digest,0x5a,32);
}
static void destroy_chip(struct bq_fg_chip *b) { CHECK(!held);CHECK(pthread_mutex_destroy(&b->data_lock.raw)==0);CHECK(pthread_mutex_destroy(&b->i2c_rw_lock.raw)==0); }
static void reset_bus(void) {
 CHECK(!held);write_result=1;read_result=2;mode_result=0;require_locked_sleep=true;
 write_calls=read_calls=mode_calls=sleep_calls=wire_count=0;attempted=finished=0;pause_armed=pause_entered=pause_release=false;actor=1;memset(last_challenge,0,36);
}
static void group(void) { groups++; }
