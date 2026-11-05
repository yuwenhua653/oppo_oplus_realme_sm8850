# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/soc/qcom/dcvs
obj-$(CONFIG_QCOM_DCVS_FP) += dcvs_fp.o
obj-$(CONFIG_QCOM_DCVS) += qcom-dcvs.o
qcom-dcvs-y := dcvs.o dcvs_epss.o dcvs_icc.o trace-dcvs.o
obj-$(CONFIG_QCOM_PMU_LIB) += qcom-pmu-lib.o
qcom-pmu-lib-y := pmu_lib.o
obj-$(CONFIG_QTI_QCOM_SCMI_CLIENT) += qcom_scmi_client.o
