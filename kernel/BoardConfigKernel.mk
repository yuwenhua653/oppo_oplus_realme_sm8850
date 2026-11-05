# SPDX-License-Identifier: Apache-2.0
# Redmi K90PM: build Image and all installed modules from committed Kleaf sources.
MYRON_KERNEL_ENTRY := kernel/xiaomi/myron-build
MYRON_KERNEL_OUT := $(PRODUCT_OUT)/obj/MYRON_KERNEL
MYRON_KERNEL_DIST := $(MYRON_KERNEL_OUT)/dist
MYRON_KERNEL_WORKSPACE := $(MYRON_KERNEL_OUT)/workspace
MYRON_KERNEL_JOBS ?= 2
MYRON_KERNEL_RAM_MB ?= 10000

# The device Android.mk owns the kernel rule. Disable the legacy make/defconfig
# builder, not kernel compilation. No TARGET_PREBUILT_KERNEL or Image copy input.
TARGET_NO_KERNEL_OVERRIDE := true
TARGET_KERNEL_VERSION := 6.12
MYRON_KERNEL_SOURCE := $(MYRON_KERNEL_WORKSPACE)/common
# With the legacy builder disabled, TARGET_KERNEL_SOURCE is consumed only by
# generated_kernel_headers. Preserve the existing Qualcomm userspace UAPI
# export Makefile; actual Image/module sources are MYRON_KERNEL_SOURCE above.
TARGET_KERNEL_SOURCE := $(KERNEL_PATH)/kernel-headers

# Source mode is fail-closed: input/SoC-ID/provider checks must pass before the
# source images enter ROM packaging. R123 passed device functional validation;
# see DT-STATUS.md for scope and the explicit OEM fallback.
MYRON_DT_MODE ?= source
MYRON_SOURCE_DT_OUT := $(MYRON_KERNEL_OUT)/source-dt
ifeq ($(MYRON_DT_MODE),source)
BOARD_PREBUILT_DTBOIMAGE := $(MYRON_SOURCE_DT_OUT)/dtbo.img
BOARD_PREBUILT_DTBIMAGE_DIR :=
else ifeq ($(MYRON_DT_MODE),oem)
BOARD_PREBUILT_DTBOIMAGE := $(KERNEL_PATH)/dtbo.img
BOARD_PREBUILT_DTBIMAGE_DIR := $(KERNEL_PATH)/dtb
else
$(error MYRON_DT_MODE must be oem or source)
endif

include $(DEVICE_PATH)/kernel/modules.mk
BOARD_USES_SYSTEM_DLKMIMAGE := true
BOARD_USES_VENDOR_DLKMIMAGE := true
BOARD_SYSTEM_KERNEL_MODULES := $(addprefix $(MYRON_KERNEL_DIST)/modules/,$(MYRON_SYSTEM_MODULES))
BOARD_SYSTEM_KERNEL_MODULES_LOAD := false
BOARD_VENDOR_KERNEL_MODULES := $(addprefix $(MYRON_KERNEL_DIST)/modules/,$(MYRON_VENDOR_MODULES))
BOARD_VENDOR_KERNEL_MODULES_LOAD := $(MYRON_VENDOR_LOAD_MODULES)
# Retain the three TFA codec links enabled by the validated R123 loader.
BOARD_VENDOR_KERNEL_MODULES_OPTIONS_FILE := $(DEVICE_PATH)/kernel/modules.options
BOARD_VENDOR_RAMDISK_KERNEL_MODULES := $(addprefix $(MYRON_KERNEL_DIST)/modules/,$(MYRON_RAMDISK_MODULES))
BOARD_VENDOR_RAMDISK_KERNEL_MODULES_LOAD := $(MYRON_BOOT_LOAD_MODULES)
BOARD_VENDOR_RAMDISK_RECOVERY_KERNEL_MODULES_LOAD := $(MYRON_RECOVERY_LOAD_MODULES)
BOARD_RECOVERY_KERNEL_MODULES := $(addprefix $(MYRON_KERNEL_DIST)/modules/,$(MYRON_RAMDISK_MODULES))
BOARD_RECOVERY_KERNEL_MODULES_LOAD := $(MYRON_RECOVERY_LOAD_MODULES)

# The source module set exceeds the existing vendor_dlkm slot as raw ext4.
# This EROFS configuration has booted on the target device; keep the image raw.
BOARD_VENDOR_DLKMIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_VENDOR_DLKMIMAGE_EROFS_COMPRESSOR := lz4hc,9
TARGET_USERIMAGES_SPARSE_EROFS_DISABLED := true

# GKI providers are signed; stripping after signing invalidates the signature.
BOARD_DO_NOT_STRIP_VENDOR_MODULES := true
BOARD_DO_NOT_STRIP_VENDOR_RAMDISK_MODULES := true
BOARD_DO_NOT_STRIP_RECOVERY_MODULES := true
