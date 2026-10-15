// SPDX-License-Identifier: GPL-2.0-only
/*
 * Myron FT3683 SPI touchscreen, direct IC-computed (TIC) contacts.
 * Protocol references: MeowArchMobile_sm8650AB_Touch cb907533e92d,
 * MiCode/vendor_xiaomi_proprietary_touch-driver c286ab85f498 (GPLv2).
 * Stock Myron protocol and DT were independently checked; see README.md.
 * No Xiaomi private ABI, bootloader commands, or firmware update path.
 */
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/input.h>
#include <linux/input/mt.h>
#include <linux/interrupt.h>
#include <linux/irq.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/pinctrl/consumer.h>
#include <linux/pm.h>
#include <linux/property.h>
#include <linux/regulator/consumer.h>
#include <linux/slab.h>
#include <linux/spi/spi.h>
#include <linux/workqueue.h>

#include "fts_myron_frame.h"

#define FTS_DATA_OFFSET 7
#define FTS_FRAME_LEN (FTS_MYRON_REPORT_LEN + FTS_DATA_OFFSET + 2)
#define FTS_REG_REPORT 0x01
#define FTS_REG_CHIP_H 0xa3
#define FTS_REG_CHIP_L 0x9f
#define FTS_REG_TIC 0x9e
#define FTS_RETRY_DELAY_MS 250
#define FTS_OFFLINE_DELAY_MS 1000

struct fts_myron {
	struct spi_device *spi;
	struct input_dev *input;
	struct gpio_desc *reset;
	struct regulator *avdd, *iovdd;
	struct pinctrl *pinctrl;
	struct pinctrl_state *pins_active;
	struct mutex lock;
	struct delayed_work recover;
	struct fts_myron_geometry geometry;
	u8 *tx, *rx, *report;
	bool irq_enabled, suspended, stopping;
	u16 active, chip_id;
	u32 valid_frames, faults, recoveries;
};

/* All controller I/O and input reporting run under ts->lock after probe. */
static int fts_transfer(struct fts_myron *ts, size_t len)
{
	struct spi_transfer transfer = {
		.tx_buf = ts->tx,
		.rx_buf = ts->rx,
		.len = len,
	};
	int ret;

	ret = spi_sync_transfer(ts->spi, &transfer, 1);
	/* CS must remain high between every attempt, including failed ones. */
	usleep_range(150, 200);
	if (ret) {
		usleep_range(2000, 2100);
		return ret;
	}
	return (ts->rx[3] & 0xa0) ? -EIO : 0;
}

static int fts_read(struct fts_myron *ts, u8 reg, u8 *dest, size_t len)
{
	size_t total = FTS_DATA_OFFSET + len + 2;
	unsigned int attempt;
	u16 crc;
	int ret = -EINVAL;

	if (!len || total > FTS_FRAME_LEN)
		return -EINVAL;
	for (attempt = 0; attempt < 3; attempt++) {
		memset(ts->tx, 0, total);
		memset(ts->rx, 0, total);
		ts->tx[0] = reg;
		ts->tx[1] = 0xa0;
		ts->tx[2] = len >> 8;
		ts->tx[3] = len;
		ret = fts_transfer(ts, total);
		if (ret)
			continue;
		crc = ts->rx[FTS_DATA_OFFSET + len] |
		      ((u16)ts->rx[FTS_DATA_OFFSET + len + 1] << 8);
		if (crc != fts_myron_crc(ts->rx + FTS_DATA_OFFSET, len)) {
			ret = -EBADMSG;
			continue;
		}
		memcpy(dest, ts->rx + FTS_DATA_OFFSET, len);
		return 0;
	}
	return ret;
}

/* The only write supported by this driver is the volatile TIC register. */
static int fts_write_tic(struct fts_myron *ts)
{
	unsigned int attempt;
	int ret = -EIO;

	for (attempt = 0; attempt < 3; attempt++) {
		memset(ts->tx, 0, 8);
		memset(ts->rx, 0, 8);
		ts->tx[0] = FTS_REG_TIC;
		ts->tx[3] = 1;
		/* ctrl=0 (write), three dummy bytes, payload=0 (TIC). */
		ret = fts_transfer(ts, 8);
		if (!ret)
			return 0;
	}
	return ret;
}

