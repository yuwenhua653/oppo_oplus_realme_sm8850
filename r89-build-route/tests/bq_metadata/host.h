#define _XOPEN_SOURCE 700
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef int atomic_t;
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x), (v), __ATOMIC_RELAXED)
struct mutex { pthread_mutex_t lock; int rank; };
static _Thread_local int lock_rank;
static void mutex_lock(struct mutex *m)
{
    assert((m->rank == 1 && lock_rank == 0) || (m->rank == 2 && lock_rank == 1));
    assert(pthread_mutex_lock(&m->lock) == 0); lock_rank = m->rank;
}
static void mutex_unlock(struct mutex *m)
{
    assert(lock_rank == m->rank); lock_rank--; assert(pthread_mutex_unlock(&m->lock) == 0);
}
static int atomic_read(const atomic_t *a) { return READ_ONCE(*a); }
struct i2c_client { int unused; };
struct bq_fg_chip {
    struct i2c_client *client;
    struct mutex data_lock, i2c_rw_lock;
    atomic_t pm_suspend;
    u8 regs[1];
    const char *cell_name;
};
#define BQ_FG_REG_ALT_MAC 0
static void fake_log(const char *format, ...) { (void)format; }
#define mca_log_info fake_log
static void usleep_range(int a,int b) { assert(a == 4000 && b == 4100); }
static unsigned cases, reads, writes;
static int read_result = 2, write_result = 1;
static u8 response[36];
static int __fg_write_block(struct i2c_client *client,u8 reg,u8 *buf,u8 length)
{
    assert(client && reg == 0x3e && length == 2 && buf[0] == 0x4b && buf[1] == 0);
    assert(lock_rank == 2); writes++; return write_result;
}
static int __fg_read_block(struct i2c_client *client,u8 reg,u8 *buf,u8 length)
{
    assert(client && reg == 0x3e && length == sizeof(response));
    assert(lock_rank == 2); reads++; memcpy(buf,response,sizeof(response)); return read_result;
}
