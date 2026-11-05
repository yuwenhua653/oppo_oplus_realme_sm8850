/*
// SPDX-License-Identifier: GPL-2.0
 * mca_battery_psy.c
 *
 * mca battery psy driver
 *
 * Copyright (c) 2023-2023 Xiaomi Technologies Co., Ltd.
 *
 * This software is licensed under the terms of the GNU General Public
 * License version 2, as published by the Free Software Foundation, and
 * may be copied, distributed, and modified under those terms.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 */
#include <linux/slab.h>
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/string.h>
#include <linux/delay.h>
#include <linux/device.h>
#include <linux/init.h>
#include <linux/of.h>
#include <linux/of_device.h>
#include <linux/power_supply.h>
#include <linux/thermal.h>
#include <linux/version.h>
#include <mca/common/mca_log.h>
#include <mca/platform/platform_buckchg_class.h>
#include <mca/strategy/strategy_fg_class.h>
#include "inc/mca_battery_psy.h"

#ifndef MCA_LOG_TAG
#define MCA_LOG_TAG "mca_battery_psy"
#endif

static bool battery_psy_is_wls_available(struct batt_psy_info *info)
{
	if (!info->wls_psy)
		info->wls_psy = power_supply_get_by_name("wireless");

	if (!info->wls_psy)
		return false;

	return true;
}

static bool battery_psy_is_usb_available(struct batt_psy_info *info)
{
	if (!info->usb_psy)
		info->usb_psy = power_supply_get_by_name("usb");

	if (!info->usb_psy)
		return false;

	return true;
}

static int get_prop_batt_health(struct batt_psy_info *info,
				union power_supply_propval *val)
{
	return strategy_class_fg_get_health(&val->intval);
}

static int get_prop_batt_capacity_level(struct batt_psy_info *info,
					union power_supply_propval *val)
{
	union power_supply_propval pval;
	int ret;

	ret = power_supply_get_property(info->batt_psy,
				       POWER_SUPPLY_PROP_CAPACITY, &pval);
	if (ret)
		return ret;
	if (pval.intval < 0 || pval.intval > 100)
		return -ERANGE;

	if (pval.intval == 0) {
		val->intval = POWER_SUPPLY_CAPACITY_LEVEL_CRITICAL;
		mca_log_info(
			"Trigger Android shutdown for CAPACITY_LEVEL_CRITICAL\n");
	} else if (pval.intval > 0 && pval.intval <= 20)
		val->intval = POWER_SUPPLY_CAPACITY_LEVEL_LOW;
	else if (pval.intval > 20 && pval.intval <= 80)
		val->intval = POWER_SUPPLY_CAPACITY_LEVEL_NORMAL;
	else if (pval.intval > 80 && pval.intval <= 99)
		val->intval = POWER_SUPPLY_CAPACITY_LEVEL_HIGH;
	else if (pval.intval == 100)
		val->intval = POWER_SUPPLY_CAPACITY_LEVEL_FULL;

	return 0;
}

static enum power_supply_property batt_psy_props[] = {
	POWER_SUPPLY_PROP_STATUS,
	POWER_SUPPLY_PROP_HEALTH,
	POWER_SUPPLY_PROP_PRESENT,
	POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT,
	POWER_SUPPLY_PROP_CHARGE_TYPE,
	POWER_SUPPLY_PROP_CAPACITY,
	POWER_SUPPLY_PROP_CAPACITY_LEVEL,
	POWER_SUPPLY_PROP_CHARGE_CONTROL_LIMIT,
	POWER_SUPPLY_PROP_CHARGE_CONTROL_LIMIT_MAX,
	POWER_SUPPLY_PROP_VOLTAGE_NOW,
	POWER_SUPPLY_PROP_VOLTAGE_MAX,
	POWER_SUPPLY_PROP_CURRENT_NOW,
	POWER_SUPPLY_PROP_CONSTANT_CHARGE_CURRENT_MAX,
	POWER_SUPPLY_PROP_CONSTANT_CHARGE_CURRENT,
	POWER_SUPPLY_PROP_CHARGE_TERM_CURRENT,
	POWER_SUPPLY_PROP_TEMP,
	POWER_SUPPLY_PROP_TECHNOLOGY,
	POWER_SUPPLY_PROP_CHARGE_COUNTER,
	POWER_SUPPLY_PROP_CYCLE_COUNT,
	POWER_SUPPLY_PROP_CHARGE_FULL,
	POWER_SUPPLY_PROP_CHARGE_FULL_DESIGN,
	POWER_SUPPLY_PROP_MODEL_NAME,
	POWER_SUPPLY_PROP_TIME_TO_FULL_NOW,
	POWER_SUPPLY_PROP_TIME_TO_EMPTY_NOW,
	POWER_SUPPLY_PROP_VOLTAGE_OCV,
};