static int fts_identify(struct fts_myron *ts)
{
	u8 high, low;
	int ret;

	ret = fts_read(ts, FTS_REG_CHIP_H, &high, 1);
	if (ret)
		return ret;
	ret = fts_read(ts, FTS_REG_CHIP_L, &low, 1);
	if (ret)
		return ret;
	/* Stock type 0x92 primary application ID and its explicit CID alias. */
	if (!((high == 0x36 && low == 0x83) ||
	      (high == 0x56 && low == 0x72))) {
		dev_err_ratelimited(&ts->spi->dev,
				    "unsupported application ID %02x:%02x\n", high, low);
		return -ENODEV;
	}
	ts->chip_id = ((u16)high << 8) | low;
	return 0;
}

static int fts_set_tic(struct fts_myron *ts)
{
	unsigned int attempt;
	u8 value;
	int ret = -EIO;

	for (attempt = 0; attempt < 3; attempt++) {
		ret = fts_write_tic(ts);
		if (!ret) {
			ret = fts_read(ts, FTS_REG_TIC, &value, 1);
			if (!ret && value)
				ret = -EIO;
			if (!ret)
				return 0;
		}
		usleep_range(1000, 1100);
	}
	return ret;
}

static void fts_release_all(struct fts_myron *ts)
{
	unsigned int slot;

	if (!ts->active)
		return;
	for (slot = 0; slot < FTS_MYRON_POINTS; slot++) {
		input_mt_slot(ts->input, slot);
		input_mt_report_slot_state(ts->input, MT_TOOL_FINGER, false);
	}
	input_mt_sync_frame(ts->input);
	input_report_key(ts->input, BTN_TOUCH, 0);
	input_sync(ts->input);
	ts->active = 0;
}

static void fts_publish(struct fts_myron *ts, const struct fts_myron_frame *frame)
{
	unsigned int i;

	for (i = 0; i < frame->count; i++) {
		const struct fts_myron_contact *c = &frame->contacts[i];
		bool down = c->flag != 1;

		input_mt_slot(ts->input, c->id);
		input_mt_report_slot_state(ts->input, MT_TOOL_FINGER, down);
		if (!down)
			continue;
		input_report_abs(ts->input, ABS_MT_POSITION_X, c->x);
		input_report_abs(ts->input, ABS_MT_POSITION_Y, c->y);
		input_report_abs(ts->input, ABS_MT_PRESSURE, 0x3f);
		input_report_abs(ts->input, ABS_MT_TOUCH_MAJOR, c->major);
		input_report_abs(ts->input, ABS_MT_TOUCH_MINOR, c->minor);
	}
	/* DROP_UNUSED releases old contacts absent from this complete v2 frame. */
	input_mt_sync_frame(ts->input);
	input_report_key(ts->input, BTN_TOUCH, !!frame->active);
	input_sync(ts->input);
	ts->active = frame->active;
	ts->valid_frames++;
	if (ts->valid_frames == 1)
		dev_info(&ts->spi->dev, "first validated protocol-v2 input frame\n");
}

static void fts_mask_irq(struct fts_myron *ts)
{
	if (ts->irq_enabled) {
		ts->irq_enabled = false;
		disable_irq_nosync(ts->spi->irq);
	}
}

static void fts_unmask_irq(struct fts_myron *ts)
{
	if (!ts->irq_enabled && !ts->suspended && !ts->stopping) {
		ts->irq_enabled = true;
		enable_irq(ts->spi->irq);
	}
}

static irqreturn_t fts_irq_thread(int irq, void *data)
{
	struct fts_myron *ts = data;
	struct fts_myron_frame frame;
	int ret;

	mutex_lock(&ts->lock);
	if (!ts->irq_enabled || ts->suspended || ts->stopping)
		goto out;
	ret = fts_read(ts, FTS_REG_REPORT, ts->report, FTS_MYRON_REPORT_LEN);
	if (!ret)
		ret = fts_myron_decode(ts->report, FTS_MYRON_REPORT_LEN,
				       &ts->geometry, &frame);
	if (!ret) {
		fts_publish(ts, &frame);
	} else {
		ts->faults++;
		fts_mask_irq(ts);
		fts_release_all(ts);
		dev_warn_ratelimited(&ts->spi->dev,
			"frame error %d, IRQ paused for bounded recovery (faults=%u)\n",
			ret, ts->faults);
		mod_delayed_work(system_wq, &ts->recover,
				 msecs_to_jiffies(FTS_RETRY_DELAY_MS));
	}
out:
	mutex_unlock(&ts->lock);
	/* This is our dedicated IRQ even when the SPI transaction failed. */
	return IRQ_HANDLED;
}

