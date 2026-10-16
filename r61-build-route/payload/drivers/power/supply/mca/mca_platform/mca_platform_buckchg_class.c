// SPDX-License-Identifier: GPL-2.0
/*
 * mca_platform_buckchg_class.c
 *
 * mca platform buck charger class driver
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
#include <mca/platform/platform_buckchg_class.h>

struct platform_class_buckchg_data {
	void *data;
	struct platform_class_buckchg_ops *ops;
	unsigned int ops_size;
};

static struct platform_class_buckchg_data __rcu
	*platform_buckchg_ops_data[MAX_BUCK_CHARGER];
static DEFINE_MUTEX(platform_buckchg_lock);
DEFINE_STATIC_SRCU(platform_buckchg_srcu);

/* Register/unregister from sleepable context outside a dispatched callback.
 * Keep ops and data valid until unregister returns. Replacement waits for old
 * callbacks and atomically publishes the associated ops/data pair.
 */
int platform_class_buckchg_ops_register_v2(unsigned int role, void *data,
		struct platform_class_buckchg_ops *ops, unsigned int ops_size)
{
	struct platform_class_buckchg_data *entry, *old;

	if (role >= MAX_BUCK_CHARGER || !ops ||
	    ops_size < offsetof(struct platform_class_buckchg_ops, get_aicl_status))
		return -EINVAL;
	entry = kmalloc(sizeof(*entry), GFP_KERNEL);
	if (!entry)
		return -ENOMEM;
	entry->data = data;
	entry->ops = ops;
	entry->ops_size = ops_size;
	mutex_lock(&platform_buckchg_lock);
	old = rcu_replace_pointer(platform_buckchg_ops_data[role], entry,
				  lockdep_is_held(&platform_buckchg_lock));
	mutex_unlock(&platform_buckchg_lock);
	synchronize_srcu(&platform_buckchg_srcu);
	kfree(old);
	return 0;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_register_v2);

/* Old source registrants have no optional AICL tail; never read past it. */
int platform_class_buckchg_ops_register(unsigned int role, void *data,
				struct platform_class_buckchg_ops *ops)
{
	return platform_class_buckchg_ops_register_v2(role, data, ops,
		offsetof(struct platform_class_buckchg_ops, get_aicl_status));
}
EXPORT_SYMBOL(platform_class_buckchg_ops_register);

int platform_class_buckchg_ops_unregister(unsigned int role, void *data,
					  struct platform_class_buckchg_ops *ops)
{
	struct platform_class_buckchg_data *old;

	if (role >= MAX_BUCK_CHARGER || !ops)
		return -EINVAL;
	mutex_lock(&platform_buckchg_lock);
	old = rcu_dereference_protected(platform_buckchg_ops_data[role],
				       lockdep_is_held(&platform_buckchg_lock));
	if (!old || old->ops != ops || old->data != data) {
		mutex_unlock(&platform_buckchg_lock);
		/* Replacement may already have detached a still-running provider. */
		synchronize_srcu(&platform_buckchg_srcu);
		return -ENOENT;
	}
	RCU_INIT_POINTER(platform_buckchg_ops_data[role], NULL);
	mutex_unlock(&platform_buckchg_lock);
	synchronize_srcu(&platform_buckchg_srcu);
	kfree(old);
	return 0;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_unregister);

int platform_class_buckchg_ops_enable_hvdcp(unsigned int role, int en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->enable_hvdcp)
		ret = temp_data->ops->enable_hvdcp(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_enable_hvdcp);

int platform_class_buckchg_ops_get_aicl_status(unsigned int role, int *status)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, value, ret = -EOPNOTSUPP;

	if (role >= MAX_BUCK_CHARGER || !status)
		return -EINVAL;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops &&
	    temp_data->ops_size >= offsetof(struct platform_class_buckchg_ops, get_aicl_status) +
			   sizeof(temp_data->ops->get_aicl_status) &&
	    temp_data->ops->get_aicl_status)
		ret = temp_data->ops->get_aicl_status(temp_data->data, &value);
	if (!ret)
		*status = value;
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_aicl_status);

