# SPDX-License-Identifier: Apache-2.0
# Standard LineageOS/Evolution native kernel integration.
TARGET_KERNEL_SOURCE := kernel/xiaomi/sm8850
TARGET_KERNEL_VERSION := 6.12
TARGET_KERNEL_CONFIG := \
    gki_defconfig \
    vendor/canoe_GKI.config \
    vendor/myron_GKI.config

TARGET_KERNEL_EXT_MODULE_ROOT := kernel/xiaomi/sm8850-modules
TARGET_KERNEL_EXT_MODULES := \
    qcom/opensource/mm-drivers/msm_ext_display \
    qcom/opensource/mm-drivers/hfi_core \
    qcom/opensource/mm-drivers/hw_fence \
    qcom/opensource/mm-drivers/sync_fence \
    qcom/opensource/audio-kernel \
    qcom/opensource/dsp-kernel \
    qcom/opensource/mmrm-driver \
    qcom/opensource/synx-kernel \
    qcom/opensource/securemsm-kernel \
    qcom/opensource/datarmnet-ext/mem \
    qcom/opensource/dataipa \
    qcom/opensource/datarmnet \
    qcom/opensource/datarmnet-ext/shs \
    qcom/opensource/datarmnet-ext/perf \
    qcom/opensource/data-kernel/drivers/smem-mailbox \
    nxp/opensource/driver \
    qcom/opensource/camera-kernel \
    qcom/opensource/graphics-kernel \
    qcom/opensource/display-drivers \
    qcom/opensource/eva-kernel \
    qcom/opensource/wlan/platform \
    qcom/opensource/bt-kernel \
    qcom/opensource/wlan/qcacld-3.0

# Preserve the validated partition/load lists. kernel.mk owns installation.
include $(DEVICE_PATH)/kernel/modules.mk
SYSTEM_KERNEL_MODULES := $(MYRON_SYSTEM_MODULES)
BOOT_KERNEL_MODULES := $(MYRON_RAMDISK_MODULES)
RECOVERY_KERNEL_MODULES := $(MYRON_RAMDISK_MODULES)
BOARD_SYSTEM_KERNEL_MODULES_LOAD := false
BOARD_VENDOR_KERNEL_MODULES_LOAD := $(MYRON_VENDOR_LOAD_MODULES)
BOARD_VENDOR_RAMDISK_KERNEL_MODULES_LOAD := $(MYRON_BOOT_LOAD_MODULES)
BOARD_VENDOR_RAMDISK_RECOVERY_KERNEL_MODULES_LOAD := $(MYRON_RECOVERY_LOAD_MODULES)
BOARD_RECOVERY_KERNEL_MODULES_LOAD := $(MYRON_RECOVERY_LOAD_MODULES)
BOARD_USES_SYSTEM_DLKMIMAGE := true
BOARD_USES_VENDOR_DLKMIMAGE := true

# DT compilation uses the normal dtbs target. Image assembly retains the
# device-validated IDs, provider checks and FastRPC child ordering.
TARGET_NEEDS_DTBOIMAGE := true
TARGET_KERNEL_DTB := dtbs
BOARD_CUSTOM_DTBIMG_MK := $(DEVICE_PATH)/kernel/dtb.mk
BOARD_CUSTOM_DTBOIMG_MK := $(DEVICE_PATH)/kernel/dtbo.mk

BOARD_VENDOR_DLKMIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_VENDOR_DLKMIMAGE_EROFS_COMPRESSOR := lz4hc,9
TARGET_USERIMAGES_SPARSE_EROFS_DISABLED := true
