# SPDX-License-Identifier: GPL-2.0
obj-$(CONFIG_QCOM_IOMMU) += qcom_iommu.o

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/iommu/arm/arm-smmu
obj-$(CONFIG_ARM_SMMU) += arm_smmu.o
arm_smmu-y := arm-smmu-impl.o arm-smmu.o
ifneq ($(filter y m,$(CONFIG_ARM_SMMU_QCOM)),)
arm_smmu-y += arm-smmu-qcom.o arm-smmu-qcom-pm.o
endif
ifneq ($(filter y m,$(CONFIG_ARM_SMMU_QCOM_DEBUG)),)
arm_smmu-y += arm-smmu-qcom-debug.o
endif
ifneq ($(filter y m,$(CONFIG_ARM_SMMU_NVIDIA)),)
arm_smmu-y += arm-smmu-nvidia.o
endif
