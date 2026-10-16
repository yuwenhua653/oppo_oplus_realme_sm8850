// SPDX-License-Identifier: GPL-2.0
/*
 * Minimal opt-in battery telemetry. No charging, authentication, firmware,
 * manufacturer commands or persistent storage operations are implemented.
 */
#include <linux/device.h>
#include <linux/err.h>
#include <linux/errno.h>
#include <linux/i2c.h>
#include <linux/init.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/power_supply.h>
#include <linux/property.h>
#include <linux/slab.h>
#include <linux/sysfs.h>

/* Public TI SLUUBO7 standard commands (13.1.4, 13.1.5, 13.1.18).
 * The original three commands remain independent of optional extended reads.
 */
#define MYRON_REG_SOC		0x2c
#define MYRON_REG_VOLTAGE	0x08
#define MYRON_REG_TEMPERATURE	0x06
/* Public SLUUBO7 13.1.6/7 and SLUUC54C 12.1.6/7: read-only words. */
#define MYRON_REG_BATTERY_STATUS	0x0a
#define MYRON_REG_CURRENT	0x0c

static bool enable_readonly;
module_param(enable_readonly, bool, 0444);
MODULE_PARM_DESC(enable_readonly,
	"Explicitly enable read-only gauge telemetry; disabled by default");

/* Separate opt-in preserves the original three-command behavior by default.
 * No automatic mapping from raw flags to STATUS/HEALTH/ONLINE is made.
 */
static bool enable_extended_readonly;
module_param(enable_extended_readonly, bool, 0444);
MODULE_PARM_DESC(enable_extended_readonly,
	"Opt in to current and raw BatteryStatus reads; requires enable_readonly");

struct myron_readonly_gauge {
	struct i2c_client *client;
	struct mutex lock;
	bool extended_readonly;
};

struct myron_readonly_sample {
	int capacity;
	int voltage_uv;
	int temp_decic;
};

static int myron_readonly_sample(struct myron_readonly_gauge *gauge,
				struct myron_readonly_sample *sample)
{
	int capacity, mv, dk, twice_decic, temp, ret = 0;

	mutex_lock(&gauge->lock);
	capacity = i2c_smbus_read_word_data(gauge->client, MYRON_REG_SOC);
	if (capacity < 0) {
		ret = capacity;
		goto out;
	}
	mv = i2c_smbus_read_word_data(gauge->client, MYRON_REG_VOLTAGE);
	if (mv < 0) {
		ret = mv;
		goto out;
	}
	dk = i2c_smbus_read_word_data(gauge->client, MYRON_REG_TEMPERATURE);
	if (dk < 0) {
		ret = dk;
		goto out;
	}

	/* The public commands define unsigned 0..32767 voltage/temperature
	 * and 0..100 relative SOC. Reject invalid raw words before arithmetic.
	 */
	if (capacity > 100 || mv > 32767 || dk > 32767) {
		ret = -ERANGE;
		goto out;
	}
	/* 0.1 K -> 0.1 C using
	 * exactly 273.15 K, rounded to nearest with ties away from zero.
	 */
	twice_decic = 2 * dk - 5463;
	temp = twice_decic < 0 ? (twice_decic - 1) / 2 :
		(twice_decic + 1) / 2;
	/* Broad telemetry-validity limits, not charging safety thresholds.
	 * Reject the whole sample; never clamp or substitute a cached value.
	 */
	if (capacity > 100 || mv <= 0 || mv > 10000 ||
	    temp < -1280 || temp > 1280) {
		ret = -ERANGE;
		goto out;
	}
	sample->capacity = capacity;
	sample->voltage_uv = mv * 1000;
	sample->temp_decic = temp;
out:
	mutex_unlock(&gauge->lock);
	return ret;
}

/* Keep new reads separate: their failures cannot invalidate original SOC/V/T.
 * This helper has only two admitted command codes, never a userspace address.
 */
