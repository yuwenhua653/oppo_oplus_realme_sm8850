// SPDX-License-Identifier: GPL-2.0-only
/*
 * Myron thermal request observer. This is deliberately NOT a charger policy.
 * Sysfs writes record unverified requests; they never program hardware, vote,
 * publish a cooling state, or establish a temperature/freshness guarantee.
 */
#include <linux/device.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/sysfs.h>
#include <linux/timekeeping.h>

#define MT_ROWS 15
#define MT_COLS 10
#define MT_CELLS (MT_ROWS * MT_COLS)

static bool enable_observer;
module_param(enable_observer, bool, 0444);
MODULE_PARM_DESC(enable_observer, "Opt in to recording unverified thermal requests; no charger control");

/* Exact live 600-byte wired_thermal property, decoded big-endian u32 cells.
 * Raw SHA256: 6539e46407caa74c604290577741c36f730ee0051c1c5bb27698c0422f714bca
 * Table values are mA; current request attributes below remain raw uA.
 */
static const u32 mt_expected[MT_ROWS][MT_COLS] = {
	{ 1900, 1500, 1900, 3000, 13500, 13500, 13500, 13500, 13500, 13500 },
	{ 1900, 1500, 1900, 3000, 11000, 11000, 11000, 11000, 11000, 11000 },
	{ 1900, 1500, 1900, 3000, 9000, 9000, 9000, 9000, 9000, 9000 },
	{ 1900, 1450, 1900, 3000, 8000, 8000, 8000, 8000, 8000, 8000 },
	{ 1900, 1400, 1900, 3000, 7000, 7000, 7000, 7000, 7000, 7000 },
	{ 1900, 1350, 1900, 2800, 6000, 6000, 6000, 6000, 6000, 6000 },
	{ 1900, 1300, 1900, 2600, 5000, 5000, 5000, 5000, 5000, 5000 },
	{ 1900, 1150, 1900, 2310, 4000, 4000, 4000, 4000, 4000, 4000 },
	{ 1700, 1100, 1700, 2200, 3500, 3500, 3500, 3500, 3500, 3500 },
	{ 1600, 1000, 1600, 2000, 3000, 3000, 3000, 3000, 3000, 3000 },
	{ 1400, 900, 1500, 2000, 2500, 2500, 2500, 2500, 2500, 2500 },
	{ 1200, 850, 1500, 2000, 2000, 2000, 2000, 2000, 2000, 2000 },
	{ 1100, 750, 1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500 },
	{ 1100, 650, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000 },
	{ 1100, 600, 500, 500, 500, 500, 500, 500, 500, 500 },
};

enum mt_input_id {
	MT_LEVEL,
	MT_CURRENT,
	MT_CURRENT2,
	MT_REMOVE,
	MT_INPUTS,
};

static const char * const mt_names[MT_INPUTS] = {
	"wired_ctrl_limit", "wired_chg_curr", "wired_chg_curr2",
	"wired_thermal_remove",
};

struct mt_record {
	bool seen;
	u32 raw;
	u64 sequence;
	u64 boottime_ns;
};

struct mt_observer {
	struct mutex lock;
	u64 accepted_sequence;
	struct mt_record input[MT_INPUTS];
};

/* Reject signs, spaces, embedded NUL, overflow, and multiple lines. */
static int mt_parse_scalar(const char *buf, size_t count, u32 *value)
{
	u32 parsed = 0;
	size_t i, digits = count;

	if (!count || count > 11)
		return -EINVAL;
	if (buf[digits - 1] == '\n')
		digits--;
	if (!digits || digits > 10)
		return -EINVAL;
	for (i = 0; i < digits; i++) {
		u32 digit;

		if (buf[i] < '0' || buf[i] > '9')
			return -EINVAL;
		digit = buf[i] - '0';
		if (parsed > (U32_MAX - digit) / 10)
			return -ERANGE;
		parsed = parsed * 10 + digit;
	}
	*value = parsed;
	return 0;
}

