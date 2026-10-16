// SPDX-License-Identifier: GPL-2.0
/*
 * mca_platform_fg_ic_ops.c
 *
 * mca platform fuelgauge ic operation driver
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
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/mutex.h>
#include <linux/srcu.h>
#include <linux/errno.h>
#include <linux/string.h>
#include <mca/platform/platform_fg_ic_ops.h>

struct fuelguage_info {
	void *data;
	struct fuelguage_ic_ops *ops;
	size_t ops_size;
};
static struct fuelguage_info __rcu *g_fg_ic_ops[FG_IC_MAX];
static DEFINE_MUTEX(platform_fg_lock);
DEFINE_STATIC_SRCU(platform_fg_srcu);

/* Atomically publish the ops/data pair; wait before old provider reclamation.
 * Register/unregister must not run from inside a dispatched FG callback.
 */
static int platform_fg_ic_ops_register_size(unsigned int ic_role, void *data,
					    struct fuelguage_ic_ops *ops, size_t ops_size)
{
	struct fuelguage_info *entry, *old;

	if (ic_role >= FG_IC_MAX || !data || !ops)
		return -EOPNOTSUPP;
	entry = kmalloc(sizeof(*entry), GFP_KERNEL);
	if (!entry)
		return -ENOMEM;
	entry->data = data;
	entry->ops = ops;
	entry->ops_size = ops_size;
	mutex_lock(&platform_fg_lock);
	old = rcu_replace_pointer(g_fg_ic_ops[ic_role], entry,
				  lockdep_is_held(&platform_fg_lock));
	mutex_unlock(&platform_fg_lock);
	synchronize_srcu(&platform_fg_srcu);
	kfree(old);
	return 0;
}
int platform_fg_ic_ops_register(unsigned int ic_role, void *data,
				struct fuelguage_ic_ops *ops)
{
	return platform_fg_ic_ops_register_size(ic_role, data, ops,
					       MCA_FG_LEGACY_OPS_SIZE);
}
EXPORT_SYMBOL(platform_fg_ic_ops_register);

int platform_fg_ic_ops_register_v2(unsigned int ic_role, void *data,
				 struct fuelguage_ic_ops *ops, size_t ops_size)
{
	if (ops_size != sizeof(*ops))
		return -EINVAL;
	return platform_fg_ic_ops_register_size(ic_role, data, ops, ops_size);
}
EXPORT_SYMBOL(platform_fg_ic_ops_register_v2);

int platform_fg_ic_ops_unregister(unsigned int ic_role, void *data,
				  struct fuelguage_ic_ops *ops)
{
	struct fuelguage_info *old;

	if (ic_role >= FG_IC_MAX || !data || !ops)
		return -EINVAL;
	mutex_lock(&platform_fg_lock);
	old = rcu_dereference_protected(g_fg_ic_ops[ic_role],
				       lockdep_is_held(&platform_fg_lock));
	if (!old || old->ops != ops || old->data != data) {
		mutex_unlock(&platform_fg_lock);
		/* A replacement can have detached a still-running old provider. */
		synchronize_srcu(&platform_fg_srcu);
		return -ENOENT;
	}
	RCU_INIT_POINTER(g_fg_ic_ops[ic_role], NULL);
	mutex_unlock(&platform_fg_lock);
	synchronize_srcu(&platform_fg_srcu);
	kfree(old);
	return 0;
}
EXPORT_SYMBOL(platform_fg_ic_ops_unregister);

int platform_fg_ops_probe_ok(unsigned int ic_role, bool *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_probe_ok)
		ret = info->ops->fg_ic_probe_ok(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_probe_ok);

int platform_fg_ops_get_batt_info(unsigned int ic_role, void *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_batt_info)
		ret = info->ops->fg_ic_get_batt_info(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_batt_info);