#define BATT_SOC_DEFAULT 15
#define BATT_VOLTAGE_DEFAULT 3700000
#define BATT_CURRENT_DEFAULT -500000
#define BATT_TEMP_DEFAULT 250

static int fake_batt_psy_get_prop(struct batt_psy_info *info,
				  enum power_supply_property psp,
				  union power_supply_propval *pval)
{
	int main_chg_type = 0;
	int ret;

	switch (psp) {
	case POWER_SUPPLY_PROP_PRESENT:
		pval->intval = 1;
		break;
	case POWER_SUPPLY_PROP_STATUS:
		if (battery_psy_is_usb_available(info)) {
			ret = power_supply_get_property(
				info->usb_psy, POWER_SUPPLY_PROP_ONLINE, pval);
			if (ret)
				return ret;
			pval->intval = pval->intval ?
					       POWER_SUPPLY_STATUS_CHARGING :
					       POWER_SUPPLY_STATUS_DISCHARGING;
		} else
			pval->intval = POWER_SUPPLY_STATUS_UNKNOWN;
		break;
	case POWER_SUPPLY_PROP_CHARGE_TYPE:
		ret = platform_class_buckchg_ops_get_chg_type(MAIN_BUCK_CHARGER,
							    &main_chg_type);
		if (ret)
			return ret;
		pval->intval = main_chg_type;
		break;
	case POWER_SUPPLY_PROP_CAPACITY_LEVEL:
		pval->intval = POWER_SUPPLY_CAPACITY_LEVEL_LOW;
		break;
	case POWER_SUPPLY_PROP_CAPACITY:
		pval->intval = BATT_SOC_DEFAULT;
		break;
	case POWER_SUPPLY_PROP_VOLTAGE_NOW:
	case POWER_SUPPLY_PROP_VOLTAGE_OCV:
		pval->intval = BATT_VOLTAGE_DEFAULT;
		break;
	case POWER_SUPPLY_PROP_CURRENT_NOW:
		pval->intval = BATT_CURRENT_DEFAULT;
		break;
	case POWER_SUPPLY_PROP_TEMP:
		pval->intval = BATT_TEMP_DEFAULT;
		break;
	default:
		mca_log_info("Get prop %d is not supported in battery\n", psp);
		return -ENODATA;
	}

	return 0;
}

static int batt_psy_get_prop(struct power_supply *psy,
			     enum power_supply_property psp,
			     union power_supply_propval *result)
{
	struct batt_psy_info *info = power_supply_get_drvdata(psy);
	union power_supply_propval value = {};
	union power_supply_propval *pval = &value;
	int rc = 0;
	int uisoc;
	int main_chg_type = 0;
	bool charging_done;

	if (!info || !info->batt_psy)
		return -ENODEV;

	/* The existing explicit factory mode is not an error fallback. */
	if (info->fake_power) {
		rc = fake_batt_psy_get_prop(info, psp, pval);
		if (!rc)
			*result = value;
		return rc;
	}

	/* The class returns -1 when no strategy has registered its ops. */
	if (strategy_class_fg_ops_is_init_ok() <= 0)
		return -ENODATA;

