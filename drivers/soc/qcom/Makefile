# SPDX-License-Identifier: GPL-2.0
CFLAGS_rpmh-rsc.o := -I$(src)
CFLAGS_qcom_aoss.o := -I$(src)
obj-$(CONFIG_QCOM_GENI_SE) +=	qcom-geni-se.o
obj-$(CONFIG_QCOM_GSBI)	+=	qcom_gsbi.o
obj-$(CONFIG_QCOM_OCMEM)	+= ocmem.o
obj-$(CONFIG_QCOM_PD_MAPPER)	+= qcom_pd_mapper.o
obj-$(CONFIG_QCOM_PMIC_GLINK)	+= pmic_glink.o
obj-$(CONFIG_QCOM_PMIC_GLINK)	+= pmic_glink_altmode.o
obj-$(CONFIG_QCOM_PMIC_PDCHARGER_ULOG)	+= pmic_pdcharger_ulog.o
CFLAGS_pmic_pdcharger_ulog.o	:=  -I$(src)
obj-$(CONFIG_QCOM_RAMP_CTRL)	+= ramp_controller.o
obj-$(CONFIG_QCOM_RMTFS_MEM)	+= rmtfs_mem.o
obj-$(CONFIG_QCOM_RPM_MASTER_STATS)	+= rpm_master_stats.o
obj-$(CONFIG_QCOM_SMD_RPM)	+= rpm-proc.o smd-rpm.o
obj-$(CONFIG_QCOM_SMEM_STATE) += smem_state.o
CFLAGS_smp2p.o := -I$(src)
obj-$(CONFIG_QCOM_SMSM)	+= smsm.o
obj-$(CONFIG_QCOM_SPM)		+= spm.o
obj-$(CONFIG_QCOM_STATS)	+= qcom_stats.o
obj-$(CONFIG_QCOM_WCNSS_CTRL) += wcnss_ctrl.o
obj-$(CONFIG_QCOM_APR) += apr.o
obj-$(CONFIG_QCOM_KRYO_L2_ACCESSORS) +=	kryo-l2-accessors.o
obj-$(CONFIG_QCOM_ICC_BWMON)	+= icc-bwmon.o
obj-$(CONFIG_QCOM_PBS) +=	qcom-pbs.o

obj-y += dcvs/

obj-y += mem_buf/

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/soc/qcom
obj-$(CONFIG_QTI_ALTMODE_GLINK) += altmode-glink.o
obj-$(CONFIG_QCOM_COMMAND_DB) += cmd-db.o
obj-$(CONFIG_QCOM_CPU_PHYS_LOG_MAP) += cpu_phys_log_map.o
obj-$(CONFIG_QCOM_CPUCP_FAST) += cpucp_fast.o
obj-$(CONFIG_QCOM_CRM_V2) += crm-v2.o
obj-$(CONFIG_QCOM_DEBUG_SYMBOL) += debug_symbol.o
obj-$(CONFIG_QCOM_EUD) += eud.o
obj-$(CONFIG_QCOM_FSA4480_I2C) += fsa4480_i2c.o
fsa4480_i2c-y := fsa4480-i2c.o
obj-$(CONFIG_GIC_INTERRUPT_ROUTING) += gic_intr_routing.o
obj-$(CONFIG_QCOM_LLCC) += llcc-qcom.o
obj-$(CONFIG_QCOM_MDT_LOADER) += mdt_loader.o
obj-$(CONFIG_MEM_PROT) += mem-prot.o
obj-$(CONFIG_QCOM_MEMORY_DUMP_V2) += memory_dump_v2.o
obj-$(CONFIG_QCOM_MINIDUMP) += minidump.o
minidump-y := minidump_log.o msm_minidump.o
ifneq ($(filter y m,$(CONFIG_QCOM_MINIDUMP_PANIC_MEMORY_INFO)),)
minidump-y += minidump_memory.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_MINIDUMP_SMEM)),)
minidump-y += minidump_smem.o
endif
ifneq ($(filter y m,$(CONFIG_QCOM_MINIDUMP_RM)),)
minidump-y += minidump_rm.o
endif
obj-$(CONFIG_MSM_PERFORMANCE) += msm_performance.o
obj-$(CONFIG_QCOM_PANEL_EVENT_NOTIFIER) += panel_event_notifier.o
obj-$(CONFIG_QCOM_PCIE_PDC) += pcie-pdc.o
obj-$(CONFIG_QCOM_PDR_HELPERS) += pdr_interface.o
obj-$(CONFIG_QTI_PMIC_PON_LOG) += pmic-pon-log.o
obj-$(CONFIG_QCOM_AOSS_QMP) += qcom_aoss.o
obj-$(CONFIG_QCOM_CPU_VENDOR_HOOKS) += qcom_cpu_vendor_hooks.o
obj-$(CONFIG_QCOM_CPUCP) += qcom_cpucp.o
obj-$(CONFIG_QCOM_INLINE_CRYPTO_ENGINE) += qcom_ice.o
qcom_ice-y := ice.o
obj-$(CONFIG_QCOM_LOGBUF_BOOTLOG) += qcom_logbuf_boot_log.o
obj-$(CONFIG_QCOM_LOGBUF_VENDOR_HOOKS) += qcom_logbuf_vendor_hooks.o
obj-$(CONFIG_QCOM_PDR_MSG) += qcom_pdr_msg.o
obj-$(CONFIG_QCOM_RAMDUMP) += qcom_ramdump.o
obj-$(CONFIG_QCOM_RPMH) += qcom_rpmh.o
qcom_rpmh-y := rpmh-rsc.o rpmh.o
obj-$(CONFIG_QCOM_SDEI) += qcom_sdei.o
obj-$(CONFIG_QCOM_SOC_WATCHDOG) += qcom_soc_wdt.o
obj-$(CONFIG_QCOM_VA_MINIDUMP) += qcom_va_minidump.o
obj-$(CONFIG_QCOM_WDT_CORE) += qcom_wdt_core.o
obj-$(CONFIG_QCOM_QMI_HELPERS) += qmi_helpers.o
qmi_helpers-y := qmi_encdec.o qmi_interface.o
obj-$(CONFIG_QTI_PMIC_GLINK) += qti_pmic_glink.o
obj-$(CONFIG_QCOM_SECURE_BUFFER) += secure_buffer.o
obj-$(CONFIG_QCOM_SMEM) += smem.o
obj-$(CONFIG_QCOM_SMP2P) += smp2p.o
obj-$(CONFIG_QCOM_SOCINFO) += socinfo.o
obj-$(CONFIG_QCOM_WCD_USBSS_I2C) += wcd_usbss_i2c.o
wcd_usbss_i2c-y := wcd-usbss-regmap.o wcd-usbss-tables.o wcd-usbss-utils.o wcd939x-i2c.o
