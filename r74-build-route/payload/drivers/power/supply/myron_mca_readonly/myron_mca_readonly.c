// SPDX-License-Identifier: GPL-2.0-only
/* Fixed MCA GET allowlist, with separately opted-in read-only reporting. */
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/completion.h>
#include <linux/workqueue.h>
#include <linux/sysfs.h>
#include <linux/ktime.h>
#include <linux/timekeeping.h>
#include <linux/jiffies.h>
#include <linux/limits.h>
#include <linux/random.h>
#include <linux/string.h>
#include <linux/err.h>
#include <linux/power_supply.h>
#include <linux/soc/qcom/qti_pmic_glink.h>

#define MR_OWNER 0x800aU
#define MR_TYPE 1U
#define MR_READ 1U
#define MR_PROPERTIES 6U
#define MR_ROUNDS 60U
#define MR_INTERVAL_MS 5000U
#define MR_ACK_MS 250U
#define MR_MAX_REQUESTS (MR_PROPERTIES * MR_ROUNDS)
#define MR_MAX_CONSECUTIVE_TIMEOUTS 3U
#define MR_FRESH_MS 15000U
#define MR_NOTIFY_MS 1000U
/* Conservative physical envelopes, not negotiated limits or setpoints. */
#define MR_MAX_BUS_UV 60000000U
#define MR_MAX_BUS_UA 15000000U
#define MR_NODE "/soc/pmic-glink/mca,adsp_glink"

static bool enable_readonly;
module_param(enable_readonly, bool, 0444);
MODULE_PARM_DESC(enable_readonly, "Explicit opt-in to bounded six-property GET diagnostics");
static bool enable_power_supply;
module_param(enable_power_supply, bool, 0444);
MODULE_PARM_DESC(enable_power_supply, "Also opt in to continuously refreshed read-only USB reporting");

/* These are MCA property IDs, not QTI battery-charger property IDs. */
static const u32 mr_properties[MR_PROPERTIES] = {
	0x20001, /* USB_ONLINE */
	0x20002, /* BUS_VOLT */
	0x20004, /* BUS_CURR */
	0x2000c, /* USB_REAL_TYPE */
	0x2001,  /* CHG_STATUS */
	0x2008,  /* INPUT_CURR_LIMIT */
};

struct mr_request {
	struct pmic_glink_hdr hdr;
	u32 property;
	u32 seq;
	u8 data[256];
} __packed;

struct mr_response {
	struct pmic_glink_hdr hdr;
	u32 property;
	u32 remote_status;
	u32 seq;
	u8 data[256];
} __packed;

struct mr_sample {
	u32 property;
	u32 seq;
	u32 raw;
	u32 remote_status;
	int error;
	bool attempted;
	bool response_seen;
	u64 start_ms;
	u64 end_ms;
};

struct mr_cache {
	struct mr_sample samples[MR_PROPERTIES];
	u32 round;
	u64 start_ms;
	u64 end_ms;
};

struct mr_supply_cache {
	bool valid;
	u64 expires_ms;
	int online;
	int voltage_uv;
	int current_ua;
	int status;
};

struct mr_device {
	struct pmic_glink_client *client;
	spinlock_t lock;
	struct completion ack;
	struct delayed_work work;
	struct delayed_work notify_work;
	struct power_supply *psy;
	bool reporting;
	bool notify_pending;
	u32 generation;
	struct mr_supply_cache supply;
	bool stopping;
	bool link_up;
	bool pending;
	bool active;
	bool finished;
	bool initial_link_assumed;
	bool firmware_reply_seen;
	u32 consecutive_timeouts;
	u32 stop_reason; /* 0 running, 1 round limit, 2 timeout, 3 removal, 4 overflow */
	u32 next_seq;
	u32 requests_sent;
	u32 pending_property;
	u32 pending_seq;
	u32 pending_raw;
	u32 pending_remote_status;
	int pending_error;
	bool pending_response_seen;
	u64 run_start_ms;
	u64 run_end_ms;
	struct mr_cache cache;
};

static u64 mr_now_ms(void)
{
	return ktime_get_boottime_ns() / 1000000;
}

/* Caller holds lock. Invalidity persists until a new coherent round. */
static void mr_invalidate(struct mr_device *m)
{
	if (m->supply.valid)
		m->notify_pending = true;
	m->supply.valid = false;
}

