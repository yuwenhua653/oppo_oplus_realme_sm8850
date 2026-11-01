// SPDX-License-Identifier: GPL-2.0
/* Myron SMEM battery information. Derived from the pinned Xiaomi MCA source.
 * The Myron stock ABI exports one int(void) getter and owns a 36-byte item.
 * The returned qcom_smem_get mapping is borrowed and must never be kfree'd.
 */
#include <linux/module.h>
#include <linux/types.h>
#include <linux/err.h>
#include <linux/compiler.h>
#include <linux/soc/qcom/smem.h>
#include <mca/common/mca_log.h>
#include <mca/common/mca_smem.h>

#ifndef MCA_LOG_TAG
#define MCA_LOG_TAG "mca_smem"
#endif
#define SMEM_ID_VENDOR_BATTERY_INFO 0x51
struct mca_smem_battery_info {
 u32 reserved[8];
 u32 zero_speed_start_mode;
};
static struct mca_smem_battery_info *batt_info;

int mca_qcom_smem_is_zero_speed(void)
{
 struct mca_smem_battery_info *info = READ_ONCE(batt_info);
 if (!info)
  return -ENODEV;
 return READ_ONCE(info->zero_speed_start_mode);
}
EXPORT_SYMBOL(mca_qcom_smem_is_zero_speed);

static int __init mca_qcom_smem_init(void)
{
 struct mca_smem_battery_info *info;
 size_t size = 0;
 int ret;
 ret = qcom_smem_alloc(QCOM_SMEM_HOST_ANY, SMEM_ID_VENDOR_BATTERY_INFO,
                       sizeof(*info));
 if (ret < 0 && ret != -EEXIST) {
  mca_log_err("unable to allocate battery SMEM: %d\n", ret);
  return -EPROBE_DEFER;
 }
 info = qcom_smem_get(QCOM_SMEM_HOST_ANY, SMEM_ID_VENDOR_BATTERY_INFO, &size);
 if (IS_ERR_OR_NULL(info)) {
  mca_log_err("unable to acquire battery SMEM\n");
  return -EPROBE_DEFER;
 }
 if (size < sizeof(*info))
  return -EINVAL;
 WRITE_ONCE(batt_info, info);
 return 0;
}
module_init(mca_qcom_smem_init);
static void __exit mca_qcom_smem_exit(void)
{
 WRITE_ONCE(batt_info, NULL);
}
module_exit(mca_qcom_smem_exit);
MODULE_DESCRIPTION("mca get smem info");
MODULE_AUTHOR("liuliang10@xiaomi.com");
MODULE_LICENSE("GPL v2");