	if (!battery_psy_is_usb_available(info) ||
	    !battery_psy_is_wls_available(info))
		return -ENODEV;

	switch (psp) {
	case POWER_SUPPLY_PROP_STATUS:
		/* mishow app needs a discharging status while input is suspended. */
		if (!info->input_suppend_voter)
			info->input_suppend_voter =
				mca_find_votable("input_suspend");
		if (info->input_suppend_voter &&
		    mca_get_client_vote(info->input_suppend_voter, "micharge")) {
			pval->intval = POWER_SUPPLY_STATUS_DISCHARGING;
			break;
		}

		rc = power_supply_get_property(info->usb_psy,
					       POWER_SUPPLY_PROP_ONLINE, pval);
		if (rc)
			break;
		if (!pval->intval) {
			rc = power_supply_get_property(info->wls_psy,
						       POWER_SUPPLY_PROP_ONLINE, pval);
			if (rc)
				break;
		}
		if (!pval->intval) {
			pval->intval = POWER_SUPPLY_STATUS_DISCHARGING;
			break;
		}
		uisoc = strategy_class_fg_ops_get_soc();
		if (uisoc < 0) {
			rc = uisoc;
			break;
		}
		if (uisoc > 100) {
			rc = -ERANGE;
			break;
		}
		charging_done = strategy_class_fg_ops_get_charging_done();
		pval->intval = uisoc == 100 && charging_done ?
			POWER_SUPPLY_STATUS_FULL : POWER_SUPPLY_STATUS_CHARGING;
		break;
	case POWER_SUPPLY_PROP_HEALTH:
		rc = get_prop_batt_health(info, pval);
		break;
	case POWER_SUPPLY_PROP_PRESENT:
		pval->intval = 1;
		break;
	case POWER_SUPPLY_PROP_CHARGE_TYPE:
		rc = platform_class_buckchg_ops_get_chg_type(MAIN_BUCK_CHARGER,
							    &main_chg_type);
		if (!rc)
			pval->intval = main_chg_type;
		break;
	case POWER_SUPPLY_PROP_CAPACITY_LEVEL:
		rc = get_prop_batt_capacity_level(info, pval);
		break;
	case POWER_SUPPLY_PROP_CAPACITY:
		uisoc = strategy_class_fg_ops_get_soc();
		if (uisoc < 0)
			rc = uisoc;
		else if (uisoc > 100)
			rc = -ERANGE;
		else
			pval->intval = uisoc;
		break;
	case POWER_SUPPLY_PROP_CHARGE_CONTROL_LIMIT_MAX:
		pval->intval = 16;
		break;
	case POWER_SUPPLY_PROP_VOLTAGE_NOW:
	case POWER_SUPPLY_PROP_VOLTAGE_OCV:
		rc = strategy_class_fg_ops_get_voltage(&pval->intval);
		if (!rc)
			pval->intval *= 1000;
		break;
	case POWER_SUPPLY_PROP_VOLTAGE_MAX:
		rc = power_supply_get_property(info->usb_psy, psp, pval);
		break;
	case POWER_SUPPLY_PROP_CURRENT_NOW:
		rc = strategy_class_fg_ops_get_current(&pval->intval);
		break;
	case POWER_SUPPLY_PROP_CONSTANT_CHARGE_CURRENT_MAX:
		rc = power_supply_get_property(
			info->usb_psy, POWER_SUPPLY_PROP_CURRENT_MAX, pval);
		break;
	case POWER_SUPPLY_PROP_TEMP:
		rc = strategy_class_fg_ops_get_temperature(&pval->intval);
		break;
	case POWER_SUPPLY_PROP_TECHNOLOGY:
		pval->intval = POWER_SUPPLY_TECHNOLOGY_LIPO;
		break;
	case POWER_SUPPLY_PROP_CHARGE_COUNTER:
		rc = strategy_class_fg_get_rm(&pval->intval);
		break;
	case POWER_SUPPLY_PROP_CYCLE_COUNT:
		rc = strategy_class_fg_ops_get_cyclecount(&pval->intval);
		break;
	case POWER_SUPPLY_PROP_CHARGE_FULL:
		rc = strategy_class_fg_get_fcc(&pval->intval);
		break;
	case POWER_SUPPLY_PROP_CHARGE_FULL_DESIGN:
		rc = strategy_class_fg_get_dc(&pval->intval);
		break;
	case POWER_SUPPLY_PROP_MODEL_NAME:
		rc = strategy_class_fg_get_model_name(&pval->strval);
		break;
	/* Advertised properties without a value must be skippable by uevent. */
	case POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT:
	case POWER_SUPPLY_PROP_CHARGE_CONTROL_LIMIT:
	case POWER_SUPPLY_PROP_CONSTANT_CHARGE_CURRENT:
	case POWER_SUPPLY_PROP_CHARGE_TERM_CURRENT:
	case POWER_SUPPLY_PROP_TIME_TO_FULL_NOW:
	case POWER_SUPPLY_PROP_TIME_TO_EMPTY_NOW:
		rc = -ENODATA;
		break;
	default:
		rc = -EINVAL;
		break;
	}

