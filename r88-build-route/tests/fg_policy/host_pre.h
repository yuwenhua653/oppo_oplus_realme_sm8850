#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#define EPROBE_DEFER 517
typedef int64_t ktime_t;
typedef int64_t time64_t;
struct device { int unused; };
struct platform_device { struct device dev; void *data; };
struct work_struct { int unused; };
struct delayed_work { struct work_struct work; };
struct notifier_block { int (*notifier_call)(struct notifier_block *, unsigned long, void *); };
struct power_supply { int unused; };
struct mca_votable { int unused; };
struct mca_battery_shutdown_para_info { int unused; };
/* Enum values from the compiled R87 platform_fg_ic_ops.h, SHA256
 * 4f747e4c91436578fc03eaa061deb7b617625189f570690c141118a47f3336b6. */
enum mca_fg_ic_role { FG_IC_MASTER = 0, FG_IC_SLAVE, FG_IC_MAX };
enum mca_fg_optional_op {
 MCA_FG_OP_AVERAGE_CURRENT, MCA_FG_OP_OTA_FLAG, MCA_FG_OP_OTA_UPDATE,
 MCA_FG_OP_QBG_CHG_DATA, MCA_FG_OP_FIRST_USAGE_DATE, MCA_FG_OP_MANUFACTURING_DATE,
 MCA_FG_OP_SET_FIRST_USAGE_DATE, MCA_FG_OP_ABNORMAL_COUNTS, MCA_FG_OP_PACK_VENDOR_CHECKED,
};
static int assertions;
static const char *scenario;
#define CHECK(x) do { assertions++; if (!(x)) { fprintf(stderr,"FAIL %s: %s\n", scenario, #x); exit(41); } } while (0)
static void host_log(const char *format, ...) { (void)format; }
#define mca_log_info host_log
#define mca_log_err host_log
#define dev_warn(d,...) ((void)(d), host_log(__VA_ARGS__))
#define dev_info(d,...) ((void)(d), host_log(__VA_ARGS__))
#define GFP_KERNEL 0
#define POWER_SUPPLY_STATUS_CHARGING 1
#define POWER_SUPPLY_HEALTH_GOOD 1
#define msecs_to_jiffies(x) (x)
#define clamp(v,lo,hi) ((v)<(lo)?(lo):((v)>(hi)?(hi):(v)))
#define clamp_t(t,v,lo,hi) ((t)clamp((v),(lo),(hi)))
#define min(a,b) ((a)<(b)?(a):(b))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