static int mt_check_table(struct device_node *node)
{
	u32 cells[MT_CELLS];
	int count, ret, row, col;

	if (!node || !of_device_is_available(node) ||
	    !of_device_is_compatible(node, "mca_charger_thermal"))
		return -ENODEV;
	count = of_property_count_u32_elems(node, "wired_thermal");
	if (count != MT_CELLS)
		return -EINVAL;
	ret = of_property_read_u32_array(node, "wired_thermal", cells,
				       MT_CELLS);
	if (ret)
		return ret;
	for (row = 0; row < MT_ROWS; row++)
		for (col = 0; col < MT_COLS; col++)
			if (cells[row * MT_COLS + col] != mt_expected[row][col])
				return -EINVAL;
	return 0;
}

static ssize_t mt_store(struct device *dev, enum mt_input_id id,
			const char *buf, size_t count)
{
	struct mt_observer *observer = dev_get_drvdata(dev);
	struct mt_record *record;
	u32 value;
	int ret;

	if (!observer)
		return -ENODEV;
	ret = mt_parse_scalar(buf, count, &value);
	if (ret)
		return ret;
	if ((id == MT_LEVEL && value > MT_ROWS) ||
	    (id == MT_REMOVE && value > 1) ||
	    ((id == MT_CURRENT || id == MT_CURRENT2) && value > INT_MAX))
		return -ERANGE;
	mutex_lock(&observer->lock);
	if (observer->accepted_sequence == U64_MAX) {
		mutex_unlock(&observer->lock);
		return -EOVERFLOW;
	}
	record = &observer->input[id];
	record->raw = value;
	record->sequence = ++observer->accepted_sequence;
	record->boottime_ns = ktime_get_boottime_ns();
	record->seen = true;
	mutex_unlock(&observer->lock);
	return count;
}

static ssize_t mt_show(struct device *dev, enum mt_input_id id, char *buf)
{
	struct mt_observer *observer = dev_get_drvdata(dev);
	ssize_t len;

	if (!observer)
		return -ENODEV;
	mutex_lock(&observer->lock);
	if (observer->input[id].seen)
		len = sysfs_emit(buf, "%u\n", observer->input[id].raw);
	else
		len = -ENODATA;
	mutex_unlock(&observer->lock);
	return len;
}