void platform_fg_ops_get_batt_abnormal_info(unsigned int ic_role, void *value)
{
	struct fuelguage_info *info;
	int idx;

	if (ic_role >= FG_IC_MAX)
		return;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_batt_abnormal_info)
		info->ops->fg_ic_get_batt_abnormal_info(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
}
EXPORT_SYMBOL(platform_fg_ops_get_batt_abnormal_info);

int platform_fg_ops_get_soc(unsigned int ic_role)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_soc)
		ret = info->ops->fg_ic_get_soc(info->data);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_soc);

int platform_fg_ops_get_rsoc(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_rsoc)
		ret = info->ops->fg_ic_get_rsoc(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_rsoc);

int platform_fg_ops_get_curr(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_curr)
		ret = info->ops->fg_ic_get_curr(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_curr);

int platform_fg_ops_set_verify_digest(unsigned int ic_role, char *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_set_verify_digest)
		ret = info->ops->fg_ic_set_verify_digest(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_set_verify_digest);

int platform_fg_ops_get_verify_digest(unsigned int ic_role, char *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_verify_digest)
		ret = info->ops->fg_ic_get_verify_digest(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_verify_digest);

int platform_fg_ops_set_authentic(unsigned int ic_role, int value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_set_authentic)
		ret = info->ops->fg_ic_set_authentic(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_set_authentic);

int platform_fg_ops_get_authentic(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_authentic)
		ret = info->ops->fg_ic_get_authentic(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_authentic);

int platform_fg_ops_get_error_state(unsigned int ic_role, bool *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_error_state)
		ret = info->ops->fg_ic_get_error_state(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_error_state);

int platform_fg_ops_get_volt(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_volt)
		ret = info->ops->fg_ic_get_volt(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_volt);

int platform_fg_ops_set_temp(unsigned int ic_role, int value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_set_temp)
		ret = info->ops->fg_ic_set_temp(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_set_temp);

int platform_fg_ops_get_temp(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_temp)
		ret = info->ops->fg_ic_get_temp(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_temp);

int platform_fg_ops_get_original_temp(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_original_temp)
		ret = info->ops->fg_ic_get_original_temp(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_original_temp);

int platform_fg_ops_set_iterm(unsigned int ic_role, int value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_set_iterm)
		ret = info->ops->fg_ic_set_iterm(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_set_iterm);

int platform_fg_ops_get_charge_status(unsigned int ic_role)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_charge_status)
		ret = info->ops->fg_ic_get_charge_status(info->data);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_charge_status);

int platform_fg_ops_get_rm(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_rm)
		ret = info->ops->fg_ic_get_rm(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_rm);

int platform_fg_ops_get_isc_alert_level(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_isc_alert_level)
		ret = info->ops->fg_ic_get_isc_alert_level(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_isc_alert_level);

int platform_fg_ops_get_soa_alert_level(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_soa_alert_level)
		ret = info->ops->fg_ic_get_soa_alert_level(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_soa_alert_level);

int platform_fg_ops_get_fastcharge(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_fastcharge)
		ret = info->ops->fg_ic_get_fastcharge(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_fastcharge);

int platform_fg_ops_set_fastcharge(unsigned int ic_role, bool value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_set_fastcharge)
		ret = info->ops->fg_ic_set_fastcharge(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_set_fastcharge);

int platform_fg_ops_get_chg_vol(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_chg_vol)
		ret = info->ops->fg_ic_get_chg_vol(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_chg_vol);

int platform_fg_ops_get_chip_ok(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_chip_ok)
		ret = info->ops->fg_ic_get_chip_ok(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_chip_ok);

int platform_fg_ops_get_cyclecount(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_cyclecount)
		ret = info->ops->fg_ic_get_cyclecount(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_cyclecount);

int platform_fg_ops_get_tte(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_tte)
		ret = info->ops->fg_ic_get_tte(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_tte);

int platform_fg_ops_get_ttf(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_ttf)
		ret = info->ops->fg_ic_get_ttf(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_ttf);

