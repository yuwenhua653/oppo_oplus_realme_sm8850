
obj-$(CONFIG_MHI_BUS_PCI_GENERIC) += mhi_pci_generic.o
mhi_pci_generic-y += pci_generic.o

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/bus/mhi/host
obj-$(CONFIG_MHI_BUS) += mhi.o
mhi-y := boot.o init.o main.o pm.o
ifneq ($(filter y m,$(CONFIG_MHI_BUS_MISC)),)
mhi-y += misc.o
endif
ifneq ($(filter y m,$(CONFIG_MHI_BUS_DEBUG)),)
mhi-y += debugfs.o
endif