	if (rc) {
		mca_log_err("Couldn't get prop %d rc = %d\n", psp, rc);
		return rc;
	}

	/* Publish a value only after every provider needed for it succeeded. */
	*result = value;
	return 0;
}

static int batt_psy_set_prop(struct power_supply *psy,
			     enum power_supply_property psp,
			     const union power_supply_propval *val)
{
	struct batt_psy_info *info = power_supply_get_drvdata(psy);
	int rc = 0;

	if (!battery_psy_is_usb_available(info)) {
		mca_log_err("get usb psy fail\n");
		return 0;
	}

	switch (psp) {
	case POWER_SUPPLY_PROP_CHARGE_CONTROL_LIMIT:
		break;
	case POWER_SUPPLY_PROP_CAPACITY:
		break;
	case POWER_SUPPLY_PROP_TEMP:
		break;
	default:
		mca_log_err("set prop %d is not supported in battery\n", psp);
		rc = -EINVAL;
		break;
	}

	if (rc < 0) {
		mca_log_err("Couldn't set prop %d rc = %d\n", psp, rc);
		return -ENODATA;
	}

	return 0;
}

static int batt_psy_prop_is_writeable(struct power_supply *psy,
				      enum power_supply_property psp)
{
	switch (psp) {
	case POWER_SUPPLY_PROP_CHARGE_CONTROL_LIMIT:
	case POWER_SUPPLY_PROP_CAPACITY:
	case POWER_SUPPLY_PROP_TEMP:
		return 1;
	default:
		break;
	}

	return 0;
}

static const struct power_supply_desc _batt_psy_desc = {
	.name = "battery",
	.type = POWER_SUPPLY_TYPE_BATTERY,
	.properties = batt_psy_props,
	.num_properties = ARRAY_SIZE(batt_psy_props),
	.get_property = batt_psy_get_prop,
	.set_property = batt_psy_set_prop,
	.property_is_writeable = batt_psy_prop_is_writeable,
};

static int power_supply_read_temp(struct thermal_zone_device *tzd, int *temp)
{
	static int last_temp;
	int t = 0;
	int ret;

	ret = strategy_class_fg_ops_get_thermal_temperature(&t);
	if (ret)
		return ret;
	*temp = t * 100;
	if (t != last_temp) {
		last_temp = t;
		pr_info("batt_thermal temp:%d\n", t);
	}

	return 0;
}

static struct thermal_zone_device_ops psy_tzd_ops = {
	.get_temp = power_supply_read_temp,
};