int platform_fg_ops_get_fcc(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_fcc)
		ret = info->ops->fg_ic_get_fcc(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_fcc);

int platform_fg_ops_get_full_design(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_full_design)
		ret = info->ops->fg_ic_get_full_design(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_full_design);

int platform_fg_ops_get_soh(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_soh)
		ret = info->ops->fg_ic_get_soh(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_soh);

int platform_fg_ops_get_temp_max(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_temp_max)
		ret = info->ops->fg_ic_get_temp_max(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_temp_max);

int platform_fg_ops_get_time_ot(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_time_ot)
		ret = info->ops->fg_ic_get_time_ot(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_time_ot);

int platform_fg_ops_get_batt_cell_info(unsigned int ic_role, const char **value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_batt_cell_info)
		ret = info->ops->fg_ic_get_batt_cell_info(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_batt_cell_info);

int platform_fg_ops_get_cutoff_voltage(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_cutoff_voltage)
		ret = info->ops->fg_ic_get_cutoff_voltage(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_cutoff_voltage);

int platform_fg_ops_set_cutoff_voltage(unsigned int ic_role, int value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_set_cutoff_voltage)
		ret = info->ops->fg_ic_set_cutoff_voltage(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_set_cutoff_voltage);

int platform_fg_ops_get_dod_count(unsigned int ic_role)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_dod_count)
		ret = info->ops->fg_ic_get_dod_count(info->data);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_dod_count);

int platform_fg_ops_get_count_level1(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_count_level1)
		ret = info->ops->fg_ic_get_count_level1(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_count_level1);

int platform_fg_ops_get_count_level2(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_count_level2)
		ret = info->ops->fg_ic_get_count_level2(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_count_level2);

int platform_fg_ops_get_count_level3(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_count_level3)
		ret = info->ops->fg_ic_get_count_level3(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_count_level3);

int platform_fg_ops_get_vsiloss(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_vsiloss)
		ret = info->ops->fg_ic_get_vsiloss(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_vsiloss);

int platform_fg_ops_get_iaver(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_iaver)
		ret = info->ops->fg_ic_get_iaver(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_iaver);

int platform_fg_ops_get_count_lowtemp(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_count_lowtemp)
		ret = info->ops->fg_ic_get_count_lowtemp(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_count_lowtemp);

int platform_fg_ops_set_clear_count_data(unsigned int ic_role)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_set_clear_count_data)
		ret = info->ops->fg_ic_set_clear_count_data(info->data);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_set_clear_count_data);

int platform_fg_ops_get_adapt_power(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_adapt_power)
		ret = info->ops->fg_ic_get_adapt_power(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_adapt_power);

int platform_fg_ops_get_aged_flag(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_aged_flag)
		ret = info->ops->fg_ic_get_aged_flag(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_aged_flag);

int platform_fg_ops_get_raw_soc(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_raw_soc)
		ret = info->ops->fg_ic_get_raw_soc(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_raw_soc);

int platform_fg_ops_get_real_supplement_energy(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_real_supplement_energy)
		ret = info->ops->fg_ic_get_real_supplement_energy(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_real_supplement_energy);

int platform_fg_ops_get_calibration_ffc_iterm(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_calibration_ffc_iterm)
		ret = info->ops->fg_ic_get_calibration_ffc_iterm(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_calibration_ffc_iterm);

int platform_fg_ops_get_calibration_charge_energy(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_calibration_charge_energy)
		ret = info->ops->fg_ic_get_calibration_charge_energy(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_calibration_charge_energy);

void platform_fg_ops_fl4p0_enable_check(unsigned int ic_role)
{
	struct fuelguage_info *info;
	int idx;

	if (ic_role >= FG_IC_MAX)
		return;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_fl4p0_enable_check)
		info->ops->fg_ic_fl4p0_enable_check(info->data);
	srcu_read_unlock(&platform_fg_srcu, idx);
}
EXPORT_SYMBOL(platform_fg_ops_fl4p0_enable_check);

