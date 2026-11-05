# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/misc/hwid -I$(srctree)/drivers/power/supply/mca/include -I$(srctree)/drivers/power/supply/mca/mca_common -I$(srctree)/include
obj-$(CONFIG_MYRON_MCA_SERVICES) += mca_adsp_glink.o
obj-$(CONFIG_MYRON_MCA_INTERFACE) += mca_charge_interface.o
obj-$(CONFIG_MYRON_MCA_PLATFORM) += mca_charge_mievent.o
obj-$(CONFIG_MYRON_MCA_BASE) += mca_event.o
obj-$(CONFIG_MYRON_MCA_BASE) += mca_hwid.o
obj-$(CONFIG_MYRON_MCA_BASE) += mca_log.o
obj-$(CONFIG_MYRON_MCA_BASE) += mca_parse_dts.o
obj-$(CONFIG_MYRON_MCA_PLATFORM) += mca_qcom_smem.o
obj-$(CONFIG_MYRON_MCA_BASE) += mca_sysfs.o
obj-$(CONFIG_MYRON_MCA_BASE) += mca_voter.o
obj-$(CONFIG_MYRON_MCA_BASE) += mca_workqueue.o