static bool mr_supply_fresh(struct mr_device *m, u64 now)
{
	return m->supply.valid && !m->stopping && !m->finished &&
		m->link_up && now < m->supply.expires_ms &&
		now >= m->supply.expires_ms - MR_FRESH_MS;
}

static int mr_supply_get(struct power_supply *psy,
			enum power_supply_property property,
			union power_supply_propval *value)
{
	struct mr_device *m = power_supply_get_drvdata(psy);
	unsigned long flags;
	int ret = 0;

	/* Identity remains readable when telemetry is absent; never sends a GET. */
	if (property == POWER_SUPPLY_PROP_MODEL_NAME) {
		value->strval = "myron-mca-readonly";
		return 0;
	}
	spin_lock_irqsave(&m->lock, flags);
	if (!mr_supply_fresh(m, mr_now_ms())) {
		if (property == POWER_SUPPLY_PROP_STATUS)
			value->intval = POWER_SUPPLY_STATUS_UNKNOWN;
		else
			ret = -ENODATA;
		goto out;
	}
	switch (property) {
	case POWER_SUPPLY_PROP_ONLINE:
		value->intval = m->supply.online;
		break;
	case POWER_SUPPLY_PROP_VOLTAGE_NOW:
		value->intval = m->supply.voltage_uv;
		break;
	case POWER_SUPPLY_PROP_CURRENT_NOW:
		value->intval = m->supply.current_ua;
		break;
	case POWER_SUPPLY_PROP_STATUS:
		value->intval = m->supply.status;
		break;
	default:
		ret = -EINVAL;
	}
out:
	spin_unlock_irqrestore(&m->lock, flags);
	return ret;
}

static const enum power_supply_property mr_supply_properties[] = {
	POWER_SUPPLY_PROP_ONLINE,
	POWER_SUPPLY_PROP_VOLTAGE_NOW,
	POWER_SUPPLY_PROP_CURRENT_NOW,
	POWER_SUPPLY_PROP_STATUS,
	POWER_SUPPLY_PROP_MODEL_NAME,
};
static const struct power_supply_desc mr_supply_desc = {
	.name = "usb",
	.type = POWER_SUPPLY_TYPE_USB,
	.properties = mr_supply_properties,
	.num_properties = ARRAY_SIZE(mr_supply_properties),
	.get_property = mr_supply_get,
	.no_thermal = true,
};
static char *mr_supplied_to[] = { "battery" };

/* Xiaomi MCA enum from mca_event.h, not Linux/BatteryManager status numbers.
 * INHIBIT (0) is deliberately unknown: the reference policy treats it as
 * charging, but the label alone is insufficient for this read-only bridge.
 */
static int mr_status(u32 online, u32 raw)
{
	if (!online)
		return raw == 6 || raw == 7 ? POWER_SUPPLY_STATUS_DISCHARGING :
			POWER_SUPPLY_STATUS_UNKNOWN;
	switch (raw) {
	case 1: /* TRICKLE */
	case 2: /* PRECHARGE */
	case 3: /* FULLON */
	case 4: /* TAPER */
	case 8: /* FAST_LINEAR */
		return POWER_SUPPLY_STATUS_CHARGING;
	case 5: /* TERMINATION */
		return POWER_SUPPLY_STATUS_FULL;
	case 6: /* PAUSE */
	case 7: /* CHARGING_DISABLED */
		return POWER_SUPPLY_STATUS_NOT_CHARGING;
	default:
		return POWER_SUPPLY_STATUS_UNKNOWN;
	}
}

/* Caller holds lock; all six replies belong to one uninterrupted link epoch.
 * Sequential samples are not an atomic firmware snapshot. Contradictory
 * offline/charging replies are therefore withheld instead of extrapolated.
 */