void platform_fg_ops_update_fw(unsigned int ic_role)
{
	struct fuelguage_info *info;
	int idx;

	if (ic_role >= FG_IC_MAX)
		return;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_update_fw)
		info->ops->fg_ic_update_fw(info->data);
	srcu_read_unlock(&platform_fg_srcu, idx);
}
EXPORT_SYMBOL(platform_fg_ops_update_fw);

int platform_fg_ops_get_device_name(unsigned int ic_role, const char **value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_device_name)
		ret = info->ops->fg_ic_get_device_name(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_device_name);

int platform_fg_ops_get_temp_min(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_temp_min)
		ret = info->ops->fg_ic_get_temp_min(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_temp_min);

void platform_fg_ops_set_force_report_full(unsigned int ic_role)
{
	struct fuelguage_info *info;
	int idx;

	if (ic_role >= FG_IC_MAX)
		return;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_set_force_report_full)
		info->ops->fg_ic_set_force_report_full(info->data);
	srcu_read_unlock(&platform_fg_srcu, idx);
}
EXPORT_SYMBOL(platform_fg_ops_set_force_report_full);

int platform_fg_ops_get_fc(unsigned int ic_role, bool *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_fc)
		ret = info->ops->fg_ic_get_fc(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_fc);

int platform_fg_ops_set_co(unsigned int ic_role, bool value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_set_co)
		ret = info->ops->fg_ic_set_co(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_set_co);

void platform_fg_ops_get_ui_soh(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;

	if (ic_role >= FG_IC_MAX)
		return;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_ui_soh)
		info->ops->fg_ic_get_ui_soh(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
}
EXPORT_SYMBOL(platform_fg_ops_get_ui_soh);

void platform_fg_ops_get_pack_vendor(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;

	if (ic_role >= FG_IC_MAX)
		return;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_pack_vendor)
		info->ops->fg_ic_get_pack_vendor(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
}
EXPORT_SYMBOL(platform_fg_ops_get_pack_vendor);

unsigned long platform_fg_ops_get_calc_rvalue(unsigned int ic_role)
{
	struct fuelguage_info *info;
	int idx;
	unsigned long ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_calc_rvalue)
		ret = info->ops->fg_ic_get_calc_rvalue(info->data);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_calc_rvalue);

int platform_fg_ops_get_batt_sn(unsigned int ic_role, char *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_batt_sn)
		ret = info->ops->fg_ic_get_batt_sn(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_batt_sn);

int platform_fg_ops_get_csd_flag(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_csd_flag)
		ret = info->ops->fg_ic_get_csd_flag(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_csd_flag);

int platform_fg_ops_get_batt_qmax(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_batt_qmax)
		ret = info->ops->fg_ic_get_batt_qmax(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_batt_qmax);

int platform_fg_ops_get_fg_vendor(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_fg_vendor)
		ret = info->ops->fg_ic_get_fg_vendor(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_fg_vendor);

int platform_fg_ops_set_reboot_vol_thr(unsigned int ic_role, u8 value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_set_reboot_vol_thr)
		ret = info->ops->fg_ic_set_reboot_vol_thr(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_set_reboot_vol_thr);

int platform_fg_ops_get_fast_mode_times(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_get_fast_mode_times)
		ret = info->ops->fg_ic_get_fast_mode_times(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_fast_mode_times);

int platform_fg_ops_set_fast_mode_times(unsigned int ic_role, int value)
{
	struct fuelguage_info *info;
	int idx;
	int ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops->fg_ic_set_fast_mode_times)
		ret = info->ops->fg_ic_set_fast_mode_times(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_set_fast_mode_times);

static struct platform_driver platform_fg_ops_driver = {
	.driver = {
		.name = "platform_fg_ops",
	},
};

static int __init platform_fg_init(void)
{
	return platform_driver_register(&platform_fg_ops_driver);
}