static int myron_readonly_extended_word(struct myron_readonly_gauge *gauge,
				       unsigned char command)
{
	int ret;

	if (!gauge->extended_readonly)
		return -EOPNOTSUPP;
	if (command != MYRON_REG_CURRENT && command != MYRON_REG_BATTERY_STATUS)
		return -EINVAL;
	mutex_lock(&gauge->lock);
	ret = i2c_smbus_read_word_data(gauge->client, command);
	mutex_unlock(&gauge->lock);
	/* Preserve negative errno before any signed-word conversion. */
	if (ret > 0xffff)
		return -ERANGE;
	return ret;
}

static ssize_t battery_status_raw_show(struct device *dev,
				      struct device_attribute *attr, char *buf)
{
	struct myron_readonly_gauge *gauge =
		power_supply_get_drvdata(to_power_supply(dev));
	int raw;

	(void)attr;
	raw = myron_readonly_extended_word(gauge, MYRON_REG_BATTERY_STATUS);
	if (raw < 0)
		return raw;
	/* Raw flags, including reserved bits, are evidence, not a health decision.
	 * In particular DSG can mean RELAX as well as DISCHARGE.
	 */
	return sysfs_emit(buf, "0x%04x\n", (unsigned int)raw);
}
static DEVICE_ATTR_RO(battery_status_raw);

static struct attribute *myron_readonly_diag_attrs[] = {
	&dev_attr_battery_status_raw.attr,
	NULL,
};
static const struct attribute_group myron_readonly_diag_group = {
	.name = "myron_readonly_diag",
	.attrs = myron_readonly_diag_attrs,
};
static const struct attribute_group *myron_readonly_diag_groups[] = {
	&myron_readonly_diag_group,
	NULL,
};

static int myron_readonly_get_property(struct power_supply *psy,
				      enum power_supply_property prop,
				      union power_supply_propval *value)
{
	struct myron_readonly_gauge *gauge = power_supply_get_drvdata(psy);
	struct myron_readonly_sample sample;
	int ret;

	switch (prop) {
	case POWER_SUPPLY_PROP_CURRENT_NOW:
		if (!gauge->extended_readonly)
			return -EINVAL;
		ret = myron_readonly_extended_word(gauge, MYRON_REG_CURRENT);
		if (ret < 0)
			return ret;
		/* Signed 16-bit mA -> uA, same positive-charge/negative-discharge
		 * convention as Linux. Full range fits the signed int result.
		 */
		value->intval = (s16)ret * 1000;
		return 0;
	case POWER_SUPPLY_PROP_STATUS:
		value->intval = POWER_SUPPLY_STATUS_UNKNOWN;
		return 0;
	case POWER_SUPPLY_PROP_HEALTH:
		value->intval = POWER_SUPPLY_HEALTH_UNKNOWN;
		return 0;
	case POWER_SUPPLY_PROP_CAPACITY:
	case POWER_SUPPLY_PROP_VOLTAGE_NOW:
	case POWER_SUPPLY_PROP_TEMP:
		break;
	default:
		return -EINVAL;
	}

	ret = myron_readonly_sample(gauge, &sample);
	if (ret)
		return ret;
	switch (prop) {
	case POWER_SUPPLY_PROP_CAPACITY:
		value->intval = sample.capacity;
		break;
	case POWER_SUPPLY_PROP_VOLTAGE_NOW:
		value->intval = sample.voltage_uv;
		break;
	case POWER_SUPPLY_PROP_TEMP:
		value->intval = sample.temp_decic;
		break;
	default:
		return -EINVAL;
	}
	return 0;
}

static enum power_supply_property myron_readonly_properties[] = {
	POWER_SUPPLY_PROP_STATUS,
	POWER_SUPPLY_PROP_HEALTH,
	POWER_SUPPLY_PROP_CAPACITY,
	POWER_SUPPLY_PROP_VOLTAGE_NOW,
	POWER_SUPPLY_PROP_TEMP,
};

static const struct power_supply_desc myron_readonly_desc = {
	.name = "battery",
	.type = POWER_SUPPLY_TYPE_BATTERY,
	.properties = myron_readonly_properties,
	.num_properties = ARRAY_SIZE(myron_readonly_properties),
	.get_property = myron_readonly_get_property,
	.no_thermal = true,
};