int platform_class_buckchg_ops_get_online(unsigned int role, int *online)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_online)
		ret = temp_data->ops->get_online(temp_data->data, online);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_online);

int platform_class_buckchg_ops_is_charge_done(unsigned int role,
					      bool *charge_done)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->is_charge_done)
		ret = temp_data->ops->is_charge_done(temp_data->data, charge_done);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_is_charge_done);

int platform_class_buckchg_ops_get_hiz_status(unsigned int role, int *hz)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_hiz_status)
		ret = temp_data->ops->get_hiz_status(temp_data->data, hz);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_hiz_status);

int platform_class_buckchg_ops_get_input_volt_lmt(unsigned int role, int *mV)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_input_volt_lmt)
		ret = temp_data->ops->get_input_volt_lmt(temp_data->data, mV);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_input_volt_lmt);

int platform_class_buckchg_ops_get_input_curr_lmt(unsigned int role, int *mA)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_input_curr_lmt)
		ret = temp_data->ops->get_input_curr_lmt(temp_data->data, mA);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_input_curr_lmt);

int platform_class_buckchg_ops_get_bus_curr(unsigned int role, int *bus_curr)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_bus_curr)
		ret = temp_data->ops->get_bus_curr(temp_data->data, bus_curr);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_bus_curr);

int platform_class_buckchg_ops_get_bus_volt(unsigned int role, int *bus_volt)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_bus_volt)
		ret = temp_data->ops->get_bus_volt(temp_data->data, bus_volt);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_bus_volt);

int platform_class_buckchg_ops_get_usb_sns_volt(unsigned int role,
						int *bus_volt)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_usb_sns_volt)
		ret = temp_data->ops->get_usb_sns_volt(temp_data->data, bus_volt);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_usb_sns_volt);

int platform_class_buckchg_ops_get_ac_volt(unsigned int role, int *mV)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_ac_volt)
		ret = temp_data->ops->get_ac_volt(temp_data->data, mV);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_ac_volt);

int platform_class_buckchg_ops_get_batt_volt_sns(unsigned int role, int *sns)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_batt_volt_sns)
		ret = temp_data->ops->get_batt_volt_sns(temp_data->data, sns);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_batt_volt_sns);

int platform_class_buckchg_ops_get_batt_volt(unsigned int role, int *mV)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_batt_volt)
		ret = temp_data->ops->get_batt_volt(temp_data->data, mV);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_batt_volt);

int platform_class_buckchg_ops_get_batt_curr(unsigned int role, int *mA)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_batt_curr)
		ret = temp_data->ops->get_batt_curr(temp_data->data, mA);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_batt_curr);

int platform_class_buckchg_ops_get_sys_volt(unsigned int role, int *vsys_min)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_sys_volt)
		ret = temp_data->ops->get_sys_volt(temp_data->data, vsys_min);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_sys_volt);

int platform_class_buckchg_ops_get_bus_tsns(unsigned int role, int *sns)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_bus_tsns)
		ret = temp_data->ops->get_bus_tsns(temp_data->data, sns);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_bus_tsns);

int platform_class_buckchg_ops_get_batt_tsns(unsigned int role, int *sns)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_batt_tsns)
		ret = temp_data->ops->get_batt_tsns(temp_data->data, sns);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_batt_tsns);

int platform_class_buckchg_ops_get_die_temp(unsigned int role, int *temp)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_die_temp)
		ret = temp_data->ops->get_die_temp(temp_data->data, temp);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_die_temp);

int platform_class_buckchg_ops_get_batt_id(unsigned int role, int *id)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_batt_id)
		ret = temp_data->ops->get_batt_id(temp_data->data, id);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_batt_id);

int platform_class_buckchg_ops_get_chg_status(unsigned int role,
					      int *chg_status)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_chg_status)
		ret = temp_data->ops->get_chg_status(temp_data->data, chg_status);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_chg_status);

int platform_class_buckchg_ops_get_chg_type(unsigned int role, int *chg_type)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_chg_type)
		ret = temp_data->ops->get_chg_type(temp_data->data, chg_type);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_chg_type);

