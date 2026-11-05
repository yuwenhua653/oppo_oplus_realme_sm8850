# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/usb/redriver
obj-$(CONFIG_USB_REDRIVER_NB7VPQ904M) += nb7vpq904m.o
obj-$(CONFIG_USB_REDRIVER) += redriver.o