static void fts_recover_work(struct work_struct *work)
{
	struct fts_myron *ts = container_of(to_delayed_work(work),
					   struct fts_myron, recover);
	struct fts_myron_frame frame;
	int ret;

	mutex_lock(&ts->lock);
	if (ts->suspended || ts->stopping)
		goto out;
	/* Never reset, enter a bootloader, or write to an unidentified chip. */
	ret = fts_identify(ts);
	if (!ret)
		ret = fts_set_tic(ts);
	if (!ret)
		ret = fts_read(ts, FTS_REG_REPORT, ts->report, FTS_MYRON_REPORT_LEN);
	if (ret) {
		dev_warn_ratelimited(&ts->spi->dev,
			"controller recovery pending: %d\n", ret);
		mod_delayed_work(system_wq, &ts->recover,
				 msecs_to_jiffies(FTS_OFFLINE_DELAY_MS));
		goto out;
	}
	/* Drain succeeded; a zero-event idle packet need not block IRQ restart. */
	ret = fts_myron_decode(ts->report, FTS_MYRON_REPORT_LEN,
			       &ts->geometry, &frame);
	if (!ret)
		fts_publish(ts, &frame);
	ts->recoveries++;
	fts_unmask_irq(ts);
out:
	mutex_unlock(&ts->lock);
}

static int fts_read_geometry(struct device *dev, struct fts_myron *ts)
{
	u32 coords[4], factor, count, width, height;
	int ret;

	ret = device_property_read_u32_array(dev, "focaltech,display-coords", coords, 4);
	if (ret)
		return ret;
	ret = device_property_read_u32(dev, "focaltech,super-resolution-factors", &factor);
	if (ret)
		return ret;
	ret = device_property_read_u32(dev, "focaltech,max-touch-number", &count);
	if (ret)
		return ret;
	ret = device_property_read_u32(dev, "focaltech,max-x", &width);
	if (ret)
		return ret;
	ret = device_property_read_u32(dev, "focaltech,max-y", &height);
	if (ret)
		return ret;
	/* This test driver deliberately accepts only the verified Myron layout. */
	if (coords[0] || coords[1] || coords[2] != 119999 || coords[3] != 260799 ||
	    factor != 100 || count != FTS_MYRON_POINTS || width != 1200 || height != 2608)
		return -EINVAL;
	ts->geometry = (struct fts_myron_geometry) {
		.xmin = coords[0], .ymin = coords[1],
		.xmax = coords[2], .ymax = coords[3], .factor = factor,
	};
	return 0;
}

static void fts_power_off(void *data)
{
	struct fts_myron *ts = data;

	/* Final power-off, not a reset pulse: keep reset low as rails fall. */
	gpiod_set_raw_value_cansleep(ts->reset, 0);
	usleep_range(2000, 2100);
	regulator_disable(ts->iovdd);
	regulator_disable(ts->avdd);
}

static int fts_power_on(struct fts_myron *ts)
{
	struct device *dev = &ts->spi->dev;
	int ret;

	ts->avdd = devm_regulator_get(dev, "avdd");
	if (IS_ERR(ts->avdd))
		return PTR_ERR(ts->avdd);
	ts->iovdd = devm_regulator_get(dev, "iovdd");
	if (IS_ERR(ts->iovdd))
		return PTR_ERR(ts->iovdd);
	/* Require real OF suppliers; do not silently use a dummy regulator. */
	if (!device_property_present(dev, "avdd-supply") ||
	    !device_property_present(dev, "iovdd-supply"))
		return -EINVAL;
	ret = gpiod_direction_output_raw(ts->reset, 0);
	if (ret)
		return ret;
	usleep_range(2000, 2100);
	ret = regulator_enable(ts->avdd);
	if (ret)
		return ret;
	ret = regulator_enable(ts->iovdd);
	if (ret) {
		regulator_disable(ts->avdd);
		return ret;
	}
	ret = devm_add_action_or_reset(dev, fts_power_off, ts);
	if (ret)
		return ret;
	usleep_range(2100, 2200);
	gpiod_set_raw_value_cansleep(ts->reset, 1);
	msleep(100);
	return 0;
}

