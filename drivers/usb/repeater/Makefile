# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/usb/repeater
obj-$(CONFIG_USB_REPEATER) += repeater.o
obj-$(CONFIG_QTI_PMIC_EUSB2_REPEATER) += repeater-qti-pmic-eusb2.o