int platform_class_buckchg_ops_get_term_curr(unsigned int role, int *term_curr)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_term_curr)
		ret = temp_data->ops->get_term_curr(temp_data->data, term_curr);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_term_curr);

int platform_class_buckchg_ops_get_term_volt(unsigned int role, int *term_volt)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_term_volt)
		ret = temp_data->ops->get_term_volt(temp_data->data, term_volt);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_term_volt);

int platform_class_buckchg_ops_get_wls_curr(unsigned int role, int *wls_curr)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_wls_curr)
		ret = temp_data->ops->get_wls_curr(temp_data->data, wls_curr);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_wls_curr);

int platform_class_buckchg_ops_set_hiz(unsigned int role, bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_hiz)
		ret = temp_data->ops->set_hiz(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_hiz);

int platform_class_buckchg_ops_set_wls_hiz(unsigned int role, bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_wls_hiz)
		ret = temp_data->ops->set_wls_hiz(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_wls_hiz);

int platform_class_buckchg_ops_set_input_curr_lmt(unsigned int role, int ma)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_input_curr_lmt)
		ret = temp_data->ops->set_input_curr_lmt(temp_data->data, ma);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_input_curr_lmt);

int platform_class_buckchg_ops_set_wls_input_curr_lmt(unsigned int role, int ma)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_wls_input_curr_lmt)
		ret = temp_data->ops->set_wls_input_curr_lmt(temp_data->data, ma);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_wls_input_curr_lmt);

int platform_class_buckchg_ops_set_input_volt_lmt(unsigned int role, int mv)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_input_volt_lmt)
		ret = temp_data->ops->set_input_volt_lmt(temp_data->data, mv);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_input_volt_lmt);

int platform_class_buckchg_ops_set_ichg(unsigned int role, int ma)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_ichg)
		ret = temp_data->ops->set_ichg(temp_data->data, ma);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_ichg);

int platform_class_buckchg_ops_set_chg(unsigned int role, bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_chg)
		ret = temp_data->ops->set_chg(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_chg);

int platform_class_buckchg_ops_set_buck_fsw(unsigned int role, int mv)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_buck_fsw)
		ret = temp_data->ops->set_buck_fsw(temp_data->data, mv);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_buck_fsw);

int platform_class_buckchg_ops_set_otg_curr(unsigned int role, int ma)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_otg_curr)
		ret = temp_data->ops->set_otg_curr(temp_data->data, ma);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_otg_curr);

int platform_class_buckchg_ops_set_otg_volt(unsigned int role, int mv)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_otg_volt)
		ret = temp_data->ops->set_otg_volt(temp_data->data, mv);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_otg_volt);

int platform_class_buckchg_ops_set_term(unsigned int role, bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_term)
		ret = temp_data->ops->set_term(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_term);

int platform_class_buckchg_ops_set_term_curr(unsigned int role, int ma)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_term_curr)
		ret = temp_data->ops->set_term_curr(temp_data->data, ma);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_term_curr);

int platform_class_buckchg_ops_set_term_volt(unsigned int role, int mv)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_term_volt)
		ret = temp_data->ops->set_term_volt(temp_data->data, mv);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_term_volt);

int platform_class_buckchg_ops_adc_enable(unsigned int role, bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->adc_enable)
		ret = temp_data->ops->adc_enable(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_adc_enable);

int platform_class_buckchg_ops_set_prechg_volt(unsigned int role, int mv)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_prechg_volt)
		ret = temp_data->ops->set_prechg_volt(temp_data->data, mv);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_prechg_volt);

int platform_class_buckchg_ops_set_prechg_curr(unsigned int role, int ma)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_prechg_curr)
		ret = temp_data->ops->set_prechg_curr(temp_data->data, ma);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_prechg_curr);

int platform_class_buckchg_ops_force_dpdm(unsigned int role, int en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->force_dpdm)
		ret = temp_data->ops->force_dpdm(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_force_dpdm);

int platform_class_buckchg_ops_request_dpdm(unsigned int role, bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->request_dpdm)
		ret = temp_data->ops->request_dpdm(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_request_dpdm);

int platform_class_buckchg_ops_set_wd_timeout(unsigned int role, int ms)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_wd_timeout)
		ret = temp_data->ops->set_wd_timeout(temp_data->data, ms);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_wd_timeout);