static void mr_publish(struct mr_device *m, const struct mr_cache *cache,
		       u32 generation)
{
	struct mr_supply_cache next = { 0 };
	u64 start = cache->samples[0].start_ms;
	u64 now = mr_now_ms();
	u32 online = cache->samples[0].raw;
	u32 voltage = cache->samples[1].raw;
	u32 current = cache->samples[2].raw;
	u32 status = cache->samples[4].raw;
	unsigned int i;

	if (!m->reporting)
		return;
	if (m->stopping || m->finished || !m->link_up ||
	    generation != m->generation || online > 1 ||
	    voltage > MR_MAX_BUS_UV || voltage > INT_MAX ||
	    current > MR_MAX_BUS_UA || current > INT_MAX ||
	    (online && voltage < 1000000U) ||
	    (!online && status != 6 && status != 7) ||
	    start > now || now - start >= MR_FRESH_MS)
		goto invalid;
	for (i = 0; i < MR_PROPERTIES; i++) {
		const struct mr_sample *s = &cache->samples[i];
		if (!s->attempted || !s->response_seen || s->error ||
		    s->remote_status || s->start_ms < start ||
		    s->end_ms < s->start_ms || s->end_ms > now)
			goto invalid;
	}
	next.valid = true;
	next.expires_ms = start + MR_FRESH_MS;
	if (next.expires_ms < start)
		goto invalid;
	next.online = online;
	next.voltage_uv = voltage;
	next.current_ua = current;
	next.status = mr_status(online, status);
	if (!m->supply.valid || next.online != m->supply.online ||
	    next.voltage_uv != m->supply.voltage_uv ||
	    next.current_ua != m->supply.current_ua ||
	    next.status != m->supply.status)
		m->notify_pending = true;
	m->supply = next;
	return;
invalid:
	mr_invalidate(m);
}

/* Independent of the potentially blocking transport worker. Reads also
 * enforce expiry directly, including immediately after suspend/resume.
 */
static void mr_notify_work(struct work_struct *work)
{
	struct mr_device *m = container_of(to_delayed_work(work),
					 struct mr_device, notify_work);
	unsigned long flags;
	bool changed;

	spin_lock_irqsave(&m->lock, flags);
	if (!mr_supply_fresh(m, mr_now_ms()))
		mr_invalidate(m);
	changed = m->notify_pending;
	m->notify_pending = false;
	if (!m->stopping && !m->finished)
		schedule_delayed_work(&m->notify_work,
				      msecs_to_jiffies(MR_NOTIFY_MS));
	spin_unlock_irqrestore(&m->lock, flags);
	/* remove drains this work before unregistering the supply. */
	if (changed)
		power_supply_changed(m->psy);
}

static bool mr_property_allowed(u32 property)
{
	unsigned int i;

	for (i = 0; i < MR_PROPERTIES; i++)
		if (mr_properties[i] == property)
			return true;
	return false;
}

static int mr_receive(void *priv, void *data, size_t len)
{
	struct mr_device *m = priv;
	struct mr_response msg;
	unsigned long flags;
	u32 raw;

	if (!m || !data || len != sizeof(msg))
		return 0;
	/* Copy before interpretation; firmware buffers need not be aligned. */
	memcpy(&msg, data, sizeof(msg));
	if (msg.hdr.owner != MR_OWNER || msg.hdr.type != MR_TYPE ||
	    msg.hdr.opcode != MR_READ || !mr_property_allowed(msg.property))
		return 0;
	memcpy(&raw, msg.data, sizeof(raw));
	spin_lock_irqsave(&m->lock, flags);
	if (m->stopping || !m->pending ||
	    msg.property != m->pending_property || msg.seq != m->pending_seq)
		goto out;
	m->pending_remote_status = msg.remote_status;
	m->pending_response_seen = true;
	m->firmware_reply_seen = true;
	m->pending_error = msg.remote_status ? -EREMOTEIO : 0;
	if (!msg.remote_status)
		m->pending_raw = raw;
	m->pending = false;
	complete(&m->ack);
out:
	spin_unlock_irqrestore(&m->lock, flags);
	return 0;
}

static void mr_state(void *priv, enum pmic_glink_state state)
{
	struct mr_device *m = priv;
	unsigned long flags;

	if (!m)
		return;
	spin_lock_irqsave(&m->lock, flags);
	if (!m->stopping) {
		mr_invalidate(m);
		if (m->generation == U32_MAX) {
			m->finished = true;
			m->stop_reason = 4;
		} else {
			m->generation++;
		}
		m->initial_link_assumed = false;
		m->link_up = state == PMIC_GLINK_STATE_UP;
		/* Even DOWN-UP or duplicate UP invalidates the pending epoch. */
		if (m->pending) {
			m->pending = false;
			m->pending_error = -ENOTCONN;
			complete(&m->ack);
		}
	}
	spin_unlock_irqrestore(&m->lock, flags);
	/* Never transmit or unregister from a callback. */
}

