// SPDX-License-Identifier: GPL-2.0
/*
 * mca_platform_bc12_class.c
 *
 * mca bc 12 class driver
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
#include <linux/srcu.h>
#include <mca/common/mca_log.h>
#include <mca/protocol/protocol_class.h>
#include <mca/protocol/protocol_pd_class.h>
#include <mca/platform/platform_bc12_class.h>

#ifndef MCA_LOG_TAG
#define MCA_LOG_TAG "platform_bc12_class"
#endif

struct platform_class_bc12_ops_data {
	struct platform_bc12_class_ops *ops;
	void *data;
};

struct platform_class_bc12_info {
	struct device *dev;
	bool support_multi_bc12;
};

static struct platform_class_bc12_ops_data __rcu *g_bc12_ops_data[BC12_MAX_ROLE];
static DEFINE_MUTEX(g_bc12_lock);
DEFINE_STATIC_SRCU(g_bc12_srcu);

int platform_bc12_class_ops_register(unsigned int role, struct platform_bc12_class_ops *ops, void *data)
{
	struct platform_class_bc12_ops_data *entry, *old;
	if (role >= BC12_MAX_ROLE || !ops) return -EINVAL;
	entry = kmalloc(sizeof(*entry), GFP_KERNEL);
	if (!entry) return -ENOMEM;
	entry->ops = ops;
	entry->data = data;
	mutex_lock(&g_bc12_lock);
	old = rcu_replace_pointer(g_bc12_ops_data[role], entry, lockdep_is_held(&g_bc12_lock));
	mutex_unlock(&g_bc12_lock);
	synchronize_srcu(&g_bc12_srcu);
	kfree(old);
	return 0;
}
EXPORT_SYMBOL(platform_bc12_class_ops_register);

int platform_bc12_class_ops_unregister(unsigned int role, struct platform_bc12_class_ops *ops, void *data)
{
	struct platform_class_bc12_ops_data *old;
	if (role >= BC12_MAX_ROLE || !ops) return -EINVAL;
	mutex_lock(&g_bc12_lock);
	old = rcu_dereference_protected(g_bc12_ops_data[role], lockdep_is_held(&g_bc12_lock));
	if (!old || old->ops != ops || old->data != data) {
		mutex_unlock(&g_bc12_lock);
		synchronize_srcu(&g_bc12_srcu);
		return -ENOENT;
	}
	RCU_INIT_POINTER(g_bc12_ops_data[role], NULL);
	mutex_unlock(&g_bc12_lock);
	synchronize_srcu(&g_bc12_srcu);
	kfree(old);
	return 0;
}
EXPORT_SYMBOL(platform_bc12_class_ops_unregister);

static int platform_class_bc12_ops_det_en(unsigned int role, int en)
{
	struct platform_class_bc12_ops_data *entry;
	int idx, ret = -1;
	if (role >= BC12_MAX_ROLE) return -EINVAL;
	idx = srcu_read_lock(&g_bc12_srcu);
	entry = srcu_dereference(g_bc12_ops_data[role], &g_bc12_srcu);
	if (entry && entry->ops->bc12_det_en)
		ret = entry->ops->bc12_det_en(en, entry->data);
	srcu_read_unlock(&g_bc12_srcu, idx);
	return ret;
}

static int platform_class_bc12_ops_get_chg_type(unsigned int role, int *value)
{
	struct platform_class_bc12_ops_data *entry;
	int idx, ret = -1;
	if (role >= BC12_MAX_ROLE || !value) return -EINVAL;
	idx = srcu_read_lock(&g_bc12_srcu);
	entry = srcu_dereference(g_bc12_ops_data[role], &g_bc12_srcu);
	if (entry && entry->ops->get_charge_type)
		ret = entry->ops->get_charge_type(value, entry->data);
	srcu_read_unlock(&g_bc12_srcu, idx);
	return ret;
}

static unsigned int
platform_class_bc12_get_role(struct platform_class_bc12_info *info)
{
	int pd_active = 0;

	if (!info->support_multi_bc12)
		return BC12_MAIN_ROLE;

	(void)protocol_class_pd_get_pd_active(TYPEC_PORT_1, &pd_active);
	if (pd_active)
		return BC12_AUX_ROLE;

	return BC12_MAIN_ROLE;
}

static int platform_class_bc12_det_en(void *data, int en)
{
	struct platform_class_bc12_info *info =
		(struct platform_class_bc12_info *)data;
	unsigned int role;

	if (!data)
		return -1;

	role = platform_class_bc12_get_role(info);

	return platform_class_bc12_ops_det_en(role, en);
}

static int platform_class_bc12_get_real_type(void *data, int *value)
{
	struct platform_class_bc12_info *info =
		(struct platform_class_bc12_info *)data;
	unsigned int role;

	if (!data)
		return -1;

	role = platform_class_bc12_get_role(info);

	return platform_class_bc12_ops_get_chg_type(role, value);
}

static int platform_class_bc12_parse_dt(struct platform_class_bc12_info *info)
{
	struct device_node *node = info->dev->of_node;

	info->support_multi_bc12 =
		of_property_read_bool(node, "support-multi-bc12");

	return 0;
}

static struct adapter_protocol_class_ops g_bc12_ops = {
	.adapter_det_en = platform_class_bc12_det_en,
	.get_adapter_type = platform_class_bc12_get_real_type,
};

static int platform_class_bc12_probe(struct platform_device *pdev)
{
	struct platform_class_bc12_info *platform_class_bc12;
	int ret;

	platform_class_bc12 = devm_kzalloc(
		&pdev->dev, sizeof(*platform_class_bc12), GFP_KERNEL);
	if (!platform_class_bc12)
		return -ENOMEM;

	platform_class_bc12->dev = &pdev->dev;
	platform_class_bc12_parse_dt(platform_class_bc12);
	ret = protocol_class_register_ops(ADAPTER_PROTOCOL_BC12, &g_bc12_ops,
					  platform_class_bc12);
	if (ret)
		return ret;

	platform_set_drvdata(pdev, platform_class_bc12);
	mca_log_err("probe ok\n");
	return 0;
}

static void platform_class_bc12_remove(struct platform_device *pdev)
{
	struct platform_class_bc12_info *info = platform_get_drvdata(pdev);
	if (!info) return;
	protocol_class_unregister_ops(ADAPTER_PROTOCOL_BC12, &g_bc12_ops, info);
	platform_set_drvdata(pdev, NULL);
}

static void platform_class_bc12_shutdown(struct platform_device *pdev)
{
}

static const struct of_device_id match_table[] = {
	{ .compatible = "mca,bc12_class" },
	{},
};

static struct platform_driver platform_bc12_class_driver = {
	.driver	= {
		.owner = THIS_MODULE,
		.name = "platform_bc12_class",
		.of_match_table = match_table,
	},
	.probe = platform_class_bc12_probe,
	.remove = platform_class_bc12_remove,
	.shutdown = platform_class_bc12_shutdown,
};

static int __init platform_class_bc12_init(void)
{
	return platform_driver_register(&platform_bc12_class_driver);
}
module_init(platform_class_bc12_init);

static void __exit platform_class_bc12_exit(void)
{
	struct platform_class_bc12_ops_data *old[BC12_MAX_ROLE];
	int i;
	platform_driver_unregister(&platform_bc12_class_driver);
	mutex_lock(&g_bc12_lock);
	for (i = 0; i < BC12_MAX_ROLE; i++)
		old[i] = rcu_replace_pointer(g_bc12_ops_data[i], NULL, lockdep_is_held(&g_bc12_lock));
	mutex_unlock(&g_bc12_lock);
	synchronize_srcu(&g_bc12_srcu);
	for (i = 0; i < BC12_MAX_ROLE; i++) kfree(old[i]);
}
module_exit(platform_class_bc12_exit);

MODULE_DESCRIPTION("mca protocol class");
MODULE_AUTHOR("liyuze@xiaomi.com");
MODULE_LICENSE("GPL v2");
