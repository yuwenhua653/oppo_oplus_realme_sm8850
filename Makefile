# SPDX-License-Identifier: GPL-2.0
vendor := $(src)

# Standard sibling source layout used by the Android kernel build rules.
DTC_INCLUDE += \
	$(srctree)/include \
	$(srctree)/../sm8850-modules/qcom/opensource/audio-kernel/include \
	$(srctree)/../sm8850-modules/qcom/opensource/camera-kernel \
	$(srctree)/../sm8850-modules/qcom/opensource/synx-kernel \
	$(vendor)/qcom
export DTC_INCLUDE
DTC_FLAGS += -@
export DTC_FLAGS

ifneq ($(wildcard $(vendor)/qcom),)
subdir-y += qcom
endif
