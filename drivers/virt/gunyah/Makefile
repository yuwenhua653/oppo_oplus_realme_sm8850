# SPDX-License-Identifier: GPL-2.0

obj-$(CONFIG_GUNYAH_HYPERCALLS)		+= gunyah.o

gunyah_rsc_mgr-y += rsc_mgr.o rsc_mgr_rpc.o vm_mgr.o vm_mgr_mem.o
gunyah_rsc_mgr-$(CONFIG_DMA_CMA) += vm_mgr_cma_mem.o
obj-$(CONFIG_GUNYAH) += gunyah_rsc_mgr.o gunyah_vcpu.o
obj-$(CONFIG_GUNYAH_QCOM_TRUSTED_VM) += gunyah_qtvm.o
obj-$(CONFIG_GUNYAH_PLATFORM_HOOKS) += gunyah_platform_hooks.o
obj-$(CONFIG_GUNYAH_QCOM_PLATFORM) += gunyah_qcom.o
obj-$(CONFIG_GUNYAH_IRQFD) += gunyah_irqfd.o
obj-$(CONFIG_GUNYAH_IOEVENTFD) += gunyah_ioeventfd.o

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/virt/gunyah
obj-$(CONFIG_GH_DBL) += gh_dbl.o
obj-$(CONFIG_GH_IRQ_LEND) += gh_irq_lend.o
obj-$(CONFIG_GH_MEM_NOTIFIER) += gh_mem_notifier.o
obj-$(CONFIG_GH_MSGQ) += gh_msgq.o
obj-$(CONFIG_GH_RM_DRV) += gh_rm_drv.o
gh_rm_drv-y := gh_rm_core.o gh_rm_iface.o gh_devices.o
obj-$(CONFIG_GH_RM_HEAP_MANAGER) += gh_rm_heap_manager.o
obj-$(CONFIG_GH_VCPU_MGR) += gh_vcpu_mgr.o
