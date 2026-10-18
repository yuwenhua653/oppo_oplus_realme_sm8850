/* Narrow userspace ABI shim: not a substitute for kernel API/lifetime review. */
#ifndef MT_FAKE_KERNEL_H
#define MT_FAKE_KERNEL_H
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

typedef uint32_t u32;
typedef uint64_t u64;
#define U32_MAX UINT32_MAX
#define U64_MAX UINT64_MAX
#define PAGE_SIZE 4096
#define GFP_KERNEL 0
#define __init
#define __exit
#define current get_current()
#define module_param(name, type, mode) \
 static const unsigned int test_parameter_mode = mode; \
 static const char test_parameter_name[] = #name; \
 static const char test_parameter_type[] = #type
#define MODULE_PARM_DESC(a, b)
#define MODULE_DEVICE_TABLE(a, b)
#define MODULE_DESCRIPTION(a)
#define MODULE_LICENSE(a)
#define module_init(a)
#define module_exit(a)

/* Signature collision guard from common/include/linux/maple_tree.h.
 * This stub checks namespace compatibility, not maple-tree behavior. */
struct maple_tree;
static inline void mt_init(struct maple_tree *mt) { (void)mt; }

struct mutex { pthread_mutex_t value; };
static void mutex_init(struct mutex *lock) { assert(!pthread_mutex_init(&lock->value, NULL)); }
static void mutex_lock(struct mutex *lock) { assert(!pthread_mutex_lock(&lock->value)); }
static void mutex_unlock(struct mutex *lock) { assert(!pthread_mutex_unlock(&lock->value)); }
static atomic_uint_fast64_t test_clock;
static u64 ktime_get_boottime_ns(void) { return atomic_fetch_add(&test_clock, 1) + 1; }

struct attribute { const char *name; unsigned int mode; };
struct device;
struct device_attribute {
 struct attribute attr;
 ssize_t (*show)(struct device *, struct device_attribute *, char *);
 ssize_t (*store)(struct device *, struct device_attribute *, const char *, size_t);
};
#define DEVICE_ATTR(name, mode, show, store) \
 struct device_attribute dev_attr_##name = {{#name, mode}, show, store}
#define DEVICE_ATTR_RO(name) DEVICE_ATTR(name, 0444, name##_show, NULL)
struct attribute_group { const char *name; struct attribute **attrs; };
struct device_node { bool available, compatible; int count, read_error; u32 cells[150]; };
struct kobject { struct device *owner; };
struct device { void *data; struct device_node *of_node; struct kobject kobj; void *allocation; };
struct platform_device { struct device dev; };
struct of_device_id { char compatible[128]; };
struct platform_driver {
 int (*probe)(struct platform_device *);
 void (*remove)(struct platform_device *);
 struct { const char *name; const struct of_device_id *of_match_table; } driver;
};
static unsigned int test_allocations, test_adds, test_removes, test_registers, test_unregisters;
static bool test_alloc_fail;
static int test_add_error, test_register_error;
static void (*test_drain_callback)(struct device *);
static const struct attribute_group *test_published_group;

static void *dev_get_drvdata(struct device *dev) { return dev->data; }
static void platform_set_drvdata(struct platform_device *pdev, void *data) { pdev->dev.data = data; }
static void *devm_kzalloc(struct device *dev, size_t size, int flags) {
 (void)flags; test_allocations++;
 if (test_alloc_fail) return NULL;
 assert(!dev->allocation); dev->allocation = calloc(1, size); return dev->allocation;
}
static bool of_device_is_available(const struct device_node *node) { return node->available; }
static bool of_device_is_compatible(const struct device_node *node, const char *name) {
 assert(!strcmp(name, "mca_charger_thermal")); return node->compatible;
}
static int of_property_count_u32_elems(const struct device_node *node, const char *name) {
 assert(!strcmp(name, "wired_thermal")); return node->count;
}
static int of_property_read_u32_array(const struct device_node *node, const char *name, u32 *cells, size_t n) {
 assert(!strcmp(name, "wired_thermal")); assert(n == 150);
 if (node->read_error) return node->read_error;
 memcpy(cells, node->cells, sizeof(node->cells)); return 0;
}
static int sysfs_create_group(struct kobject *kobj, const struct attribute_group *group) {
 assert(kobj->owner->data); test_adds++;
 if (test_add_error) return test_add_error;
 test_published_group = group; return 0;
}
static void sysfs_remove_group(struct kobject *kobj, const struct attribute_group *group) {
 assert(group == test_published_group); assert(kobj->owner->data); test_removes++;
 /* Only tests ordering: real kernfs deactivation/draining is independently reviewed. */
 if (test_drain_callback) test_drain_callback(kobj->owner);
 test_published_group = NULL;
}
static int platform_driver_register(struct platform_driver *driver) {
 assert(!strcmp(driver->driver.name, "myron_buck_thermal")); test_registers++; return test_register_error;
}
static void platform_driver_unregister(struct platform_driver *driver) {
 assert(!strcmp(driver->driver.name, "myron_buck_thermal")); test_unregisters++;
}
static int sysfs_emit(char *buf, const char *fmt, ...) {
 va_list args; va_start(args, fmt); int n = vsnprintf(buf, PAGE_SIZE, fmt, args); va_end(args);
 assert(n >= 0 && n < PAGE_SIZE); return n;
}
static int sysfs_emit_at(char *buf, int at, const char *fmt, ...) {
 assert(at >= 0 && at < PAGE_SIZE); va_list args; va_start(args, fmt);
 int n = vsnprintf(buf + at, PAGE_SIZE - (size_t)at, fmt, args); va_end(args);
 assert(n >= 0 && (size_t)n < PAGE_SIZE - (size_t)at); return n;
}
#endif