int platform_class_buckchg_ops_kick_wd(unsigned int role)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->kick_wd)
		ret = temp_data->ops->kick_wd(temp_data->data);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_kick_wd);

int platform_class_buckchg_ops_set_qc_volt(unsigned int role, int mv)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_qc_volt)
		ret = temp_data->ops->set_qc_volt(temp_data->data, mv);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_qc_volt);

int platform_class_buckchg_ops_set_usb_aicl_cont_thd(unsigned int role, int mv)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_usb_aicl_cont_thd)
		ret = temp_data->ops->set_usb_aicl_cont_thd(temp_data->data, mv);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_usb_aicl_cont_thd);

int platform_class_buckchg_ops_get_usb_aicl_cont_thd(unsigned int role, int *mv)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_usb_aicl_cont_thd)
		ret = temp_data->ops->get_usb_aicl_cont_thd(temp_data->data, mv);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_usb_aicl_cont_thd);

int platform_class_buckchg_ops_set_opt_fws(unsigned int role, int mv)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_opt_fws)
		ret = temp_data->ops->set_opt_fws(temp_data->data, mv);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_opt_fws);

int platform_class_buckchg_ops_usb_adapter_allow_override(unsigned int role,
							  bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->usb_adapter_allow_override)
		ret = temp_data->ops->usb_adapter_allow_override(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_usb_adapter_allow_override);

int platform_class_buckchg_ops_set_qc3_volt(unsigned int role, int mv)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_qc3_volt)
		ret = temp_data->ops->set_qc3_volt(temp_data->data, mv);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_qc3_volt);

int platform_class_buckchg_ops_get_otg_boost_src(unsigned int role,
						 int *otg_boost_src)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_otg_boost_src)
		ret = temp_data->ops->get_otg_boost_src(temp_data->data,
						 otg_boost_src);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_otg_boost_src);

int platform_class_buckchg_ops_get_otg_boost_enable_status(
	unsigned int role, int *otg_boost_enable_sts)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_otg_boost_enable_status)
		ret = temp_data->ops->get_otg_boost_enable_status(
		temp_data->data, otg_boost_enable_sts);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_otg_boost_enable_status);

int platform_class_buckchg_ops_get_otg_gate_enable_status(
	unsigned int role, int *otg_gate_enable_sts)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_otg_gate_enable_status)
		ret = temp_data->ops->get_otg_gate_enable_status(temp_data->data,
							  otg_gate_enable_sts);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_otg_gate_enable_status);

int platform_class_buckchg_ops_set_otg(unsigned int role, bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_otg)
		ret = temp_data->ops->set_otg(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_otg);

int platform_class_buckchg_ops_set_boost_enable(unsigned int role,
						int src_enable)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_boost_enable)
		ret = temp_data->ops->set_boost_enable(temp_data->data, src_enable);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_boost_enable);

int platform_class_buckchg_ops_set_boost_voltage(unsigned int role,
						 int src_value)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_boost_voltage)
		ret = temp_data->ops->set_boost_voltage(temp_data->data, src_value);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_boost_voltage);

int platform_class_buckchg_ops_set_aicl_enable(unsigned int role, bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_aicl_enable)
		ret = temp_data->ops->set_aicl_enable(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_aicl_enable);

int platform_class_buckchg_ops_set_rerun_aicl(unsigned int role, bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_rerun_aicl)
		ret = temp_data->ops->set_rerun_aicl(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_rerun_aicl);

int platform_class_buckchg_ops_is_support_cid(unsigned int role, bool *en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->is_support_cid)
		ret = temp_data->ops->is_support_cid(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_is_support_cid);

int platform_class_buckchg_ops_set_ship_mode(unsigned int role, bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_ship_mode)
		ret = temp_data->ops->set_ship_mode(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_ship_mode);

int platform_class_buckchg_ops_get_ship_mode(unsigned int role, bool *en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_ship_mode)
		ret = temp_data->ops->get_ship_mode(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_ship_mode);

