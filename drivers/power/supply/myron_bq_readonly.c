// SPDX-License-Identifier: GPL-2.0
/*
 * Minimal opt-in battery telemetry. No charging, authentication, firmware,
 * persistent storage operations are implemented. A separately enabled, fixed
 * manufacturer-name query writes only its command selector once during probe.
 */
#include <linux/device.h>
#include <linux/delay.h>
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
#include <linux/string.h>
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

/* A separately identified provider owns freshness and status interpretation.
 * Gauge flags/current never imply a charging state here.
 */
static bool enable_status_readonly;
module_param(enable_status_readonly, bool, 0444);
MODULE_PARM_DESC(enable_status_readonly,
	"Forward verified read-only MCA status; requires both telemetry opt-ins");

/* This is a command-selector write followed by a read, not a passive read.
 * The only admitted MAC is ManufacturerName(0x004c); there is no data/checksum
 * write, arbitrary command, authentication operation or charging control.
 */
static bool enable_manufacturer_query;
module_param(enable_manufacturer_query, bool, 0444);
MODULE_PARM_DESC(enable_manufacturer_query,
	"Opt in to one fixed manufacturer-name query during probe; requires both telemetry opt-ins");

#define MYRON_MAC_REGISTER	0x3e
#define MYRON_MAC_MANUFACTURER	0x004c
#define MYRON_MAC_FRAME_BYTES	36
#define MYRON_MAC_PAYLOAD_BYTES	32

struct myron_readonly_gauge {
	struct i2c_client *client;
	struct power_supply *psy;
	struct mutex lock;
	bool extended_readonly;
	bool status_readonly;
	int manufacturer_error;
	unsigned int manufacturer_length;
	u8 manufacturer_name[MYRON_MAC_PAYLOAD_BYTES];
};

/* Called once before publication, with no retry or userspace trigger.
 * SLUUC54C 12.1.26-29/12.8.30 and the stock driver use this register window.
 * The length includes command, checksum and length itself. A valid response
 * needs at least three payload bytes to contain the vendor discriminator;
 * never infer a variant from the DT alias, missing bytes or a failed query.
 */
static int myron_manufacturer_query(struct myron_readonly_gauge *gauge)
{
	u8 selector[] = { MYRON_MAC_REGISTER, MYRON_MAC_MANUFACTURER, 0 };
	u8 reg = MYRON_MAC_REGISTER;
	u8 frame[MYRON_MAC_FRAME_BYTES] = { 0 };
	struct i2c_msg select = {
		.addr = gauge->client->addr,
		.flags = 0,
		.len = sizeof(selector),
		.buf = selector,
	};
	struct i2c_msg read[] = {
		{ .addr = gauge->client->addr, .flags = 0,
		  .len = 1, .buf = &reg },
		{ .addr = gauge->client->addr, .flags = I2C_M_RD,
		  .len = sizeof(frame), .buf = frame },
	};
	unsigned int length, i, sum = 0;
	int ret;

	if (!i2c_check_functionality(gauge->client->adapter, I2C_FUNC_I2C))
		return -EOPNOTSUPP;
	mutex_lock(&gauge->lock);
	ret = i2c_transfer(gauge->client->adapter, &select, 1);
	if (ret != 1) {
		ret = ret < 0 ? ret : -EIO;
		goto out;
	}
	usleep_range(4000, 4100);
	ret = i2c_transfer(gauge->client->adapter, read, ARRAY_SIZE(read));
	if (ret != ARRAY_SIZE(read)) {
		ret = ret < 0 ? ret : -EIO;
		goto out;
	}
	length = frame[35];
	if (length < 7 || length > sizeof(frame) ||
	    frame[0] != (u8)MYRON_MAC_MANUFACTURER ||
	    frame[1] != (u8)(MYRON_MAC_MANUFACTURER >> 8)) {
		ret = -EPROTO;
		goto out;
	}
	for (i = 0; i < length - 2; i++)
		sum += frame[i];
	if ((u8)(0xff - (sum & 0xff)) != frame[34]) {
		ret = -EBADMSG;
		goto out;
	}
	memcpy(gauge->manufacturer_name, frame + 2, length - 4);
	gauge->manufacturer_length = length - 4;
	ret = 0;
out:
	mutex_unlock(&gauge->lock);
	return ret;
}

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

static ssize_t manufacturer_name_show(struct device *dev,
				     struct device_attribute *attr, char *buf)
{
	struct myron_readonly_gauge *gauge =
		power_supply_get_drvdata(to_power_supply(dev));

	(void)attr;
	/* Immutable post-probe evidence. Reading this file never sends I2C. */
	if (gauge->manufacturer_error)
		return sysfs_emit(buf, "command=0x004c valid=0 error=%d\n",
				  gauge->manufacturer_error);
	return sysfs_emit(buf,
		"command=0x004c valid=1 length=%u discriminator=0x%02x payload=%*phN\n",
		gauge->manufacturer_length, gauge->manufacturer_name[2],
		(int)gauge->manufacturer_length, gauge->manufacturer_name);
}
static DEVICE_ATTR_RO(manufacturer_name);

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

static struct attribute *myron_manufacturer_diag_attrs[] = {
	&dev_attr_battery_status_raw.attr,
	&dev_attr_manufacturer_name.attr,
	NULL,
};
static const struct attribute_group myron_manufacturer_diag_group = {
	.name = "myron_readonly_diag",
	.attrs = myron_manufacturer_diag_attrs,
};
static const struct attribute_group *myron_manufacturer_diag_groups[] = {
	&myron_manufacturer_diag_group,
	NULL,
};

