# SPDX-License-Identifier: Apache-2.0
# Every module is a declared output, even on a clean build (no wildcard on out/).
myron_kernel_image := $(MYRON_KERNEL_DIST)/Image
myron_kernel_outputs := $(addprefix $(MYRON_KERNEL_DIST)/modules/,$(MYRON_ALL_MODULES))
myron_kernel_inputs := $(wildcard $(DEVICE_PATH)/kernel/*.py $(DEVICE_PATH)/kernel/*.json $(DEVICE_PATH)/kernel/*.mk)
myron_kernel_inputs += $(wildcard $(MYRON_KERNEL_ENTRY)/*.py $(MYRON_KERNEL_ENTRY)/*.json $(MYRON_KERNEL_ENTRY)/*.bazel)

# Cheap source/output checks run on every invocation; unchanged successful builds
# are reused. Dirty source or altered output fails instead of silently mixing ABI.
.PHONY: myron-kernel-source-check
.KATI_RESTAT: $(myron_kernel_image)
$(myron_kernel_image): .KATI_IMPLICIT_OUTPUTS := $(myron_kernel_outputs)
$(myron_kernel_image): myron-kernel-source-check $(myron_kernel_inputs)
	@echo "Building/checking Redmi K90PM kernel from committed sources"
	PATH=/usr/local/bin:/usr/bin:/bin /usr/bin/python3 -B $(DEVICE_PATH)/kernel/rom_kernel.py build --entry $(MYRON_KERNEL_ENTRY) --workspace $(MYRON_KERNEL_WORKSPACE) --dist $(MYRON_KERNEL_DIST) --jobs $(MYRON_KERNEL_JOBS) --ram-mb $(MYRON_KERNEL_RAM_MB)

$(PRODUCT_OUT)/kernel: $(myron_kernel_image)
	@mkdir -p $(dir $@)
	cmp -s $< $@ || cp -f $< $@

ALL_DEFAULT_INSTALLED_MODULES += $(PRODUCT_OUT)/kernel
.PHONY: kernel
kernel: $(PRODUCT_OUT)/kernel

# Compile/assemble source DTs behind the same kernel build dependency. Unlike a
# wildcard on an empty out directory, both outputs exist in the clean Ninja graph.
myron_source_dtb := $(MYRON_SOURCE_DT_OUT)/dtb.img
myron_source_dtbo := $(MYRON_SOURCE_DT_OUT)/dtbo.img
myron_dt_tools := $(HOST_OUT_EXECUTABLES)/fdtoverlay $(HOST_OUT_EXECUTABLES)/fdtoverlaymerge $(HOST_OUT_EXECUTABLES)/fdtput $(HOST_OUT_EXECUTABLES)/mkdtboimg
.PHONY: myron-source-dt-force myron-source-dt-check
.KATI_RESTAT: $(myron_source_dtb)
$(myron_source_dtb): .KATI_IMPLICIT_OUTPUTS := $(myron_source_dtbo)
$(myron_source_dtb): $(myron_kernel_image) $(DEVICE_PATH)/kernel/source_dt.py $(DEVICE_PATH)/kernel/dt-profile.json $(myron_dt_tools) myron-source-dt-force
	/usr/bin/python3 -B $(DEVICE_PATH)/kernel/source_dt.py --full $(MYRON_KERNEL_WORKSPACE)/integration-artifacts/full --output $(MYRON_SOURCE_DT_OUT) --fdtoverlay $(HOST_OUT_EXECUTABLES)/fdtoverlay --fdtoverlaymerge $(HOST_OUT_EXECUTABLES)/fdtoverlaymerge --fdtput $(HOST_OUT_EXECUTABLES)/fdtput --mkdtboimg $(HOST_OUT_EXECUTABLES)/mkdtboimg

myron-source-dt-check: $(myron_source_dtb) $(myron_source_dtbo)

ifeq ($(MYRON_DT_MODE),source)
$(PRODUCT_OUT)/dtb.img: $(myron_source_dtb)
	@mkdir -p $(dir $@)
	cmp -s $< $@ || cp -f $< $@
# Android's existing DTBO rule supplies AVB/footer and partition-size checks.
endif
