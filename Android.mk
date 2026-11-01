# SPDX-License-Identifier: Apache-2.0
LOCAL_PATH := $(call my-dir)
ifeq ($(TARGET_DEVICE),myron)
include $(LOCAL_PATH)/kernel/build.mk
endif
