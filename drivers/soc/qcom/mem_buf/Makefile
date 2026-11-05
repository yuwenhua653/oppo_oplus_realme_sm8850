# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/soc/qcom/mem_buf
obj-$(CONFIG_QCOM_MEM_BUF) += mem_buf.o
mem_buf-y := mem-buf.o
ifneq ($(filter y m,$(CONFIG_QCOM_MEM_BUF_GH)),)
mem_buf-y += mem-buf-gh.o
endif
obj-$(CONFIG_QCOM_MEM_BUF_DEV) += mem_buf_dev.o
mem_buf_dev-y := mem-buf-dev.o mem-buf-ids.o mem_buf_dma_buf.o
ifneq ($(filter y m,$(CONFIG_QCOM_MEM_BUF_DEV_GH)),)
mem_buf_dev-y += mem-buf-dev-gh.o
endif
obj-$(CONFIG_QCOM_MEM_BUF_MSGQ) += mem_buf_msgq.o
mem_buf_msgq-y := mem-buf-msgq.o