static void __exit platform_fg_exit(void)
{
	struct fuelguage_info *old[FG_IC_MAX];
	unsigned int role;

	platform_driver_unregister(&platform_fg_ops_driver);
	mutex_lock(&platform_fg_lock);
	for (role = 0; role < FG_IC_MAX; role++)
		old[role] = rcu_replace_pointer(g_fg_ic_ops[role], NULL,
					lockdep_is_held(&platform_fg_lock));
	mutex_unlock(&platform_fg_lock);
	synchronize_srcu(&platform_fg_srcu);
	for (role = 0; role < FG_IC_MAX; role++)
		kfree(old[role]);
}
module_init(platform_fg_init);
module_exit(platform_fg_exit);
MODULE_DESCRIPTION("platform fg ops");
MODULE_AUTHOR("liyuze1@xiaomi.com");
MODULE_LICENSE("GPL v2");


/* The size gate prevents reading beyond an old 67-slot provider table. */
int platform_fg_ops_has_optional_op(unsigned int ic_role,
				    enum mca_fg_optional_op op)
{
	struct fuelguage_info *info;
	int idx, ret = -EPROBE_DEFER;

	if (ic_role >= FG_IC_MAX)
		return -EINVAL;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (!info || !info->ops)
		goto out;
	ret = 0;
	if (info->ops_size < sizeof(*info->ops))
		goto out;
	switch (op) {
	case MCA_FG_OP_AVERAGE_CURRENT:
		ret = !!info->ops->fg_ic_get_average_current;
		break;
	case MCA_FG_OP_OTA_FLAG:
		ret = !!info->ops->fg_ic_get_ota_update_flag;
		break;
	case MCA_FG_OP_OTA_UPDATE:
		ret = !!info->ops->fg_ic_ota_update_check;
		break;
	case MCA_FG_OP_QBG_CHG_DATA:
		ret = !!info->ops->fg_ic_qbg_send_chg_data;
		break;
	case MCA_FG_OP_FIRST_USAGE_DATE:
		ret = !!info->ops->fg_ic_get_first_usage_date;
		break;
	case MCA_FG_OP_MANUFACTURING_DATE:
		ret = !!info->ops->fg_ic_get_manufacturing_date;
		break;
	case MCA_FG_OP_SET_FIRST_USAGE_DATE:
		ret = !!info->ops->fg_ic_set_first_usage_date;
		break;
	case MCA_FG_OP_ABNORMAL_COUNTS:
		ret = !!info->ops->fg_ic_get_abnormal_counts;
		break;
	case MCA_FG_OP_PACK_VENDOR_CHECKED:
		ret = !!info->ops->fg_ic_get_pack_vendor_checked;
		break;
	default:
		ret = -EINVAL;
	}
out:
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_has_optional_op);

int platform_fg_ops_get_average_current(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int result = 0;
	int idx, ret = -EOPNOTSUPP;

	if (!value)
		return -EINVAL;
	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops_size >= sizeof(*info->ops) &&
	    info->ops->fg_ic_get_average_current)
		ret = info->ops->fg_ic_get_average_current(info->data, &result);
	srcu_read_unlock(&platform_fg_srcu, idx);
	if (!ret)
		*value = result;
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_average_current);

int platform_fg_ops_get_ota_update_flag(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int result = 0;
	int idx, ret = -EOPNOTSUPP;

	if (!value)
		return -EINVAL;
	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops_size >= sizeof(*info->ops) &&
	    info->ops->fg_ic_get_ota_update_flag)
		ret = info->ops->fg_ic_get_ota_update_flag(info->data, &result);
	srcu_read_unlock(&platform_fg_srcu, idx);
	if (!ret)
		*value = result;
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_ota_update_flag);

int platform_fg_ops_ota_update_check(unsigned int ic_role)
{
	struct fuelguage_info *info;
	int idx, ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops_size >= sizeof(*info->ops) &&
	    info->ops->fg_ic_ota_update_check)
		ret = info->ops->fg_ic_ota_update_check(info->data);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_ota_update_check);

