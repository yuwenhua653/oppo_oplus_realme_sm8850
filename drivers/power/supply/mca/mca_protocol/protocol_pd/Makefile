# SPDX-License-Identifier: GPL-2.0

obj-y += qcom_tcpc/

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/power/supply/mca/include -I$(srctree)/drivers/power/supply/mca/mca_protocol/protocol_pd
obj-$(CONFIG_MYRON_MCA_PLATFORM) += mca_protocol_pd_class.o
