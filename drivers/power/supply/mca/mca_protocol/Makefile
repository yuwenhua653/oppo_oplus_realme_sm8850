# SPDX-License-Identifier: GPL-2.0

obj-y += protocol_pd/

obj-y += protocol_qc/

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/power/supply/mca/include -I$(srctree)/drivers/power/supply/mca/mca_protocol
obj-$(CONFIG_MYRON_MCA_PLATFORM) += mca_protocol_class.o
