# SPDX-License-Identifier: GPL-2.0-only

obj-$(CONFIG_QRTR_TUN) += qrtr-tun.o
qrtr-tun-y	:= tun.o

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/net/qrtr
obj-$(CONFIG_QRTR) += qrtr.o
qrtr-y := af_qrtr.o ns.o
obj-$(CONFIG_QRTR_MHI) += qrtr-mhi.o
qrtr-mhi-y := mhi.o
obj-$(CONFIG_QRTR_SMD) += qrtr-smd.o
qrtr-smd-y := smd.o
