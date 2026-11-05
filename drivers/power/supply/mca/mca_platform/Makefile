# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/misc/hwid -I$(srctree)/drivers/power/supply/mca/include -I$(srctree)/drivers/power/supply/mca/mca_platform -I$(srctree)/include
obj-$(CONFIG_MYRON_MCA_PLATFORM) += mca_platform_bc12_class.o
obj-$(CONFIG_MYRON_MCA_PLATFORM) += mca_platform_buckchg_class.o
obj-$(CONFIG_MYRON_MCA_PLATFORM) += mca_platform_cp_class.o
obj-$(CONFIG_MYRON_MCA_PLATFORM) += mca_platform_fg_ic_ops.o
obj-$(CONFIG_MYRON_MCA_PLATFORM) += mca_platform_loadsw_class.o
obj-$(CONFIG_MYRON_MCA_SERVICES) += mca_platform_wireless_class.o
