# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/eom
obj-$(CONFIG_EOM_MSM) += eom_driver.o
eom_driver-y := phy_core.o eom_driver_main.o buffer_manager.o
ifneq ($(filter y m,$(CONFIG_ARCH_CANOE)),)
eom_driver-y += pcie_eom_canoe_phy.o
endif
ifneq ($(filter y m,$(CONFIG_ARCH_SERAPH)),)
eom_driver-y += pcie_eom_seraph_phy.o
endif
ifneq ($(filter y m,$(CONFIG_ARCH_X1E80100)),)
eom_driver-y += pcie_eom_hamoa_phy.o
endif
