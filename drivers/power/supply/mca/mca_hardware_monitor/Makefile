# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/misc/hwid -I$(srctree)/drivers/power/supply/mca/include -I$(srctree)/drivers/power/supply/mca/mca_hardware_monitor -I$(srctree)/include
obj-$(CONFIG_MYRON_MCA_SERVICES) += mca_bmd.o
obj-$(CONFIG_MYRON_MCA_SERVICES) += mca_connector_antiburn.o
obj-$(CONFIG_MYRON_MCA_SERVICES) += mca_ibat_ocp_monitor.o
obj-$(CONFIG_MYRON_MCA_SERVICES) += mca_lpd_detect.o
obj-$(CONFIG_MYRON_MCA_SERVICES) += mca_path_control.o
obj-$(CONFIG_MYRON_MCA_SERVICES) += mca_vbat_ovp_monitor.o