static int fts_probe(struct spi_device *spi)
{
	struct device *dev = &spi->dev;
	struct fts_myron *ts;
	unsigned int attempt;
	int ret;

	ts = devm_kzalloc(dev, sizeof(*ts), GFP_KERNEL);
	if (!ts)
		return -ENOMEM;
	ts->spi = spi;
	mutex_init(&ts->lock);
	INIT_DELAYED_WORK(&ts->recover, fts_recover_work);
	spi_set_drvdata(spi, ts);
	ret = fts_read_geometry(dev, ts);
	if (ret)
		return dev_err_probe(dev, ret, "unverified Myron geometry/binding\n");
	if (spi->irq <= 0)
		return dev_err_probe(dev, -EINVAL, "missing DT interrupt\n");
	if (irq_get_trigger_type(spi->irq) != IRQ_TYPE_LEVEL_LOW)
		return dev_err_probe(dev, -EINVAL, "expected DT level-low IRQ\n");
	spi->mode = SPI_MODE_0;
	spi->bits_per_word = 8;
	if (!spi->max_speed_hz || spi->max_speed_hz > 15000000)
		return dev_err_probe(dev, -EINVAL, "unexpected SPI frequency\n");
	ret = spi_setup(spi);
	if (ret)
		return dev_err_probe(dev, ret, "SPI setup\n");
	if (spi_max_transfer_size(spi) < FTS_FRAME_LEN)
		return dev_err_probe(dev, -EMSGSIZE, "SPI needs %u-byte transactions\n",
				     FTS_FRAME_LEN);
	ts->tx = devm_kzalloc(dev, FTS_FRAME_LEN, GFP_KERNEL);
	ts->rx = devm_kzalloc(dev, FTS_FRAME_LEN, GFP_KERNEL);
	ts->report = devm_kzalloc(dev, FTS_MYRON_REPORT_LEN, GFP_KERNEL);
	if (!ts->tx || !ts->rx || !ts->report)
		return -ENOMEM;
	ts->pinctrl = devm_pinctrl_get(dev);
	if (IS_ERR(ts->pinctrl))
		return dev_err_probe(dev, PTR_ERR(ts->pinctrl), "pinctrl unavailable\n");
	ts->pins_active = pinctrl_lookup_state(ts->pinctrl, "pmx_ts_active");
	if (IS_ERR(ts->pins_active))
		return dev_err_probe(dev, PTR_ERR(ts->pins_active), "active pin state\n");
	ret = pinctrl_select_state(ts->pinctrl, ts->pins_active);
	if (ret)
		return dev_err_probe(dev, ret, "select active pins\n");
	/* Linux resolves con_id + '-gpio', matching focaltech,reset-gpio. */
	ts->reset = devm_gpiod_get(dev, "focaltech,reset", GPIOD_ASIS);
	if (IS_ERR(ts->reset))
		return dev_err_probe(dev, PTR_ERR(ts->reset), "vendor reset GPIO\n");
	ret = fts_power_on(ts);
	if (ret)
		return dev_err_probe(dev, ret, "power-on sequence\n");
	/* Allow normal application firmware to finish booting, reads only. */
	for (attempt = 0; attempt < 5; attempt++) {
		ret = fts_identify(ts);
		if (!ret)
			break;
		if (attempt < 4)
			msleep(200);
	}
	if (ret)
		return dev_err_probe(dev, ret, "application ID read/check\n");
	ret = fts_set_tic(ts);
	if (ret)
		return dev_err_probe(dev, ret, "TIC write/readback\n");
	ts->input = devm_input_allocate_device(dev);
	if (!ts->input)
		return -ENOMEM;
	ts->input->name = "FocalTech Myron Touchscreen";
	ts->input->phys = "focaltech_myron/input0";
	ts->input->id.bustype = BUS_SPI;
	input_set_abs_params(ts->input, ABS_MT_POSITION_X, 0, ts->geometry.xmax, 0, 0);
	input_set_abs_params(ts->input, ABS_MT_POSITION_Y, 0, ts->geometry.ymax, 0, 0);
	input_set_abs_params(ts->input, ABS_MT_PRESSURE, 0, 255, 0, 0);
	input_set_abs_params(ts->input, ABS_MT_TOUCH_MAJOR, 0, 255, 0, 0);
	input_set_abs_params(ts->input, ABS_MT_TOUCH_MINOR, 0, 255, 0, 0);
	input_set_capability(ts->input, EV_KEY, BTN_TOUCH);
	ret = input_mt_init_slots(ts->input, FTS_MYRON_POINTS,
				  INPUT_MT_DIRECT | INPUT_MT_DROP_UNUSED);
	if (ret)
		return dev_err_probe(dev, ret, "multitouch slots\n");
	ret = input_register_device(ts->input);
	if (ret)
		return dev_err_probe(dev, ret, "input registration\n");
	/* Keep masked until registration completes. Preserve DT level polarity. */
	ret = devm_request_threaded_irq(dev, spi->irq, NULL, fts_irq_thread,
			 IRQF_ONESHOT | IRQF_NO_AUTOEN | IRQF_TRIGGER_LOW,
			 "focaltech_myron", ts);
	if (ret)
		return dev_err_probe(dev, ret, "threaded IRQ\n");
	mutex_lock(&ts->lock);
	fts_unmask_irq(ts);
	mutex_unlock(&ts->lock);
	dev_info(dev,
		"Myron TIC ready: app=%04x, 3120-byte reads, 10 slots, 119999x260799, factor 100\n",
		ts->chip_id);
	return 0;
}