/* Only the single worker calls this; client remains alive until worker drain. */
static void mr_get(struct mr_device *m, u32 property, struct mr_sample *sample)
{
	struct mr_request msg = { 0 };
	unsigned long flags;
	int ret;

	memset(sample, 0, sizeof(*sample));
	sample->property = property;
	sample->start_ms = mr_now_ms();
	if (!mr_property_allowed(property)) {
		ret = -EINVAL;
		goto finish;
	}
	spin_lock_irqsave(&m->lock, flags);
	if (m->stopping)
		ret = -ESHUTDOWN;
	else if (!m->link_up)
		ret = -ENOTCONN;
	else if (m->finished || m->next_seq == U32_MAX ||
		 m->requests_sent == U32_MAX ||
		 (!m->reporting && m->requests_sent >= MR_MAX_REQUESTS))
		ret = -EOVERFLOW;
	else
		ret = 0;
	if (ret) {
		spin_unlock_irqrestore(&m->lock, flags);
		goto finish;
	}
	msg.hdr.owner = MR_OWNER;
	msg.hdr.type = MR_TYPE;
	msg.hdr.opcode = MR_READ;
	msg.property = property;
	msg.seq = ++m->next_seq;
	sample->seq = msg.seq;
	reinit_completion(&m->ack);
	m->pending_property = property;
	m->pending_seq = msg.seq;
	m->pending_raw = 0;
	m->pending_remote_status = 0;
	m->pending_response_seen = false;
	m->pending_error = -EINPROGRESS;
	m->pending = true;
	m->requests_sent++;
	spin_unlock_irqrestore(&m->lock, flags);

	/* This send can itself block: MR_ACK_MS is NOT an end-to-end deadline. */
	sample->attempted = true;
	ret = pmic_glink_write(m->client, &msg, sizeof(msg));
	if (ret > 0)
		ret = -EPROTO;
	if (!ret && !wait_for_completion_timeout(&m->ack,
					msecs_to_jiffies(MR_ACK_MS)))
		ret = -ETIMEDOUT;
	spin_lock_irqsave(&m->lock, flags);
	m->pending = false;
	if (!ret)
		ret = m->pending_error;
	sample->response_seen = m->pending_response_seen;
	sample->remote_status = m->pending_remote_status;
	if (!ret)
		sample->raw = m->pending_raw;
	spin_unlock_irqrestore(&m->lock, flags);
finish:
	sample->error = ret;
	sample->end_ms = mr_now_ms();
}

static void mr_work(struct work_struct *work)
{
	struct mr_device *m = container_of(to_delayed_work(work), struct mr_device, work);
	struct mr_cache next = { 0 };
	unsigned long flags;
	unsigned int i;
	u32 generation;
	int abort_error = 0;

	spin_lock_irqsave(&m->lock, flags);
	if (m->stopping || m->finished ||
	    (!m->reporting && m->cache.round >= MR_ROUNDS)) {
		spin_unlock_irqrestore(&m->lock, flags);
		return;
	}
	if (m->cache.round == U32_MAX) {
		m->finished = true;
		m->stop_reason = 4;
		mr_invalidate(m);
		spin_unlock_irqrestore(&m->lock, flags);
		return;
	}
	m->active = true;
	if (!m->run_start_ms)
		m->run_start_ms = mr_now_ms();
	next.round = m->cache.round + 1;
	generation = m->generation;
	spin_unlock_irqrestore(&m->lock, flags);
	next.start_ms = mr_now_ms();
	for (i = 0; i < MR_PROPERTIES; i++) {
		mr_get(m, mr_properties[i], &next.samples[i]);
		/* A remote property rejection still allows the other fixed GETs. */
		if (next.samples[i].error && next.samples[i].error != -EREMOTEIO) {
			abort_error = next.samples[i].error;
			break;
		}
	}
	if (abort_error)
		for (++i; i < MR_PROPERTIES; i++) {
			next.samples[i].property = mr_properties[i];
			next.samples[i].error = -ECANCELED; /* not attempted */
		}
	next.end_ms = mr_now_ms();
	spin_lock_irqsave(&m->lock, flags);
	m->cache = next;
	m->active = false;
	if (abort_error == -ETIMEDOUT)
		m->consecutive_timeouts++;
	else
		m->consecutive_timeouts = 0;
	if (m->stopping || m->finished || abort_error == -EOVERFLOW ||
	    (!m->reporting && next.round >= MR_ROUNDS) ||
	    m->consecutive_timeouts >= MR_MAX_CONSECUTIVE_TIMEOUTS) {
		m->finished = true;
		m->stop_reason = m->stopping ? 3 :
			(m->consecutive_timeouts >= MR_MAX_CONSECUTIVE_TIMEOUTS ? 2 :
			 (abort_error == -EOVERFLOW || m->stop_reason == 4 ? 4 : 1));
		m->run_end_ms = next.end_ms;
	} else {
		/* Queue while stop is excluded; remove cancels after setting stop. */
		schedule_delayed_work(&m->work, msecs_to_jiffies(MR_INTERVAL_MS));
	}
	mr_publish(m, &next, generation);
	spin_unlock_irqrestore(&m->lock, flags);
}

