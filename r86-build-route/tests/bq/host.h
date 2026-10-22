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
#include <sys/types.h>
typedef uint8_t u8;
typedef uint16_t u16;
#define READ_FASTCHARGE_REG 0
#define MPC7021 5
#define MPC7012 4
#define FG_MAC_CMD_FASTCHARGE_EN 0x003e
#define FG_MAC_CMD_FASTCHARGE_DIS 0x003f
#define FG_IC_PROP_FAST_CHARGE 1
#define PAGE_SIZE 4096
#define scnprintf snprintf
#define mca_log_info(...) ((void)0)
static atomic_uint assertions;
#define CHECK(x) do { atomic_fetch_add(&assertions,1); if (!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x); abort(); } } while (0)
struct mutex { pthread_mutex_t impl; };
struct bq_fg_chip { struct mutex data_lock; bool fast_mode,fast_mode_valid; int fg_vendor; };
static _Thread_local bool owns_data, getter_actor;
static pthread_mutex_t state=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cond=PTHREAD_COND_INITIALIZER;
static bool pause_write,write_entered,release_write,getter_waiting;
static atomic_bool getter_done;
static int mode_result,mode_calls,last_len;
static u16 last_cmd;
static u8 last_data[2];
static void mutex_lock(struct mutex *m) {
 CHECK(!owns_data);
 if (getter_actor) { CHECK(!pthread_mutex_lock(&state)); getter_waiting=true; CHECK(!pthread_cond_broadcast(&cond)); CHECK(!pthread_mutex_unlock(&state)); }
 CHECK(!pthread_mutex_lock(&m->impl)); owns_data=true;
}
static void mutex_unlock(struct mutex *m) { CHECK(owns_data); owns_data=false; CHECK(!pthread_mutex_unlock(&m->impl)); }
/* Existing validated MAC core boundary: return0 is completed success. */
static int fg_mac_write_block_locked(struct bq_fg_chip *b,u16 cmd,u8 *data,u8 len) {
 CHECK(b && owns_data); mode_calls++; last_cmd=cmd; last_len=len; memcpy(last_data,data,2);
 CHECK(!pthread_mutex_lock(&state));
 if (pause_write) { write_entered=true; CHECK(!pthread_cond_broadcast(&cond)); while (!release_write) CHECK(!pthread_cond_wait(&cond,&state)); }
 CHECK(!pthread_mutex_unlock(&state)); return mode_result;
}
static void init_chip(struct bq_fg_chip *b) { memset(b,0,sizeof(*b)); b->fg_vendor=MPC7012; CHECK(!pthread_mutex_init(&b->data_lock.impl,NULL)); }
static void finish_chip(struct bq_fg_chip *b) { CHECK(!owns_data); CHECK(!pthread_mutex_destroy(&b->data_lock.impl)); }
static void reset_wire(void) { mode_result=mode_calls=last_len=0;last_cmd=0;memset(last_data,0xa5,2);pause_write=write_entered=release_write=getter_waiting=false;getter_actor=false;atomic_store(&getter_done,false); }
