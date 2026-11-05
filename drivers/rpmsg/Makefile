# SPDX-License-Identifier: GPL-2.0
obj-$(CONFIG_RPMSG)		+= rpmsg_core.o
obj-$(CONFIG_RPMSG_CHAR)	+= rpmsg_char.o
obj-$(CONFIG_RPMSG_CTRL)	+= rpmsg_ctrl.o
obj-$(CONFIG_RPMSG_NS)		+= rpmsg_ns.o
obj-$(CONFIG_RPMSG_MTK_SCP)	+= mtk_rpmsg.o
CFLAGS_qcom_glink_native.o	:= -I$(src)
obj-$(CONFIG_RPMSG_QCOM_GLINK_RPM) += qcom_glink_rpm.o
obj-$(CONFIG_RPMSG_VIRTIO)	+= virtio_rpmsg_bus.o

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/rpmsg
obj-$(CONFIG_QCOM_GLINK_PKT) += glink_pkt.o
obj-$(CONFIG_RPMSG_QCOM_GLINK) += qcom_glink.o
qcom_glink-y := qcom_glink_memshare.o qcom_glink_native.o qcom_glink_ssr.o
obj-$(CONFIG_RPMSG_QCOM_GLINK_SMEM) += qcom_glink_smem.o
obj-$(CONFIG_RPMSG_QCOM_SMD) += qcom_smd.o