int platform_class_buckchg_ops_set_wls_vdd_flag(unsigned int role, bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_wls_vdd_flag)
		ret = temp_data->ops->set_wls_vdd_flag(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_wls_vdd_flag);

int platform_class_buckchg_ops_get_lpd_enable(unsigned int role, int *lpd_en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_lpd_enable)
		ret = temp_data->ops->get_lpd_enable(temp_data->data, lpd_en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_lpd_enable);

int platform_class_buckchg_ops_get_lpd_status(unsigned int role,
					      int *lpd_status)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_lpd_status)
		ret = temp_data->ops->get_lpd_status(temp_data->data, lpd_status);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_lpd_status);

int platform_class_buckchg_ops_get_lpd_sbu1(unsigned int role, int *lpd_sbu1)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_lpd_sbu1)
		ret = temp_data->ops->get_lpd_sbu1(temp_data->data, lpd_sbu1);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_lpd_sbu1);

int platform_class_buckchg_ops_get_lpd_sbu2(unsigned int role, int *lpd_sbu2)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_lpd_sbu2)
		ret = temp_data->ops->get_lpd_sbu2(temp_data->data, lpd_sbu2);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_lpd_sbu2);

int platform_class_buckchg_ops_get_lpd_cc1(unsigned int role, int *lpd_cc1)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_lpd_cc1)
		ret = temp_data->ops->get_lpd_cc1(temp_data->data, lpd_cc1);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_lpd_cc1);

int platform_class_buckchg_ops_get_lpd_cc2(unsigned int role, int *lpd_cc2)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_lpd_cc2)
		ret = temp_data->ops->get_lpd_cc2(temp_data->data, lpd_cc2);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_lpd_cc2);

int platform_class_buckchg_ops_get_lpd_dp(unsigned int role, int *lpd_dp)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_lpd_dp)
		ret = temp_data->ops->get_lpd_dp(temp_data->data, lpd_dp);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_lpd_dp);

int platform_class_buckchg_ops_get_lpd_dm(unsigned int role, int *lpd_dm)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_lpd_dm)
		ret = temp_data->ops->get_lpd_dm(temp_data->data, lpd_dm);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_lpd_dm);

int platform_class_buckchg_ops_set_lpd_sbu1(unsigned int role, int lpd_sbu1)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_lpd_sbu1)
		ret = temp_data->ops->set_lpd_sbu1(temp_data->data, lpd_sbu1);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_lpd_sbu1);

int platform_class_buckchg_ops_set_lpd_control(unsigned int role,
					       int lpd_control)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_lpd_control)
		ret = temp_data->ops->set_lpd_control(temp_data->data, lpd_control);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_lpd_control);

int platform_class_buckchg_ops_get_lpd_control(unsigned int role,
					       int *lpd_control)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_lpd_control)
		ret = temp_data->ops->get_lpd_control(temp_data->data, lpd_control);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_lpd_control);

int platform_class_buckchg_ops_set_lpd_uart_control(unsigned int role,
						    int lpd_uart_control)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_lpd_uart_control)
		ret = temp_data->ops->set_lpd_uart_control(temp_data->data,
						    lpd_uart_control);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_lpd_uart_control);

int platform_class_buckchg_ops_get_lpd_uart_control(unsigned int role,
						    int *lpd_uart_control)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_lpd_uart_control)
		ret = temp_data->ops->get_lpd_uart_control(temp_data->data,
						    lpd_uart_control);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_lpd_uart_control);

int platform_class_buckchg_ops_get_pack_vbat(unsigned int role, int *pvbat)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_pack_vbat)
		ret = temp_data->ops->get_pack_vbat(temp_data->data, pvbat);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_pack_vbat);

int platform_class_buckchg_ops_set_eu_model(unsigned int role, bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_eu_model)
		ret = temp_data->ops->set_eu_model(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_eu_model);

int platform_class_buckchg_ops_is_init_ok(unsigned int role)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->is_init_ok)
		ret = temp_data->ops->is_init_ok(temp_data->data);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_is_init_ok);

int platform_class_buckchg_ops_set_restart_aicl(unsigned int role, bool en)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_restart_aicl)
		ret = temp_data->ops->set_restart_aicl(temp_data->data, en);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_restart_aicl);

