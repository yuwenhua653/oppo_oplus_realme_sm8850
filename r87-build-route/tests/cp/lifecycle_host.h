#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>

#define GFP_KERNEL 0
#define SC8581_MASTER 0
#define SC8581_SLAVE 1
#define SC8581_EN_BUCK_CP_I2C_ADDR 0x6f
#define IRQF_TRIGGER_FALLING 1
#define IRQF_ONESHOT 2
#define MCA_EVENT_TYPE_CP_INFO 1
#define MCA_EVENT_CP_IIC_ERROR 2
#define MCA_CHARGE_LOG_ID_CP_MASTER_IC 0
#define mca_log_err(...) ((void)0)
#define mca_log_info(...) ((void)0)
#define dev_name(dev) "lifecycle-fixture"
typedef int irqreturn_t;
struct work_struct { int unused; };
struct delayed_work { struct work_struct work; bool initialized; void (*fn)(struct work_struct *); };
struct device { int unused; };
struct i2c_client { struct device dev; unsigned addr; void *data; };
struct i2c_device_id { int unused; };
struct sc8581_device {
    struct i2c_client *client;
    struct device *dev;
    int cp_role, irq_gpio, nlpm_gpio, irq;
    bool chip_ok, ovpgate_en, i2c_is_working;
    char log_tag[25];
    struct delayed_work irq_handle_work;
};
static void sc8581_restore_nlpm(void *data);
static void sc8581_disable_irq_wake(void *data);
static void sc8581_cancel_irq_work(void *data);
static void sc8581_quiesce_device(void *data);
static void sc8581_disable_wakeup(void *data);

