# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/power/supply/myron_mca_readonly -I$(srctree)/include
obj-$(CONFIG_MYRON_MCA_READONLY) += myron_mca_readonly.o
