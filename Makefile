# SPDX-License-Identifier: GPL-2.0
vendor := $(src)

# Match the pinned LineageOS SM8850 modules repository layout.
ifeq ($(CONFIG_ARCH_CANOE),y)
DTC_INCLUDE += \
	$(srctree)/../vendor/qcom/sm8850-modules/qcom/opensource/audio-kernel/include \
	$(srctree)/../vendor/qcom/sm8850-modules/qcom/opensource/camera-kernel \
	$(srctree)/../vendor/qcom/sm8850-modules/qcom/opensource/synx-kernel
export DTC_INCLUDE
endif

ifneq "$(wildcard $(vendor)/qcom)" ""
	subdir-y += qcom
endif
