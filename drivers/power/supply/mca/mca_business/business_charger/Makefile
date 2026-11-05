# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/misc/hwid -I$(srctree)/drivers/power/supply/mca/include -I$(srctree)/drivers/power/supply/mca/mca_business/business_charger -I$(srctree)/include
obj-$(CONFIG_MYRON_MCA_COMPLETE_SERVICES) += mca_business_charger_comp.o
mca_business_charger_comp-y := mca_business_charger.o mca_charger_usb_psy.o mca_charger_wireless_psy.o