int platform_class_buckchg_ops_get_pack_ibat(unsigned int role, int *ibat)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_pack_ibat)
		ret = temp_data->ops->get_pack_ibat(temp_data->data, ibat);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_pack_ibat);

int platform_class_buckchg_ops_get_pack_tbat(unsigned int role, int *tbat)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_pack_tbat)
		ret = temp_data->ops->get_pack_tbat(temp_data->data, tbat);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_pack_tbat);

int platform_class_buckchg_ops_set_too_hot_limit(unsigned int role, int limit)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_too_hot_limit)
		ret = temp_data->ops->set_too_hot_limit(temp_data->data, limit);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_too_hot_limit);

int platform_class_buckchg_ops_set_ovp_vth(unsigned int role, int value)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_ovp_vth)
		ret = temp_data->ops->set_ovp_vth(temp_data->data, value);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_ovp_vth);

int platform_class_buckchg_ops_get_ovp_vth(unsigned int role, int *value)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_ovp_vth)
		ret = temp_data->ops->get_ovp_vth(temp_data->data, value);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_ovp_vth);

int platform_class_buckchg_ops_get_icl_status(unsigned int role, int *value)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_icl_status)
		ret = temp_data->ops->get_icl_status(temp_data->data, value);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_icl_status);

int platform_class_buckchg_ops_get_usbin_collapse_rt_sts(unsigned int role, int *value)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_usbin_collapse_rt_sts)
		ret = temp_data->ops->get_usbin_collapse_rt_sts(temp_data->data, value);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_usbin_collapse_rt_sts);

int platform_class_buckchg_ops_set_screen_status(unsigned int role, bool value)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_screen_status)
		ret = temp_data->ops->set_screen_status(temp_data->data, value);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_screen_status);

int platform_class_buckchg_ops_set_audio_status(unsigned int role, int value)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->set_audio_status)
		ret = temp_data->ops->set_audio_status(temp_data->data, value);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_set_audio_status);

int platform_class_buckchg_ops_get_usb_input_swap(unsigned int role, bool *value)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_usb_input_swap)
		ret = temp_data->ops->get_usb_input_swap(temp_data->data, value);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_usb_input_swap);

int platform_class_buckchg_ops_get_wls_input_swap(unsigned int role, bool *value)
{
	struct platform_class_buckchg_data *temp_data;
	int idx, ret = -1;

	if (role >= MAX_BUCK_CHARGER)
		return -1;
	idx = srcu_read_lock(&platform_buckchg_srcu);
	temp_data = srcu_dereference(platform_buckchg_ops_data[role],
				     &platform_buckchg_srcu);
	if (temp_data && temp_data->ops && temp_data->ops->get_wls_input_swap)
		ret = temp_data->ops->get_wls_input_swap(temp_data->data, value);
	srcu_read_unlock(&platform_buckchg_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(platform_class_buckchg_ops_get_wls_input_swap);

static struct platform_driver platform_class_buckchg_driver = {
	.driver = {
		.name = "platform_class_buckchg",
	},
};

static int __init platform_class_buckchg_init(void)
{
	return platform_driver_register(&platform_class_buckchg_driver);
}

static void __exit platform_class_buckchg_exit(void)
{
	struct platform_class_buckchg_data *old[MAX_BUCK_CHARGER];
	unsigned int i;

	platform_driver_unregister(&platform_class_buckchg_driver);
	mutex_lock(&platform_buckchg_lock);
	for (i = 0; i < MAX_BUCK_CHARGER; i++)
		old[i] = rcu_replace_pointer(platform_buckchg_ops_data[i], NULL,
					    lockdep_is_held(&platform_buckchg_lock));
	mutex_unlock(&platform_buckchg_lock);
	synchronize_srcu(&platform_buckchg_srcu);
	for (i = 0; i < MAX_BUCK_CHARGER; i++)
		kfree(old[i]);
}

module_init(platform_class_buckchg_init);
module_exit(platform_class_buckchg_exit);
MODULE_DESCRIPTION("platform buckchg class");
MODULE_AUTHOR("liyuze1@xiaomi.com");
MODULE_LICENSE("GPL v2");