static enum power_supply_property myron_readonly_extended_properties[] = {
	POWER_SUPPLY_PROP_STATUS,
	POWER_SUPPLY_PROP_HEALTH,
	POWER_SUPPLY_PROP_CAPACITY,
	POWER_SUPPLY_PROP_VOLTAGE_NOW,
	POWER_SUPPLY_PROP_TEMP,
	POWER_SUPPLY_PROP_CURRENT_NOW,
};
static const struct power_supply_desc myron_readonly_extended_desc = {
	.name = "battery",
	.type = POWER_SUPPLY_TYPE_BATTERY,
	.properties = myron_readonly_extended_properties,
	.num_properties = ARRAY_SIZE(myron_readonly_extended_properties),
	.get_property = myron_readonly_get_property,
	.no_thermal = true,
};

static int myron_readonly_probe(struct i2c_client *client)
{
	struct power_supply_config cfg = {};
	struct myron_readonly_gauge *gauge;
	struct myron_readonly_sample sample;
	struct power_supply *existing, *psy;
	const struct power_supply_desc *desc;
	int ret;

	if (!enable_readonly)
		return -EPERM;
	if (client->addr != 0x55 || !client->dev.of_node ||
	    !of_device_is_compatible(client->dev.of_node, "ti,bq27z561_master"))
		return -ENODEV;
	if (!i2c_check_functionality(client->adapter, I2C_FUNC_SMBUS_READ_WORD_DATA))
		return -EOPNOTSUPP;
	/* Even with cfg.of_node unset, the core reads this parent reference
	 * and may expose extra battery-info properties. Refuse all forms.
	 */
	if (device_property_present(&client->dev, "monitored-battery"))
		return -EOPNOTSUPP;
	existing = power_supply_get_by_name(myron_readonly_desc.name);
	if (existing) {
		power_supply_put(existing);
		return -EBUSY;
	}

	gauge = devm_kzalloc(&client->dev, sizeof(*gauge), GFP_KERNEL);
	if (!gauge)
		return -ENOMEM;
	gauge->client = client;
	gauge->extended_readonly = enable_extended_readonly;
	mutex_init(&gauge->lock);
	ret = myron_readonly_sample(gauge, &sample);
	if (ret)
		return dev_err_probe(&client->dev, ret,
			"read-only telemetry sample unavailable\n");
	cfg.drv_data = gauge;
	desc = &myron_readonly_desc;
	if (gauge->extended_readonly) {
		desc = &myron_readonly_extended_desc;
		/* Core device groups share the managed supply's lifetime. */
		cfg.attr_grp = myron_readonly_diag_groups;
	}
	/* Context is ready for register-time callbacks. Devres unregisters
	 * this supply and cancels the core's work before freeing the context.
	 * A racing same-name registration is rejected by the device core.
	 */
	psy = devm_power_supply_register(&client->dev, desc, &cfg);
	if (IS_ERR(psy))
		return dev_err_probe(&client->dev, PTR_ERR(psy),
			"read-only telemetry registration failed\n");
	dev_info(&client->dev,
		 "read-only battery telemetry ready; charging state unknown\n");
	return 0;
}

static const struct of_device_id myron_readonly_match[] = {
	{ .compatible = "ti,bq27z561_master" },
	{},
};
/* Deliberately no exported modalias: load this opt-in module explicitly. */

static struct i2c_driver myron_readonly_driver = {
	.driver = {
		.name = "myron_bq_readonly",
		.of_match_table = myron_readonly_match,
	},
	.probe = myron_readonly_probe,
};

static int __init myron_readonly_init(void)
{
	/* No bus registration or hardware access without explicit opt-in. */
	if (!enable_readonly)
		return -EPERM;
	return i2c_add_driver(&myron_readonly_driver);
}
module_init(myron_readonly_init);

static void __exit myron_readonly_exit(void)
{
	i2c_del_driver(&myron_readonly_driver);
}
module_exit(myron_readonly_exit);

MODULE_DESCRIPTION("Opt-in read-only battery telemetry");
MODULE_LICENSE("GPL");