static ssize_t snapshot_show(struct device *dev, struct device_attribute *attr, char *buf)
{
	struct mr_device *m = dev_get_drvdata(dev);
	struct mr_cache cache;
	unsigned long flags;
	unsigned int i;
	u32 requests, timeouts, stop_reason;
	u64 start, end;
	bool active, finished, stopping, link_up, assumed, reply_seen, reporting, visible;
	u32 generation;
	ssize_t len;

	spin_lock_irqsave(&m->lock, flags);
	cache = m->cache;
	requests = m->requests_sent;
	start = m->run_start_ms;
	end = m->run_end_ms;
	active = m->active;
	finished = m->finished;
	stopping = m->stopping;
	link_up = m->link_up;
	assumed = m->initial_link_assumed;
	reply_seen = m->firmware_reply_seen;
	timeouts = m->consecutive_timeouts;
	stop_reason = m->stop_reason;
	reporting = m->reporting;
	visible = mr_supply_fresh(m, mr_now_ms());
	generation = m->generation;
	spin_unlock_irqrestore(&m->lock, flags);
	len = sysfs_emit(buf, "protocol=1 owner=0x800a operation=GET round=%u max_rounds=%u active=%u finished=%u stopping=%u link_up=%u requests=%u max_requests=%u run_start_ms=%llu run_end_ms=%llu round_start_ms=%llu round_end_ms=%llu clock=BOOTTIME initial_link_assumed=%u firmware_reply_seen=%u consecutive_timeouts=%u stop_reason=%u\n",
		cache.round, reporting ? U32_MAX : MR_ROUNDS, active, finished, stopping, link_up,
		requests, reporting ? U32_MAX : MR_MAX_REQUESTS, (unsigned long long)start, (unsigned long long)end,
		(unsigned long long)cache.start_ms, (unsigned long long)cache.end_ms,
		assumed, reply_seen, timeouts, stop_reason);
	if (reporting)
		len += sysfs_emit_at(buf, len - 1,
			" power_supply_reporting=1 freshness_ms=%u supply_valid=%u generation=%u\n",
			MR_FRESH_MS, visible, generation) - 1;
	for (i = 0; i < MR_PROPERTIES; i++) {
		const struct mr_sample *s = &cache.samples[i];
		len += sysfs_emit_at(buf, len, "property=0x%08x seq=%u attempted=%u valid=%u raw_u32=%u raw_hex=0x%08x error=%d response_seen=%u remote_status=0x%08x start_ms=%llu end_ms=%llu\n",
			s->property, s->seq, s->attempted, s->error == 0, s->raw, s->raw, s->error,
			s->response_seen, s->remote_status,
			(unsigned long long)s->start_ms, (unsigned long long)s->end_ms);
	}
	return len;
}
static DEVICE_ATTR_RO(snapshot);

static struct attribute *mr_attrs[] = {
	&dev_attr_snapshot.attr,
	NULL,
};
static const struct attribute_group mr_group = {
	.name = "myron_mca_readonly",
	.attrs = mr_attrs,
};

static void mr_stop(struct mr_device *m)
{
	unsigned long flags;

	spin_lock_irqsave(&m->lock, flags);
	m->stopping = true;
	mr_invalidate(m);
	m->stop_reason = 3;
	if (m->pending) {
		m->pending = false;
		m->pending_error = -ESHUTDOWN;
		complete(&m->ack);
	}
	spin_unlock_irqrestore(&m->lock, flags);
}

