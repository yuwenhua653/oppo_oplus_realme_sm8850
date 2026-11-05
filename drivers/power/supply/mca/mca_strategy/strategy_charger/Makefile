# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/misc/hwid -I$(srctree)/drivers/power/supply/mca/include -I$(srctree)/drivers/power/supply/mca/mca_strategy/strategy_charger -I$(srctree)/include
obj-$(CONFIG_MYRON_MCA_COMPLETE_SERVICES) += mca_buckchg_jeita.o
obj-$(CONFIG_MYRON_MCA_COMPLETE_SERVICES) += mca_charger_thermal.o
obj-$(CONFIG_MYRON_MCA_COMPLETE_SERVICES) += mca_strategy_buckchg.o
obj-$(CONFIG_MYRON_MCA_COMPLETE_SERVICES) += mca_strategy_quickchg.o
