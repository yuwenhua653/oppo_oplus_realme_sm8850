# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/firmware/qcom/si_core
obj-$(CONFIG_QCOM_SI_CORE) += si_core_module.o
si_core_module-y := si_core.o si_core_async.o si_core_helpers.o xts/mem-object.o
ifneq ($(filter y m,$(CONFIG_QCOM_SCM_INVOKE_LEGACY)),)
si_core_module-y += qcom_scm_invoke_legacy.o
endif
ifeq ($(filter y m,$(CONFIG_QCOM_SCM_INVOKE_LEGACY)),)
si_core_module-y += qcom_scm_invoke.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_SI_CORE_ADCI)),)
si_core_module-y += si_core_adci.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_SI_CORE_WQ)),)
si_core_module-y += si_core_wq.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_SI_CORE_MEM_FFA)),)
si_core_module-y += si_core_ffa.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_SI_CORE_DOORBELL)),)
si_core_module-y += si_core_doorbell.o
endif
ccflags-y += -I$(src)/xts