static int mr_probe(struct platform_device *pdev)
{
	struct pmic_glink_client_data client_data = { 0 };
	struct power_supply_config supply_config = { 0 };
	struct device_node *expected;
	struct mr_device *m;
	unsigned int i;
	int ret;

	if (!enable_readonly)
		return -EPERM;
	/* OF full_name stores a node component, not its absolute DT path. */
	expected = of_find_node_by_path(MR_NODE);
	ret = expected && pdev->dev.of_node == expected ? 0 : -ENODEV;
	of_node_put(expected);
	if (ret)
		return ret;
	m = kzalloc(sizeof(*m), GFP_KERNEL);
	if (!m)
		return -ENOMEM;
	spin_lock_init(&m->lock);
	init_completion(&m->ack);
	INIT_DELAYED_WORK(&m->work, mr_work);
	INIT_DELAYED_WORK(&m->notify_work, mr_notify_work);
	m->reporting = enable_power_supply;
	m->generation = 1;
	/* Register requires an UP transport. Early DOWN callbacks must prevail. */
	m->link_up = true;
	m->initial_link_assumed = true;
	/* Reserve the entire bounded run; no sequence wrap or reuse in this instance. */
	m->next_seq = get_random_u32() % (U32_MAX - MR_MAX_REQUESTS);
	for (i = 0; i < MR_PROPERTIES; i++) {
		m->cache.samples[i].property = mr_properties[i];
		m->cache.samples[i].error = -ENODATA;
	}
	platform_set_drvdata(pdev, m);
	client_data.name = "myron_mca_readonly";
	client_data.id = MR_OWNER;
	client_data.priv = m;
	client_data.msg_cb = mr_receive;
	client_data.state_cb = mr_state;
	m->client = pmic_glink_register_client(&pdev->dev, &client_data);
	if (IS_ERR(m->client)) {
		ret = PTR_ERR(m->client);
		goto free_device;
	}
	ret = sysfs_create_group(&pdev->dev.kobj, &mr_group);
	if (ret) {
		mr_stop(m);
		/* No work has been queued. Lower layer must drain early callbacks. */
		pmic_glink_unregister_client_sync(m->client);
		goto free_device;
	}
	if (m->reporting) {
		supply_config.drv_data = m;
		supply_config.supplied_to = mr_supplied_to;
		supply_config.num_supplicants = ARRAY_SIZE(mr_supplied_to);
		m->psy = power_supply_register(&pdev->dev, &mr_supply_desc,
					      &supply_config);
		if (IS_ERR(m->psy)) {
			ret = PTR_ERR(m->psy);
			mr_stop(m);
			sysfs_remove_group(&pdev->dev.kobj, &mr_group);
			pmic_glink_unregister_client_sync(m->client);
			goto free_device;
		}
		schedule_delayed_work(&m->notify_work, 0);
	}
	schedule_delayed_work(&m->work, 0);
	return 0;
free_device:
	platform_set_drvdata(pdev, NULL);
	kfree(m);
	return ret;
}

static void mr_remove(struct platform_device *pdev)
{
	struct mr_device *m = platform_get_drvdata(pdev);

	mr_stop(m);
	/* Group removal drains active cache readers before driver data is freed. */
	sysfs_remove_group(&pdev->dev.kobj, &mr_group);
	cancel_delayed_work_sync(&m->work);
	cancel_delayed_work_sync(&m->notify_work);
	/* Requires the reviewed lower-layer unregister callback-drain contract. */
	pmic_glink_unregister_client_sync(m->client);
	if (m->psy) {
		/* Cooperative cross-supply readers hold this PSY device lock and
		 * check removing before invoking our getter. Drain them before
		 * unregister/free; power_supply_unregister takes the lock itself.
		 */
		device_lock(&m->psy->dev);
		WRITE_ONCE(m->psy->removing, true);
		device_unlock(&m->psy->dev);
		power_supply_unregister(m->psy);
	}
	platform_set_drvdata(pdev, NULL);
	kfree(m);
}

static const struct of_device_id mr_match[] = {
	{ .compatible = "mca,adsp_glink" },
	{ },
};
/* Deliberately no MODULE_DEVICE_TABLE: loading is explicit, never an alias. */
static struct platform_driver mr_driver = {
	.probe = mr_probe,
	.remove = mr_remove,
	.driver = {
		.name = "myron_mca_readonly",
		.of_match_table = mr_match,
		.suppress_bind_attrs = true,
	},
};

static int __init mr_init(void)
{
	if (!enable_readonly)
		return -EPERM;
	return platform_driver_register(&mr_driver);
}
static void __exit mr_exit(void)
{
	platform_driver_unregister(&mr_driver);
}
module_init(mr_init);
module_exit(mr_exit);
MODULE_DESCRIPTION("Myron read-only MCA telemetry and optional USB reporting");
MODULE_LICENSE("GPL");
