// SPDX-License-Identifier: GPL-2.0
/*
 * mca_protocol_class.c
 *
 * mca protocol class driver
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
#include <linux/stat.h>
#include <linux/init.h>
#include <linux/ctype.h>
#include <linux/err.h>
#include <linux/slab.h>
#include <linux/kernel.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/notifier.h>
#include <linux/srcu.h>
#include <mca/protocol/protocol_class.h>

#define adapter_protocol_invalid_ops(data, name) \
	(!data || !data->ops || !data->ops->name)

struct adapter_protocol_class_data {
	struct adapter_protocol_class_ops *ops;
	void *data;
};
static struct adapter_protocol_class_data __rcu
	*g_protocol_class_data[ADAPTER_PROTOCOL_MAX];
static DEFINE_MUTEX(g_protocol_class_lock);
DEFINE_STATIC_SRCU(g_protocol_class_srcu);

/* Registration is allowed from sleepable context, outside a dispatched callback. */
int protocol_class_register_ops(unsigned int protocol,
				struct adapter_protocol_class_ops *ops,
				void *data)
{
	struct adapter_protocol_class_data *entry, *old;

	if (protocol >= ADAPTER_PROTOCOL_MAX || !ops)
		return -1;
	entry = kmalloc(sizeof(*entry), GFP_KERNEL);
	if (!entry)
		return -ENOMEM;
	entry->ops = ops;
	entry->data = data;
	mutex_lock(&g_protocol_class_lock);
	old = rcu_replace_pointer(g_protocol_class_data[protocol], entry,
				  lockdep_is_held(&g_protocol_class_lock));
	mutex_unlock(&g_protocol_class_lock);
	synchronize_srcu(&g_protocol_class_srcu);
	kfree(old);
	return 0;
}
EXPORT_SYMBOL(protocol_class_register_ops);

int protocol_class_unregister_ops(unsigned int protocol,
				  struct adapter_protocol_class_ops *ops,
				  void *data)
{
	struct adapter_protocol_class_data *old;

	if (protocol >= ADAPTER_PROTOCOL_MAX || !ops)
		return -EINVAL;
	mutex_lock(&g_protocol_class_lock);
	old = rcu_dereference_protected(g_protocol_class_data[protocol],
				       lockdep_is_held(&g_protocol_class_lock));
	if (!old || old->ops != ops || old->data != data) {
		mutex_unlock(&g_protocol_class_lock);
		/* A replacement may have detached this provider while callbacks still run. */
		synchronize_srcu(&g_protocol_class_srcu);
		return -ENOENT;
	}
	RCU_INIT_POINTER(g_protocol_class_data[protocol], NULL);
	mutex_unlock(&g_protocol_class_lock);
	synchronize_srcu(&g_protocol_class_srcu);
	kfree(old);
	return 0;
}
EXPORT_SYMBOL(protocol_class_unregister_ops);

