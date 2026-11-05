# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/misc/miev -I$(srctree)/include
obj-$(CONFIG_MIEV) += miev.o
miev-y := midevice.o mievent.o
