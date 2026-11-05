# SPDX-License-Identifier: GPL-2.0
obj-$(CONFIG_DMABUF_HEAPS_SYSTEM)	+= system_heap.o
obj-$(CONFIG_DMABUF_HEAPS_CMA)		+= cma_heap.o

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/dma-buf/heaps
obj-$(CONFIG_QCOM_DMABUF_HEAPS_DEFERRED_FREE) += deferred-free-helper.o
obj-$(CONFIG_QCOM_DMABUF_HEAPS) += qcom_dma_heaps.o
qcom_dma_heaps-y := qcom_dma_heap.o qcom_dt_parser.o qcom_sg_ops.o
ifneq ($(filter y m,$(CONFIG_QCOM_DMABUF_HEAPS_SYSTEM)),)
qcom_dma_heaps-y += qcom_system_heap.o qcom_dynamic_page_pool.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_DMABUF_HEAPS_SYSTEM_SECURE)),)
qcom_dma_heaps-y += qcom_secure_system_heap.o qcom_dynamic_page_pool.o qcom_dma_heap_secure_utils.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_DMABUF_HEAPS_CMA)),)
qcom_dma_heaps-y += qcom_cma_heap.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_DMABUF_HEAPS_CARVEOUT)),)
qcom_dma_heaps-y += qcom_carveout_heap.o qcom_dma_heap_secure_utils.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_DMABUF_HEAPS_UBWCP)),)
qcom_dma_heaps-y += qcom_ubwcp_heap.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_DMABUF_HEAPS_TVM_CARVEOUT)),)
qcom_dma_heaps-y += qcom_tvm_carveout_heap.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_DMABUF_HEAPS_SYSTEM_MOVABLE)),)
qcom_dma_heaps-y += qcom_system_movable_heap.o
endif