static int battery_psy_init(struct batt_psy_info *info)
{
	struct power_supply_config batt_cfg = {};
	struct thermal_zone_params tzp = {};
	int rc = 0;

	batt_cfg.drv_data = info;
	batt_cfg.of_node = info->dev->of_node;
	info->batt_psy = devm_power_supply_register(info->dev, &_batt_psy_desc,
						    &batt_cfg);
	if (IS_ERR(info->batt_psy)) {
		mca_log_err("Couldn't register battery power supply\n");
		return PTR_ERR(info->batt_psy);
	}

	info->tzd = thermal_tripless_zone_device_register(
			info->batt_psy->desc->name, info->batt_psy, &psy_tzd_ops, &tzp);
	if (IS_ERR(info->tzd))
		return PTR_ERR(info->tzd);

	return rc;
}

static int business_battery_dump_log_head(void *data, char *buf, int size)
{
	return snprintf(buf, size,
			"ChargeStatus uiSoc uiSoh F_Volt F_Curr  F_temp ");
}

static int business_battery_dump_log_context(void *data, char *buf, int size)
{
	struct batt_psy_info *info = data;
	union power_supply_propval value;
	int status = -1, soc = -1, volt = -1, curr = -1, temp = -1;
	int soh = -1;

	if (info && info->batt_psy) {
		if (!batt_psy_get_prop(info->batt_psy, POWER_SUPPLY_PROP_STATUS,
				       &value))
			status = value.intval;
		if (!batt_psy_get_prop(info->batt_psy, POWER_SUPPLY_PROP_CAPACITY,
				       &value))
			soc = value.intval;
		if (!batt_psy_get_prop(info->batt_psy, POWER_SUPPLY_PROP_VOLTAGE_NOW,
				       &value))
			volt = value.intval / 1000;
		if (!batt_psy_get_prop(info->batt_psy, POWER_SUPPLY_PROP_CURRENT_NOW,
				       &value))
			curr = value.intval / 1000;
		if (!batt_psy_get_prop(info->batt_psy, POWER_SUPPLY_PROP_TEMP, &value))
			temp = value.intval;
	}

	return snprintf(buf, size, "%-13d%-6d%-6d%-7d%-8d%-7d",
			status, soc, soh, volt, curr, temp);
}

static struct mca_log_charge_log_ops g_business_battery_log_ops = {
	.dump_log_head = business_battery_dump_log_head,
	.dump_log_context = business_battery_dump_log_context,
};

struct batt_psy_info *business_battery_psy_init(struct device *dev)
{
	struct batt_psy_info *info;
	int rc = 0;

	info = devm_kzalloc(dev, sizeof(*info), GFP_KERNEL);
	if (!info)
		return NULL;

	info->dev = dev;
	rc = battery_psy_init(info);
	if (rc < 0) {
		mca_log_err("Couldn't init battery psy rc=%d\n", rc);
		return NULL;
	}

	info->usb_psy = power_supply_get_by_name("usb");
	if (!info->usb_psy)
		mca_log_err("get usb psy fail\n");

	info->wls_psy = power_supply_get_by_name("wireless");
	if (!info->wls_psy)
		mca_log_err("get wls psy fail\n");

	mca_log_charge_log_register(MCA_CHARGE_LOG_ID_BATTERY_INFO,
				    &g_business_battery_log_ops, info);

	return info;
}

void business_battery_psy_deinit(struct batt_psy_info *info)
{
    if (!info)
        return;
    mca_log_charge_log_register(MCA_CHARGE_LOG_ID_BATTERY_INFO, NULL, NULL);
    if (!IS_ERR_OR_NULL(info->tzd)) {
        thermal_zone_device_unregister(info->tzd);
        info->tzd = NULL;
    }
    if (info->usb_psy) {
        power_supply_put(info->usb_psy);
        info->usb_psy = NULL;
    }
    if (info->wls_psy) {
        power_supply_put(info->wls_psy);
        info->wls_psy = NULL;
    }
    /* batt_psy is owned by devm_power_supply_register(). */
}

/*
void business_battery_psy_event_process(struct batt_psy_info *info)
{
	if (!info)
		return;

	power_supply_changed(info->batt_psy);
}
*/
