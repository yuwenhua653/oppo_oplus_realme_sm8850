# SPDX-License-Identifier: GPL-2.0-only

obj-$(CONFIG_QCOM_SPMI_ADC_TM5)	+= qcom-spmi-adc-tm5.o
obj-$(CONFIG_QCOM_SPMI_TEMP_ALARM)	+= qcom-spmi-temp-alarm.o
obj-$(CONFIG_QCOM_LMH)		+= lmh.o

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/thermal/qcom
obj-$(CONFIG_QTI_BCL_PMIC5) += bcl_pmic5.o
bcl_pmic5-y := qti_bcl_pmic5.o qti_bcl_stats.o
obj-$(CONFIG_QTI_CPU_HOTPLUG_COOLING_DEVICE) += cpu_hotplug.o
obj-$(CONFIG_QCOM_TSENS) += qcom_tsens.o
qcom_tsens-y := tsens-8960.o tsens-v0_1.o tsens-v1.o tsens-v2.o tsens.o
obj-$(CONFIG_QTI_CPU_PAUSE_COOLING_DEVICE) += thermal_pause.o
