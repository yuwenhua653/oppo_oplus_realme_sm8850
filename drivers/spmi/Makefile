# SPDX-License-Identifier: GPL-2.0-only
#
# Makefile for kernel SPMI framework.
#
obj-$(CONFIG_SPMI)	+= spmi.o spmi-devres.o

obj-$(CONFIG_SPMI_HISI3670)	+= hisi-spmi-controller.o
obj-$(CONFIG_SPMI_MTK_PMIF)	+= spmi-mtk-pmif.o

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/spmi
obj-$(CONFIG_SPMI_MSM_PMIC_ARB) += spmi-pmic-arb.o
