# SPDX-License-Identifier: Apache-2.0
# Invoked through kernel.mk's standard BOARD_CUSTOM_DTBIMG_MK hook.
# All compilation is delegated to make-kernel-config/make-dtb-target.
myron_dt_sources := $(shell find -H kernel/xiaomi/sm8850-devicetrees \
    kernel/xiaomi/sm8850/include/dt-bindings \
    kernel/xiaomi/sm8850-modules/qcom/opensource/audio-kernel/include \
    kernel/xiaomi/sm8850-modules/qcom/opensource/camera-kernel \
    kernel/xiaomi/sm8850-modules/qcom/opensource/synx-kernel \
    -type f \( -name '*.dts' -o -name '*.dtsi' -o -name '*.dtso' -o -name '*.h' -o -name 'Makefile*' \))

$(INSTALLED_DTBIMAGE_TARGET): $(ALL_KERNEL_DEFCONFIG_SRCS) $(myron_dt_sources) \
    $(DEVICE_PATH)/kernel/source_dt.py $(DEVICE_PATH)/kernel/dt-profile.json \
    $(DTC) $(HOST_OUT_EXECUTABLES)/fdtoverlay $(HOST_OUT_EXECUTABLES)/fdtoverlaymerge \
    $(HOST_OUT_EXECUTABLES)/fdtput $(HOST_OUT_EXECUTABLES)/mkdtboimg
	@mkdir -p $(DTB_OUT) $(dir $@)
	$(call make-kernel-config,$(DTB_OUT),$(ALL_KERNEL_DEFCONFIG_SRCS))
	$(call make-dtb-target,dtbs)
	PATH=$(abspath $(HOST_OUT_EXECUTABLES)):$$PATH python3 $(DEVICE_PATH)/kernel/source_dt.py \
	    --dtbs $(DTB_OUT)/arch/$(KERNEL_ARCH)/boot/dts/vendor \
	    --output $(DTB_OUT)/myron-images
	cp $(DTB_OUT)/myron-images/dtb.img $@
