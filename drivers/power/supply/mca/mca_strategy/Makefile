# SPDX-License-Identifier: GPL-2.0

obj-y += strategy_charger/

obj-y += strategy_fg/

obj-y += strategy_pd/

obj-y += strategy_wireless/

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/misc/hwid -I$(srctree)/drivers/power/supply/mca/include -I$(srctree)/drivers/power/supply/mca/mca_strategy -I$(srctree)/include
obj-$(CONFIG_MYRON_MCA_SERVICES) += mca_strategy_class.o
