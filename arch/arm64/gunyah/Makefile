# SPDX-License-Identifier: GPL-2.0

obj-$(CONFIG_GUNYAH_HYPERCALLS) += gunyah_hypercall.o

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/arch/arm64/gunyah
obj-$(CONFIG_GH_ARM64_DRV) += gh_arm_drv.o
gh_arm_drv-y := gh_arm.o irq.o reset.o
