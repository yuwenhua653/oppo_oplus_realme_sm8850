/* Host-only abstractions for the extracted production budget functions. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

typedef uint32_t u32;
struct device_node { const char *compatible; };
struct device { struct device_node *of_node; struct device *parent; };
struct power_supply { struct device dev; };
union power_supply_propval { int intval; };
enum qcom_flash_iio_props { RBATT, OCV };
enum hw_type { QCOM_MVFLASH_3CH, QCOM_MVFLASH_4CH, QCOM_MVFLASH_1CH };
struct qcom_flash_data {
    struct device *dev;
    struct power_supply *batt_psy;
    bool use_smb_battery_interface, debug_board_present;
    enum hw_type hw_type;
    u32 total_ma;
    int lock;
};
struct flash_current_headroom { unsigned short current_ma, headroom_mv; };
static const struct flash_current_headroom mvflash_4ch_map[] = {
    {750, 200}, {1000, 250}, {1250, 300}, {1500, 400}
};
#define BATTERY_RESISTANCE 0
#define POWER_SUPPLY_PROP_VOLTAGE_OCV 14
#define POWER_SUPPLY_PROP_CURRENT_NOW 17
#define ARRAY_SIZE(x) ((int)(sizeof(x) / sizeof((x)[0])))
#define spin_lock(x) ((void)(x))
#define spin_unlock(x) ((void)(x))
#define min(x,y) ({ __typeof__(x) _a=(x); __typeof__(y) _b=(y); _a < _b ? _a : _b; })
#define max(x,y) ({ __typeof__(x) _a=(x); __typeof__(y) _b=(y); _a > _b ? _a : _b; })
#define clamp_t(type,v,lo,hi) ({ type _v=(v),_lo=(lo),_hi=(hi); _v < _lo ? _lo : _v > _hi ? _hi : _v; })
/* Same signed rounding rule as Linux DIV_ROUND_CLOSEST. */
#define DIV_ROUND_CLOSEST(x, divisor) ({ \
    __typeof__(x) __x = (x); \
    __typeof__(divisor) __d = (divisor); \
    (((__typeof__(x))-1) > 0 || ((__typeof__(divisor))-1) > 0 || \
     (__x > 0) == (__d > 0)) ? \
        ((__x + (__d / 2)) / __d) : ((__x - (__d / 2)) / __d); \
})
#define pr_err(...) ((void)0)
#define pr_debug(...) ((void)0)
#define dev_err(...) ((void)0)
#define dev_info_once(...) (++mock.model_logs)

static struct {
    struct power_supply *registered;
    int resistance, voltage, current;
    int qti_rc, rbatt_rc, ocv_rc, current_rc;
    unsigned lookup_calls, qti_calls, rbatt_calls, ocv_calls, current_calls, model_logs;
} mock;

static bool of_device_is_compatible(const struct device_node *node, const char *name)
{
    return node && node->compatible && !strcmp(node->compatible, name);
}
static struct power_supply *power_supply_get_by_name(const char *name)
{
    assert(!strcmp(name, "battery"));
    mock.lookup_calls++;
    return mock.registered;
}
static int qti_battery_charger_get_prop(const char *name, int prop, int *val)
{
    assert(!strcmp(name, "battery") && prop == BATTERY_RESISTANCE);
    mock.qti_calls++;
    if (mock.qti_rc) return mock.qti_rc;
    *val = mock.resistance;
    return 0;
}
static int qcom_flash_iio_getprop(struct qcom_flash_data *flash_data,
                                enum qcom_flash_iio_props chan, int *val)
{
    (void)flash_data;
    if (chan == RBATT) {
        mock.rbatt_calls++;
        if (mock.rbatt_rc) return mock.rbatt_rc;
        *val = mock.resistance;
    } else {
        assert(chan == OCV);
        mock.ocv_calls++;
        if (mock.ocv_rc) return mock.ocv_rc;
        *val = mock.voltage;
    }
    return 0;
}
static int power_supply_get_property(struct power_supply *psy, int prop,
                                    union power_supply_propval *value)
{
    assert(psy != NULL);
    if (prop == POWER_SUPPLY_PROP_VOLTAGE_OCV) {
        mock.ocv_calls++;
        if (mock.ocv_rc) return mock.ocv_rc;
        value->intval = mock.voltage;
    } else {
        assert(prop == POWER_SUPPLY_PROP_CURRENT_NOW);
        mock.current_calls++;
        if (mock.current_rc) return mock.current_rc;
        value->intval = mock.current;
    }
    return 0;
}
