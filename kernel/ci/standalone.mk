# CI-only Android variable fixture. Compile/install recipes come unchanged from
# Evolution's kernel.mk; this file is not part of the device's ROM build path.
SHELL := /bin/bash
.SHELLFLAGS := -eo pipefail -c
.DEFAULT_GOAL := ci-all
BUILD_TOP := $(CURDIR)
DEVICE_PATH := device/xiaomi/myron
PRODUCT_OUT := out/target/product/myron
TARGET_OUT_INTERMEDIATES := $(PRODUCT_OUT)/obj
HOST_OUT_EXECUTABLES := out/host/bin
KERNEL_BUILD_OUT_PREFIX := $(CURDIR)/
KERNEL_ARCH := arm64
BOARD_KERNEL_IMAGE_NAME := Image
BOARD_KERNEL_PAGESIZE := 4096
BOARD_INCLUDE_DTB_IN_BOOTIMG := true
BUILDING_VENDOR_BOOT_IMAGE := true
TARGET_KERNEL_CLANG_PATH := $(CURDIR)/toolchains/clang
KERNEL_MAKE_CMD := $(MAKE)
KERNEL_MAKE_FLAGS := -j$(shell nproc) LLVM=1 LLVM_IAS=1
KERNEL_CROSS_COMPILE := CROSS_COMPILE=aarch64-linux-gnu-
CCACHE_BIN := /usr/bin/ccache
DEPMOD := /usr/sbin/depmod
TARGET_OUT_VENDOR_DLKM := $(PRODUCT_OUT)/vendor_dlkm
TARGET_OUT_SYSTEM_DLKM := $(PRODUCT_OUT)/system_dlkm
TARGET_VENDOR_RAMDISK_OUT := $(PRODUCT_OUT)/vendor_ramdisk
TARGET_RECOVERY_ROOT_OUT := $(PRODUCT_OUT)/recovery/root
INSTALLED_KERNEL_TARGET := $(PRODUCT_OUT)/kernel
INSTALLED_DTBIMAGE_TARGET := $(PRODUCT_OUT)/dtb.img
INSTALLED_DTBOIMAGE_TARGET := $(PRODUCT_OUT)/dtbo.img
BOARD_PREBUILT_DTBOIMAGE := $(INSTALLED_DTBOIMAGE_TARGET)
INSTALLED_VENDOR_DLKMIMAGE_TARGET := $(PRODUCT_OUT)/vendor_dlkm.img
INSTALLED_SYSTEM_DLKMIMAGE_TARGET := $(PRODUCT_OUT)/system_dlkm.img
INTERNAL_VENDOR_RAMDISK_TARGET := $(PRODUCT_OUT)/vendor_ramdisk.cpio
recovery_uncompressed_ramdisk := $(PRODUCT_OUT)/recovery.cpio
vendor_dlkmimage_intermediates := $(TARGET_OUT_INTERMEDIATES)/PACKAGING/vendor_dlkm
system_dlkmimage_intermediates := $(TARGET_OUT_INTERMEDIATES)/PACKAGING/system_dlkm
intermediates-dir-for = $(TARGET_OUT_INTERMEDIATES)/$(1)/$(2)
transform-prebuilt-to-target = mkdir -p $(dir $@); cp $< $@
include $(DEVICE_PATH)/kernel/BoardConfigKernel.mk
include vendor/lineage/build/tasks/kernel.mk

$(KERNEL_MODULES_PARTITION_FILE_LIST) $(SYSTEM_KERNEL_MODULES_PARTITION_FILE_LIST):
	@mkdir -p $(dir $@)
	@touch $@

.PHONY: ci-all ci-headers ci-options
ci-all: kernel dtbimage dtboimage ci-headers ci-options

ci-headers: $(INSTALLED_KERNEL_TARGET)
	$(call make-kernel-target,headers_install INSTALL_HDR_PATH=$(CURDIR)/out/headers)

# Android normally handles this device.mk PRODUCT_COPY_FILES entry. Only copy
# this one data file here; boot images/AVB/Soong are outside this fixture's scope.
ci-options: $(INSTALLED_KERNEL_TARGET) $(DEVICE_PATH)/kernel/modules.options
	cp $(DEVICE_PATH)/kernel/modules.options $(TARGET_OUT_VENDOR_DLKM)/lib/modules/modules.options