static void fts_stop(struct spi_device *spi)
{
	struct fts_myron *ts = spi_get_drvdata(spi);

	mutex_lock(&ts->lock);
	ts->stopping = true;
	fts_mask_irq(ts);
	mutex_unlock(&ts->lock);
	synchronize_irq(spi->irq);
	cancel_delayed_work_sync(&ts->recover);
	mutex_lock(&ts->lock);
	fts_release_all(ts);
	mutex_unlock(&ts->lock);
}

/*
 * Test-build PM: keep power and TIC mode. Mask the dedicated IRQ during
 * system sleep and revalidate on resume. No display notifier, gesture wake,
 * warm reset, or speculative sleep-register sequence is introduced.
 */
static int fts_suspend(struct device *dev)
{
	struct fts_myron *ts = spi_get_drvdata(to_spi_device(dev));

	mutex_lock(&ts->lock);
	ts->suspended = true;
	fts_mask_irq(ts);
	mutex_unlock(&ts->lock);
	synchronize_irq(ts->spi->irq);
	cancel_delayed_work_sync(&ts->recover);
	mutex_lock(&ts->lock);
	fts_release_all(ts);
	mutex_unlock(&ts->lock);
	return 0;
}

static int fts_resume(struct device *dev)
{
	struct fts_myron *ts = spi_get_drvdata(to_spi_device(dev));
	int ret;

	mutex_lock(&ts->lock);
	ts->suspended = false;
	ret = pinctrl_select_state(ts->pinctrl, ts->pins_active);
	if (!ret)
		ret = fts_identify(ts);
	if (!ret)
		ret = fts_set_tic(ts);
	if (!ret)
		fts_unmask_irq(ts);
	else
		mod_delayed_work(system_wq, &ts->recover,
				 msecs_to_jiffies(FTS_OFFLINE_DELAY_MS));
	mutex_unlock(&ts->lock);
	if (ret)
		dev_err(dev, "resume failed, delayed recovery scheduled: %d\n", ret);
	return ret;
}

static DEFINE_SIMPLE_DEV_PM_OPS(fts_pm_ops, fts_suspend, fts_resume);

static const struct of_device_id fts_of_ids[] = {
	{ .compatible = "focal,touch-spi" },
	{ }
};
MODULE_DEVICE_TABLE(of, fts_of_ids);

static const struct spi_device_id fts_spi_ids[] = {
	{ "touch-spi" },
	{ }
};
MODULE_DEVICE_TABLE(spi, fts_spi_ids);

static struct spi_driver fts_driver = {
	.driver = {
		.name = "focaltech_myron",
		.of_match_table = fts_of_ids,
		.pm = pm_sleep_ptr(&fts_pm_ops),
	},
	.id_table = fts_spi_ids,
	.probe = fts_probe,
	.remove = fts_stop,
	.shutdown = fts_stop,
};
module_spi_driver(fts_driver);

MODULE_DESCRIPTION("Myron FT3683 direct SPI multitouch test driver");
MODULE_LICENSE("GPL");
MODULE_VERSION("r58-1");
