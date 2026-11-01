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