static int myron_readonly_status(struct myron_readonly_gauge *gauge)
{
	union power_supply_propval model = {}, value = {};
	struct power_supply *usb;
	int status = POWER_SUPPLY_STATUS_UNKNOWN;

	if (!gauge->status_readonly)
		return status;
	/* A PSY reference pins this device, not the supplier's driver context.
	 * The admitted provider marks removing under this same lock before its
	 * unregister/context teardown. No gauge mutex is held across the query.
	 * Only a validated fresh cache is queried; no GET is submitted here.
	 */
	usb = power_supply_get_by_name("usb");
	if (!usb)
		return status;
	device_lock(&usb->dev);
	if (READ_ONCE(usb->removing))
		goto out;
	if (power_supply_get_property(usb, POWER_SUPPLY_PROP_MODEL_NAME, &model) ||
	    !model.strval || strcmp(model.strval, "myron-mca-readonly"))
		goto out;
	if (power_supply_get_property(usb, POWER_SUPPLY_PROP_STATUS, &value))
		goto out;
	switch (value.intval) {
	case POWER_SUPPLY_STATUS_UNKNOWN:
	case POWER_SUPPLY_STATUS_CHARGING:
	case POWER_SUPPLY_STATUS_DISCHARGING:
	case POWER_SUPPLY_STATUS_NOT_CHARGING:
	case POWER_SUPPLY_STATUS_FULL:
		status = value.intval;
		break;
	default:
		break;
	}
out:
	device_unlock(&usb->dev);
	/* The final reference may free the device, so unlock before putting it. */
	power_supply_put(usb);
	return status;
}

static void myron_readonly_external_power_changed(struct power_supply *psy)
{
	/* This callback is installed only for the status-enabled descriptor.
	 * It never dereferences gauge context or queries another supply. The
	 * remove barrier excludes scheduling new work after teardown starts.
	 */
	device_lock(&psy->dev);
	if (!READ_ONCE(psy->removing))
		power_supply_changed(psy);
	device_unlock(&psy->dev);
}

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
		value->intval = myron_readonly_status(gauge);
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

/* Expose the verified battery TEMP through the core tripless thermal zone.
 * The core converts deci-C to milli-C and unregisters it with this supply.
 * No trip points or charging policy are created here.
 */
static const struct power_supply_desc myron_readonly_desc = {
	.name = "battery",
	.type = POWER_SUPPLY_TYPE_BATTERY,
	.properties = myron_readonly_properties,
	.num_properties = ARRAY_SIZE(myron_readonly_properties),
	.get_property = myron_readonly_get_property,
	.no_thermal = false,
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
	.no_thermal = false,
};

/* Separate descriptor keeps original opt-ins free of event callbacks. */
static const struct power_supply_desc myron_readonly_status_desc = {
	.name = "battery",
	.type = POWER_SUPPLY_TYPE_BATTERY,
	.properties = myron_readonly_extended_properties,
	.num_properties = ARRAY_SIZE(myron_readonly_extended_properties),
	.get_property = myron_readonly_get_property,
	.external_power_changed = myron_readonly_external_power_changed,
	.no_thermal = false,
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
	if (enable_status_readonly && !enable_extended_readonly)
		return -EPERM;
	if (enable_manufacturer_query && !enable_extended_readonly)
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
	gauge->status_readonly = enable_status_readonly;
	gauge->manufacturer_error = -EOPNOTSUPP;
	mutex_init(&gauge->lock);
	ret = myron_readonly_sample(gauge, &sample);
	if (ret)
		return dev_err_probe(&client->dev, ret,
			"read-only telemetry sample unavailable\n");
	if (enable_manufacturer_query)
		gauge->manufacturer_error = myron_manufacturer_query(gauge);
	cfg.drv_data = gauge;
	desc = &myron_readonly_desc;
	if (gauge->extended_readonly) {
		desc = &myron_readonly_extended_desc;
		/* Core device groups share the managed supply's lifetime. */
		cfg.attr_grp = enable_manufacturer_query ?
			myron_manufacturer_diag_groups : myron_readonly_diag_groups;
	}
	if (gauge->status_readonly)
		desc = &myron_readonly_status_desc;
	/* Context is ready for register-time callbacks. Devres unregisters
	 * this supply and cancels the core's work before freeing the context.
	 * A racing same-name registration is rejected by the device core.
	 */
	psy = devm_power_supply_register(&client->dev, desc, &cfg);
	if (IS_ERR(psy))
		return dev_err_probe(&client->dev, PTR_ERR(psy),
			"read-only telemetry registration failed\n");
	gauge->psy = psy;
	i2c_set_clientdata(client, gauge);
	dev_info(&client->dev, "read-only battery telemetry ready; status forwarding %s\n",
		 gauge->status_readonly ? "enabled" : "disabled");
	return 0;
}

static void myron_readonly_remove(struct i2c_client *client)
{
	struct myron_readonly_gauge *gauge = i2c_get_clientdata(client);

	/* Exclude external callbacks before devres unregister cancels PSY work.
	 * Do not hold this lock while the core drains work or releases resources.
	 */
	if (gauge->status_readonly) {
		device_lock(&gauge->psy->dev);
		WRITE_ONCE(gauge->psy->removing, true);
		device_unlock(&gauge->psy->dev);
	}
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
	.remove = myron_readonly_remove,
};

static int __init myron_readonly_init(void)
{
	/* No bus registration or hardware access without explicit opt-in. */
	if (!enable_readonly)
		return -EPERM;
	if (enable_status_readonly && !enable_extended_readonly)
		return -EPERM;
	if (enable_manufacturer_query && !enable_extended_readonly)
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