int platform_fg_ops_qbg_send_chg_data(unsigned int ic_role)
{
	struct fuelguage_info *info;
	int idx, ret = -EOPNOTSUPP;

	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops_size >= sizeof(*info->ops) &&
	    info->ops->fg_ic_qbg_send_chg_data)
		ret = info->ops->fg_ic_qbg_send_chg_data(info->data);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_qbg_send_chg_data);

int platform_fg_ops_get_first_usage_date(unsigned int ic_role, u8 *value)
{
	struct fuelguage_info *info;
	u8 result[MCA_FG_DATE_LEN];
	int idx, ret = -EOPNOTSUPP;

	if (!value)
		return -EINVAL;
	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops_size >= sizeof(*info->ops) &&
	    info->ops->fg_ic_get_first_usage_date)
		ret = info->ops->fg_ic_get_first_usage_date(info->data, result);
	srcu_read_unlock(&platform_fg_srcu, idx);
	if (!ret)
		memcpy(value, result, sizeof(result));
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_first_usage_date);

int platform_fg_ops_get_manufacturing_date(unsigned int ic_role, u8 *value)
{
	struct fuelguage_info *info;
	u8 result[MCA_FG_DATE_LEN];
	int idx, ret = -EOPNOTSUPP;

	if (!value)
		return -EINVAL;
	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops_size >= sizeof(*info->ops) &&
	    info->ops->fg_ic_get_manufacturing_date)
		ret = info->ops->fg_ic_get_manufacturing_date(info->data, result);
	srcu_read_unlock(&platform_fg_srcu, idx);
	if (!ret)
		memcpy(value, result, sizeof(result));
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_manufacturing_date);

int platform_fg_ops_set_first_usage_date(unsigned int ic_role, const char *value)
{
	struct fuelguage_info *info;
	int idx, ret = -EOPNOTSUPP;

	if (!value)
		return -EINVAL;
	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops_size >= sizeof(*info->ops) &&
	    info->ops->fg_ic_set_first_usage_date)
		ret = info->ops->fg_ic_set_first_usage_date(info->data, value);
	srcu_read_unlock(&platform_fg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_set_first_usage_date);

int platform_fg_ops_get_abnormal_counts(unsigned int ic_role,
				      struct mca_fg_abnormal_counts *value)
{
	struct fuelguage_info *info;
	struct mca_fg_abnormal_counts result;
	int idx, ret = -EOPNOTSUPP;

	if (!value)
		return -EINVAL;
	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops_size >= sizeof(*info->ops) &&
	    info->ops->fg_ic_get_abnormal_counts)
		ret = info->ops->fg_ic_get_abnormal_counts(info->data, &result);
	srcu_read_unlock(&platform_fg_srcu, idx);
	if (!ret)
		*value = result;
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_abnormal_counts);

int platform_fg_ops_get_pack_vendor_checked(unsigned int ic_role, int *value)
{
	struct fuelguage_info *info;
	int result = 0;
	int idx, ret = -EOPNOTSUPP;

	if (!value)
		return -EINVAL;
	if (ic_role >= FG_IC_MAX)
		return -EOPNOTSUPP;
	idx = srcu_read_lock(&platform_fg_srcu);
	info = srcu_dereference(g_fg_ic_ops[ic_role], &platform_fg_srcu);
	if (info && info->ops && info->ops_size >= sizeof(*info->ops) &&
	    info->ops->fg_ic_get_pack_vendor_checked)
		ret = info->ops->fg_ic_get_pack_vendor_checked(info->data, &result);
	srcu_read_unlock(&platform_fg_srcu, idx);
	if (!ret)
		*value = result;
	return ret;
}
EXPORT_SYMBOL(platform_fg_ops_get_pack_vendor_checked);
