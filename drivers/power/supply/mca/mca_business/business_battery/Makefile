# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/misc/hwid -I$(srctree)/drivers/power/supply/mca/include -I$(srctree)/drivers/power/supply/mca/mca_business/business_battery -I$(srctree)/include
obj-$(CONFIG_MYRON_MCA_SERVICES) += mca_business_battery_comp.o
mca_business_battery_comp-y := mca_business_battery.o mca_battery_psy.o