#define MT_INPUT_ATTR(name, id) \
static ssize_t name##_show(struct device *dev, \
		struct device_attribute *attr, char *buf) \
{ \
	return mt_show(dev, id, buf); \
} \
static ssize_t name##_store(struct device *dev, \
		struct device_attribute *attr, const char *buf, size_t count) \
{ \
	return mt_store(dev, id, buf, count); \
} \
static DEVICE_ATTR(name, 0600, name##_show, name##_store)

MT_INPUT_ATTR(wired_ctrl_limit, MT_LEVEL);
MT_INPUT_ATTR(wired_chg_curr, MT_CURRENT);
MT_INPUT_ATTR(wired_chg_curr2, MT_CURRENT2);
MT_INPUT_ATTR(wired_thermal_remove, MT_REMOVE);

static const char *mt_meaning(enum mt_input_id id, const struct mt_record *rec)
{
	if (!rec->seen)
		return "unknown";
	if (id == MT_LEVEL)
		return rec->raw ? "table_row_observed" : "no_table_selection";
	if (id == MT_REMOVE)
		return rec->raw ? "removal_requested" :
			"remove_flag_clear_not_validation";
	return rec->raw ? "current_request_uA_selection_unknown" :
		"raw_zero_observed";
}

static ssize_t snapshot_show(struct device *dev,
			     struct device_attribute *attr, char *buf)
{
	struct mt_observer *observer = dev_get_drvdata(dev);
	struct mt_record *level;
	ssize_t len;
	int i;

	if (!observer)
		return -ENODEV;
	mutex_lock(&observer->lock);
	len = sysfs_emit(buf,
		"schema=1\nobserver=myron_buck_thermal\nmode=observer_only\n"
		"observer_enabled=1\ndt_table_match_at_probe=1\n"
		"table_scope=probe_snapshot\n"
		"source_verified=0\neligible_for_control=0\nhardware_applied=0\n"
		"active_mode_selected=0\n"
		"sensor_freshness=unknown\nrequest_ttl=undefined\n"
		"timestamp_kind=boottime_receipt\n"
		"timestamp_semantics=request_receipt_not_sensor_sample\n"
		"current_channel_selection=unknown\n"
		"accepted_sequence=%llu\n",
		(unsigned long long)observer->accepted_sequence);
	for (i = 0; i < MT_INPUTS; i++) {
		const struct mt_record *record = &observer->input[i];

		len += sysfs_emit_at(buf, len,
			"%s.seen=%u\n", mt_names[i], record->seen);
		if (record->seen)
			len += sysfs_emit_at(buf, len, "%s.raw=%u\n",
					     mt_names[i], record->raw);
		else
			len += sysfs_emit_at(buf, len, "%s.raw=unknown\n",
					     mt_names[i]);
		len += sysfs_emit_at(buf, len,
			"%s.sequence=%llu\n"
			"%s.boottime_ns=%llu\n%s.ingress=%s\n%s.meaning=%s\n",
			mt_names[i], (unsigned long long)record->sequence,
			mt_names[i], (unsigned long long)record->boottime_ns,
			mt_names[i], record->seen ? "sysfs_unverified" : "none",
			mt_names[i], mt_meaning(i, record));
	}
	level = &observer->input[MT_LEVEL];
	if (level->seen && level->raw) {
		const u32 *row = mt_expected[level->raw - 1];

		len += sysfs_emit_at(buf, len,
			"table_observed_row_index=%u\ntable_observed_row_cells_mA="
			"%u,%u,%u,%u,%u,%u,%u,%u,%u,%u\n",
			level->raw - 1, row[0], row[1], row[2], row[3], row[4],
			row[5], row[6], row[7], row[8], row[9]);
	} else {
		len += sysfs_emit_at(buf, len,
			"table_observed_row_index=none\ntable_observed_row_cells_mA=none\n");
	}
	mutex_unlock(&observer->lock);
	return len;
}
static DEVICE_ATTR_RO(snapshot);

static struct attribute *mt_attrs[] = {
	&dev_attr_wired_ctrl_limit.attr,
	&dev_attr_wired_chg_curr.attr,
	&dev_attr_wired_chg_curr2.attr,
	&dev_attr_wired_thermal_remove.attr,
	&dev_attr_snapshot.attr,
	NULL,
};

static const struct attribute_group mt_group = {
	.name = "myron_buck_thermal",
	.attrs = mt_attrs,
};

static int mt_probe(struct platform_device *pdev)
{
	struct mt_observer *observer;
	int ret;

	if (!enable_observer)
		return -EPERM;
	ret = mt_check_table(pdev->dev.of_node);
	if (ret)
		return ret;
	observer = devm_kzalloc(&pdev->dev, sizeof(*observer), GFP_KERNEL);
	if (!observer)
		return -ENOMEM;
	mutex_init(&observer->lock);
	platform_set_drvdata(pdev, observer);
	ret = sysfs_create_group(&pdev->dev.kobj, &mt_group);
	if (ret)
		platform_set_drvdata(pdev, NULL);
	return ret;
}

static void mt_remove(struct platform_device *pdev)
{
	/* Deactivate and drain sysfs callbacks before devres frees their context.
	 * Do not hold observer->lock while draining an in-flight show/store.
	 */
	sysfs_remove_group(&pdev->dev.kobj, &mt_group);
	platform_set_drvdata(pdev, NULL);
}

static const struct of_device_id mt_of_match[] = {
	{ .compatible = "mca_charger_thermal" },
	{ }
};
MODULE_DEVICE_TABLE(of, mt_of_match);

static struct platform_driver mt_driver = {
	.probe = mt_probe,
	.remove = mt_remove,
	.driver = {
		.name = "myron_buck_thermal",
		.of_match_table = mt_of_match,
	},
};

static int __init myron_buck_thermal_init(void)
{
	if (!enable_observer)
		return -EPERM;
	return platform_driver_register(&mt_driver);
}
module_init(myron_buck_thermal_init);

static void __exit mt_exit(void)
{
	platform_driver_unregister(&mt_driver);
}
module_exit(mt_exit);

MODULE_DESCRIPTION("Myron unverified thermal-request observer; no charging control");
MODULE_LICENSE("GPL");
