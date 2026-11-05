# SPDX-License-Identifier: GPL-2.0-only
scmi-bus-y = bus.o
scmi-core-objs := $(scmi-bus-y)

scmi-driver-y = driver.o notify.o
scmi-driver-$(CONFIG_ARM_SCMI_RAW_MODE_SUPPORT) += raw_mode.o
scmi-transport-$(CONFIG_ARM_SCMI_HAVE_SHMEM) = shmem.o
scmi-transport-$(CONFIG_ARM_SCMI_HAVE_MSG) += msg.o
scmi-protocols-y := base.o clock.o perf.o power.o reset.o sensors.o system.o voltage.o powercap.o
scmi-protocols-y += pinctrl.o
scmi-module-objs := $(scmi-driver-y) $(scmi-protocols-y) $(scmi-transport-y)

obj-$(CONFIG_ARM_SCMI_PROTOCOL) += transports/
obj-$(CONFIG_ARM_SCMI_PROTOCOL) += vendors/imx/

obj-$(CONFIG_ARM_SCMI_PROTOCOL) += scmi-core.o
obj-$(CONFIG_ARM_SCMI_PROTOCOL) += scmi-module.o

obj-$(CONFIG_ARM_SCMI_POWER_CONTROL) += scmi_power_control.o

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/firmware/arm_scmi
obj-$(CONFIG_QTI_SCMI_VENDOR_PROTOCOL) += qcom_scmi_vendor.o