enum resource_kind { R_MEMORY, R_GPIO, R_IRQ, R_ACTION };
struct resource { enum resource_kind kind; void (*action)(void *); void *data; };
static struct resource resources[32];
static int resource_n, call_n, fail_call, trace_n, test_role;
static int published, log_published, scheduled, detect_calls, init_calls;
static bool nlpm_owned, irq_gpio_owned, irq_owned, irq_wake, device_wake;
static bool work_queued, allocation_freed;
static int nlpm_level;
static const char *fail_name;
static const char *calls[64], *trace[256];
static struct sc8581_device *allocated_chip;
static int sc8581_chg_ops, g_sc8581_log_ops;
static void record(const char *name) { assert(trace_n < 256); trace[trace_n++] = name; }
static int step(const char *name) {
    assert(call_n < 64); calls[call_n++] = name; record(name);
    return (fail_call == call_n || (fail_name && !strcmp(fail_name, name))) ? -EIO : 0;
}
static void resource(enum resource_kind kind, void (*action)(void *), void *data) {
    assert(resource_n < 32); resources[resource_n++] = (struct resource){kind, action, data};
}
static void release_resources(void) {
    while (resource_n) {
        struct resource r = resources[--resource_n];
        switch (r.kind) {
        case R_ACTION: r.action(r.data); break;
        case R_IRQ: record("free_irq"); irq_owned = false; break;
        case R_GPIO:
            if ((intptr_t)r.data == 114) { record("free_nlpm_gpio"); nlpm_owned = false; }
            else { record("free_irq_gpio"); irq_gpio_owned = false; }
            break;
        case R_MEMORY:
            record("free_memory"); allocation_freed = true; free(r.data); allocated_chip = NULL; break;
        }
    }
}
static void reset_fixture(void) {
    assert(!resource_n && !allocated_chip);
    call_n = fail_call = trace_n = test_role = 0;
    published = log_published = scheduled = detect_calls = init_calls = 0;
    nlpm_owned = irq_gpio_owned = irq_owned = irq_wake = device_wake = false;
    work_queued = allocation_freed = false; nlpm_level = 0; fail_name = NULL;
    memset(calls, 0, sizeof(calls)); memset(trace, 0, sizeof(trace));
}
static void *devm_kzalloc(struct device *dev, size_t size, int flags) {
    (void)dev; (void)flags;
    if (step("allocate")) return NULL;
    void *p = calloc(1, size); assert(p); allocated_chip = p;
    resource(R_MEMORY, NULL, p); return p;
}
static void i2c_set_clientdata(struct i2c_client *client, void *data) { client->data = data; }
static bool mca_cp_is_en_buck_project_hwid(void) { return false; }
static int sc8581_parse_dt(struct sc8581_device *bq) {
    int ret = step("parse_dt"); if (ret) return ret;
    bq->cp_role = test_role; bq->nlpm_gpio = 114; bq->irq_gpio = 68; return 0;
}
static int cp_charge_detect_device(struct sc8581_device *bq) {
    (void)bq; detect_calls++; return step("detect_device");
}
static int sc8581_init_device(struct sc8581_device *bq) {
    (void)bq; init_calls++; return step("init_device");
}
static int devm_gpio_request(struct device *dev, int gpio, const char *name) {
    (void)dev; (void)name; int ret = step(gpio == 114 ? "nlpm_request" : "irq_gpio_request");
    if (ret) return ret;
    if (gpio == 114) { assert(!nlpm_owned); nlpm_owned = true; }
    else { assert(gpio == 68 && !irq_gpio_owned); irq_gpio_owned = true; }
    resource(R_GPIO, NULL, (void *)(intptr_t)gpio); return 0;
}
static int gpio_direction_output(int gpio, int value) {
    assert(gpio == 114 && nlpm_owned && !allocation_freed);
    if (value) { int ret = step("nlpm_high"); if (ret) return ret; }
    else record("restore_nlpm");
    nlpm_level = value; return 0;
}
#define gpio_direction_input(gpio) ((void)(gpio), step("irq_input"))
static int gpio_to_irq(int gpio) { assert(gpio == 68); int ret = step("irq_map"); return ret ? ret : 200; }
static int host_request_irq(struct device *dev, int irq, irqreturn_t (*handler)(int, void *), unsigned flags, const char *name, void *data) {
    (void)handler; (void)flags; (void)name; (void)data;
    int ret = step("request_irq"); if (ret) return ret;
    if (irq < 0) return irq;
    assert(!irq_owned); irq_owned = true;
    if (dev) resource(R_IRQ, NULL, NULL);
    return 0;
}
#define devm_request_irq(dev,irq,handler,flags,name,data) host_request_irq(dev,irq,handler,flags,name,data)
#define request_irq(irq,handler,flags,name,data) host_request_irq(NULL,irq,handler,flags,name,data)
static int enable_irq_wake(int irq) {
    assert(irq == 200 && irq_owned); int ret = step("enable_irq_wake"); if (!ret) irq_wake = true; return ret;
}
static inline void disable_irq_wake(int irq) { assert(irq == 200); record("disable_irq_wake"); irq_wake = false; }
int devm_add_action_or_reset(struct device *dev, void (*action)(void *), void *data) {
    (void)dev; const char *name;
    if (action == sc8581_restore_nlpm) name = "action_restore_nlpm";
    else if (action == sc8581_disable_irq_wake) name = "action_disable_irq_wake";
    else if (action == sc8581_cancel_irq_work) name = "action_cancel_work";
    else if (action == sc8581_quiesce_device) name = "action_quiesce";
    else { assert(action == sc8581_disable_wakeup); name = "action_disable_wakeup"; }
    int ret = step(name);
    if (ret) { action(data); return ret; }
    resource(R_ACTION, action, data); return 0;
}
static int device_init_wakeup(struct device *dev, bool enable) {
    (void)dev;
    if (enable) { int ret = step("wakeup_enable"); if (ret) return ret; record("device_wakeup_enabled"); }
    else record("disable_device_wakeup");
    device_wake = enable; return 0;
}
static void sc8581_irq_handler(struct work_struct *work) { (void)work; }
static irqreturn_t sc8581_int_isr(int irq, void *data) { (void)irq; (void)data; return 1; }
#define INIT_DELAYED_WORK(work,handler) do { (work)->initialized = true; (work)->fn = handler; record("initialize_work"); } while (0)
static inline void cancel_delayed_work_sync(struct delayed_work *work) {
    assert(work->initialized && !allocation_freed); record("cancel_work"); work_queued = false;
}
static bool schedule_delayed_work(struct delayed_work *work, int delay) {
    (void)delay; assert(work->initialized && !allocation_freed); scheduled++; work_queued = true; record("schedule_work"); return true;
}
static inline int sc8581_enable_charge(struct sc8581_device *bq, bool enable) {
    assert(!allocation_freed && bq); assert(!enable); record("quiesce_charge"); return 0;
}
static inline int sc8581_enable_adc(struct sc8581_device *bq, bool enable) {
    assert(!allocation_freed && bq); assert(!enable); record("quiesce_adc"); return 0;
}
static int platform_class_cp_register_ops_v2(unsigned role, void *ops, void *data, unsigned size) {
    (void)role; (void)ops; (void)data; (void)size;
    int ret = step("provider_register"); if (!ret) published++; return ret;
}
static void mca_log_charge_log_register(int id, void *ops, void *data) {
    (void)id; (void)ops; (void)data; log_published++; record("publish_log");
}
static void msleep(int ms) { assert(ms == 400); record("nlpm_settle"); }
#define mca_event_block_notify(type,event,data) ((void)(type), (void)(event), (void)(data))
