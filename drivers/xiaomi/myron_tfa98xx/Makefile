# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/xiaomi/myron_tfa98xx -I$(srctree)/drivers/xiaomi/myron_tfa98xx/inc
obj-$(CONFIG_MYRON_TFA98XX) += tfa98xx_dlkm.o
tfa98xx_dlkm-y := src/tfa98xx.o src/tfa_container.o src/tfa_dsp.o src/tfa_init.o