int protocol_class_set_adapter_verified(unsigned int protocol, int verified)
{
	struct adapter_protocol_class_data *temp_data;
	int idx, ret = -1;

	if (protocol >= ADAPTER_PROTOCOL_MAX)
		return -1;
	idx = srcu_read_lock(&g_protocol_class_srcu);
	temp_data = srcu_dereference(g_protocol_class_data[protocol],
				     &g_protocol_class_srcu);
	if (!adapter_protocol_invalid_ops(temp_data, set_adapter_verified))
		ret = temp_data->ops->set_adapter_verified(temp_data->data, verified);
	srcu_read_unlock(&g_protocol_class_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(protocol_class_set_adapter_verified);

int protocol_class_get_adapter_verified(unsigned int protocol, int *verified)
{
	struct adapter_protocol_class_data *temp_data;
	int idx, ret = -1;

	if (protocol >= ADAPTER_PROTOCOL_MAX)
		return -1;
	idx = srcu_read_lock(&g_protocol_class_srcu);
	temp_data = srcu_dereference(g_protocol_class_data[protocol],
				     &g_protocol_class_srcu);
	if (!adapter_protocol_invalid_ops(temp_data, get_adapter_verified))
		ret = temp_data->ops->get_adapter_verified(temp_data->data, verified);
	srcu_read_unlock(&g_protocol_class_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(protocol_class_get_adapter_verified);

int protocol_class_get_adapter_max_power(unsigned int protocol,
					 unsigned int *max_power)
{
	struct adapter_protocol_class_data *temp_data;
	int idx, ret = -1;

	if (protocol >= ADAPTER_PROTOCOL_MAX)
		return -1;
	idx = srcu_read_lock(&g_protocol_class_srcu);
	temp_data = srcu_dereference(g_protocol_class_data[protocol],
				     &g_protocol_class_srcu);
	if (!adapter_protocol_invalid_ops(temp_data, get_adapter_max_power))
		ret = temp_data->ops->get_adapter_max_power(temp_data->data,
						     max_power);
	srcu_read_unlock(&g_protocol_class_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(protocol_class_get_adapter_max_power);

int protocol_class_get_adapter_pwr_max_power(unsigned int protocol,
					     unsigned int *max_power)
{
	struct adapter_protocol_class_data *temp_data;
	int idx, ret = -1;

	if (protocol >= ADAPTER_PROTOCOL_MAX)
		return -1;
	idx = srcu_read_lock(&g_protocol_class_srcu);
	temp_data = srcu_dereference(g_protocol_class_data[protocol],
				     &g_protocol_class_srcu);
	if (!adapter_protocol_invalid_ops(temp_data, get_adapter_pwr_max_power))
		ret = temp_data->ops->get_adapter_pwr_max_power(temp_data->data,
							 max_power);
	srcu_read_unlock(&g_protocol_class_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(protocol_class_get_adapter_pwr_max_power);

int protocol_class_det_adapter_type(unsigned int protocol, int en)
{
	struct adapter_protocol_class_data *temp_data;
	int idx, ret = -1;

	if (protocol >= ADAPTER_PROTOCOL_MAX)
		return -1;
	idx = srcu_read_lock(&g_protocol_class_srcu);
	temp_data = srcu_dereference(g_protocol_class_data[protocol],
				     &g_protocol_class_srcu);
	if (!adapter_protocol_invalid_ops(temp_data, adapter_det_en))
		ret = temp_data->ops->adapter_det_en(temp_data->data, en);
	srcu_read_unlock(&g_protocol_class_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(protocol_class_det_adapter_type);

int protocol_class_get_adapter_type(unsigned int protocol, unsigned int *value)
{
	struct adapter_protocol_class_data *temp_data;
	int idx, ret = -1;

	if (protocol >= ADAPTER_PROTOCOL_MAX)
		return -1;
	idx = srcu_read_lock(&g_protocol_class_srcu);
	temp_data = srcu_dereference(g_protocol_class_data[protocol],
				     &g_protocol_class_srcu);
	if (!adapter_protocol_invalid_ops(temp_data, get_adapter_type))
		ret = temp_data->ops->get_adapter_type(temp_data->data, (int *)value);
	srcu_read_unlock(&g_protocol_class_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(protocol_class_get_adapter_type);

int protocol_class_get_adapter_power_cap(unsigned int protocol,
					 struct adapter_power_cap_info *cap)
{
	struct adapter_protocol_class_data *temp_data;
	int idx, ret = -1;

	if (protocol >= ADAPTER_PROTOCOL_MAX)
		return -1;
	idx = srcu_read_lock(&g_protocol_class_srcu);
	temp_data = srcu_dereference(g_protocol_class_data[protocol],
				     &g_protocol_class_srcu);
	if (!adapter_protocol_invalid_ops(temp_data, get_adapter_pwr_cap))
		ret = temp_data->ops->get_adapter_pwr_cap(temp_data->data, cap);
	srcu_read_unlock(&g_protocol_class_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(protocol_class_get_adapter_power_cap);

int protocol_class_set_adapter_volt_and_curr(unsigned int protocol, int volt,
					     int curr)
{
	struct adapter_protocol_class_data *temp_data;
	int idx, ret = -1;

	if (protocol >= ADAPTER_PROTOCOL_MAX)
		return -1;
	idx = srcu_read_lock(&g_protocol_class_srcu);
	temp_data = srcu_dereference(g_protocol_class_data[protocol],
				     &g_protocol_class_srcu);
	if (!adapter_protocol_invalid_ops(temp_data, set_adapter_volt_and_curr))
		ret = temp_data->ops->set_adapter_volt_and_curr(temp_data->data, volt,
							 curr);
	srcu_read_unlock(&g_protocol_class_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(protocol_class_set_adapter_volt_and_curr);

int protocol_class_get_adapter_volt_and_curr(unsigned int protocol, int *volt,
					     int *curr)
{
	struct adapter_protocol_class_data *temp_data;
	int idx, ret = -1;

	if (protocol >= ADAPTER_PROTOCOL_MAX)
		return -1;
	idx = srcu_read_lock(&g_protocol_class_srcu);
	temp_data = srcu_dereference(g_protocol_class_data[protocol],
				     &g_protocol_class_srcu);
	if (!adapter_protocol_invalid_ops(temp_data, get_adapter_volt_and_curr))
		ret = temp_data->ops->get_adapter_volt_and_curr(temp_data->data, volt,
							 curr);
	srcu_read_unlock(&g_protocol_class_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(protocol_class_get_adapter_volt_and_curr);

int protocol_class_get_adapter_pps_ptf(unsigned int protocol, int *pps_ptf)
{
	struct adapter_protocol_class_data *temp_data;
	int idx, ret = -1;

	if (protocol >= ADAPTER_PROTOCOL_MAX)
		return -1;
	idx = srcu_read_lock(&g_protocol_class_srcu);
	temp_data = srcu_dereference(g_protocol_class_data[protocol],
				     &g_protocol_class_srcu);
	if (!adapter_protocol_invalid_ops(temp_data, get_adapter_pps_ptf))
		ret = temp_data->ops->get_adapter_pps_ptf(temp_data->data, pps_ptf);
	srcu_read_unlock(&g_protocol_class_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(protocol_class_get_adapter_pps_ptf);

int protocol_class_get_adapter_info(unsigned int protocol,
				    struct adapter_vendor_info *info)
{
	struct adapter_protocol_class_data *temp_data;
	int idx, ret = -1;

	if (protocol >= ADAPTER_PROTOCOL_MAX)
		return -1;
	idx = srcu_read_lock(&g_protocol_class_srcu);
	temp_data = srcu_dereference(g_protocol_class_data[protocol],
				     &g_protocol_class_srcu);
	if (!adapter_protocol_invalid_ops(temp_data, get_adapter_info))
		ret = temp_data->ops->get_adapter_info(temp_data->data, info);
	srcu_read_unlock(&g_protocol_class_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(protocol_class_get_adapter_info);

int protocol_class_get_adapter_power_curve(
	unsigned int protocol, struct adapter_power_curve *pwr_curve)
{
	struct adapter_protocol_class_data *temp_data;
	int idx, ret = -1;

	if (protocol >= ADAPTER_PROTOCOL_MAX)
		return -1;
	idx = srcu_read_lock(&g_protocol_class_srcu);
	temp_data = srcu_dereference(g_protocol_class_data[protocol],
				     &g_protocol_class_srcu);
	if (!adapter_protocol_invalid_ops(temp_data, get_adapter_power_curve))
		ret = temp_data->ops->get_adapter_power_curve(temp_data->data,
						       pwr_curve);
	srcu_read_unlock(&g_protocol_class_srcu, idx);
	return ret;
}
EXPORT_SYMBOL(protocol_class_get_adapter_power_curve);

static struct platform_driver protocol_class_driver = {
	.driver	= {
		.name = "protocol_class",
	},
};

module_platform_driver(protocol_class_driver);

MODULE_DESCRIPTION("mca protocol class");
MODULE_AUTHOR("getian@xiaomi.com");
MODULE_LICENSE("GPL v2");
