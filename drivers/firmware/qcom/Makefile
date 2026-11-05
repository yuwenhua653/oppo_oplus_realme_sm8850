# SPDX-License-Identifier: GPL-2.0
#
# Makefile for the linux kernel.
#

# The platform SCM module includes qcom_tzmem.o below.
obj-$(CONFIG_QCOM_QSEECOM)	+= qcom_qseecom.o
obj-$(CONFIG_QCOM_QSEECOM_UEFISECAPP) += qcom_qseecom_uefisecapp.o

obj-y += si_core/

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/firmware/qcom -I$(srctree)/include/linux
obj-$(CONFIG_QCOM_SCM) += qcom-scm.o
qcom-scm-y := qcom_scm-legacy.o qcom_scm-smc.o qcom_scm.o
ifneq ($(filter y m,$(CONFIG_QTEE_SHM_BRIDGE)),)
qcom-scm-y += qtee_shmbridge.o
endif
ifneq ($(filter y m,$(CONFIG_MSM_HAB)),)
qcom-scm-y += qcom_scm_hab.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_TZMEM)),)
qcom-scm-y += qcom_tzmem.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_TZMEM_FFA)),)
qcom-scm-y += qcom_tzmem_ffa.o
endif
ifeq ($(filter y m,$(CONFIG_QCOM_SCM_SMCI)),)
qcom-scm-y += qcom_scm-scm.o
endif
