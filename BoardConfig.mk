#
# Copyright (C) 2026 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#

DEVICE_PATH := device/xiaomi/myron
KERNEL_PATH := kernel/xiaomi/myron-prebuilt

# Inherit from sm8850-common
include device/xiaomi/sm8850-common/BoardConfigCommon.mk

# Inherit miuicam
include device/xiaomi/myron-miuicamera/BoardConfig.mk

# Display
TARGET_SCREEN_DENSITY := 520

# Source-built kernel and matching modules (device-owned Kleaf rule).
include $(DEVICE_PATH)/kernel/BoardConfigKernel.mk

TARGET_ODM_PROP += $(DEVICE_PATH)/configs/properties/odm.prop
TARGET_VENDOR_PROP += $(DEVICE_PATH)/configs/properties/vendor.prop

# Platform
BOOT_SECURITY_PATCH := $(PLATFORM_SECURITY_PATCH)
VENDOR_SECURITY_PATCH := $(PLATFORM_SECURITY_PATCH)

# Inherit from the proprietary version
include vendor/xiaomi/myron/BoardConfigVendor.mk
