#!/vendor/bin/sh
# R36 read-only observations; subshell preserves the original loader state.
(
    r36_build=R36-NORMAL-HANDOFF-20261013-01
    r36_stage=${1-unavailable}
    r36_boot_id=unavailable
    r36_status=complete
    r36_emit() {
        printf 'R36_POSTROOT build_id=%s stage=%s boot_id=%s event=%s %s\n' \
            "$r36_build" "$r36_stage" "$r36_boot_id" "$1" "$2"
    }
    r36_fail() {
        r36_status=partial
        r36_emit OBS_FAIL "source=$1 reason=$2"
    }
    if [ -r /proc/sys/kernel/random/boot_id ]; then
        IFS= read -r r36_boot_id < /proc/sys/kernel/random/boot_id || r36_boot_id=unavailable
    fi
    case "$r36_boot_id" in
        ????????-????-????-????-????????????)
            case "$r36_boot_id" in *[!0-9a-f-]*) r36_boot_id=unavailable ;; esac ;;
        *) r36_boot_id=unavailable ;;
    esac
    r36_emit BEGIN 'protocol=1'
    [ "$r36_boot_id" != unavailable ] || r36_fail /proc/sys/kernel/random/boot_id unreadable_or_invalid
    r36_observe_file() {
        r36_source=$1
        if [ ! -r "$r36_source" ]; then
            r36_fail "$r36_source" unreadable
            return 0
        fi
        r36_lines=0
        r36_bytes=0
        r36_line=
        while IFS= read -r r36_line || [ -n "$r36_line" ]; do
            r36_lines=$((r36_lines + 1))
            r36_bytes=$((r36_bytes + ${#r36_line} + 1))
            if [ "$r36_lines" -gt 512 ] || [ "${#r36_line}" -gt 8192 ] || [ "$r36_bytes" -gt 262144 ]; then
                r36_fail "$r36_source" output_limit_truncated
                break
            fi
            r36_emit OBS "source=$r36_source data=$r36_line"
        done < "$r36_source" || r36_fail "$r36_source" read_error
        [ "$r36_lines" -gt 0 ] || r36_fail "$r36_source" empty
        return 0
    }
    for r36_source in /proc/cmdline /proc/bootconfig /proc/mounts /proc/self/mountinfo \
        /system_dlkm/r32-build-id /vendor_dlkm/r32/build-id \
        /proc/1/attr/current /proc/self/attr/current; do
        r36_observe_file "$r36_source"
    done
    r36_hash_tool=
    for r36_candidate in /vendor/bin/toybox_vendor /vendor/bin/toybox /system/bin/toybox; do
        if [ -x "$r36_candidate" ] && "$r36_candidate" sha256sum --help >/dev/null 2>&1; then
            r36_hash_tool=$r36_candidate
            break
        fi
    done
    for r36_source in /system/etc/init/hw/init.rc /vendor_dlkm/r32/init.rc /vendor_dlkm/r32/overrides.rc; do
        if [ -z "$r36_hash_tool" ]; then
            r36_fail "$r36_source" sha256sum_unavailable
        elif [ ! -r "$r36_source" ]; then
            r36_fail "$r36_source" unreadable
        elif r36_hash_line=$("$r36_hash_tool" sha256sum "$r36_source" 2>/dev/null); then
            r36_emit OBS "source=$r36_source data=sha256sum $r36_hash_line"
        else
            r36_fail "$r36_source" sha256sum_failed
        fi
    done
    r36_emit END "status=$r36_status"
    exit 0
)
# End R36 observations. R32/R43 loader with R53/R54 audited module additions follows.
# Generated R32 restricted normal-boot trial loader. No policy or property bypass.
# The two read-only ext4 image digests are authenticated by PID 1 bootstrap.
# R54 selects 213 modules; module Live state is not full hardware readiness.
set -u
PATH=/vendor/bin:/system/bin
export PATH
TAG=R32-MODULES
say() { printf '%s %s\n' "$TAG" "$*"; }
fail() { say "FAIL $*"; exit 1; }
live() {
    while read -r mn msize mrefs mdeps mstate maddr mextra; do
        if [ "$mn" = "$1" ]; then [ "$mstate" = Live ]; return; fi
    done < /proc/modules
    return 1
}
require_live() { live "$1" || fail "not-Live $1"; }
choose_timeout() {
    for timeout_candidate in /vendor/bin/toybox_vendor /vendor/bin/toybox /system/bin/toybox; do
        [ -x "$timeout_candidate" ] || continue
        "$timeout_candidate" insmod --help >/dev/null 2>&1 || continue
        # Android Toybox timeout --help can return ARGFAIL=125 even when usable.
        # Run only its no-op true applet; never load a module during this probe.
        if "$timeout_candidate" timeout -k 2 1 "$timeout_candidate" true >/dev/null 2>&1; then
            TIMEOUT=$timeout_candidate
            return 0
        fi
    done
    fail 'timeout/insmod applet unavailable; no module attempted'
}
load_one() {
    lm_name=$1; lm_dir=$2; lm_file=$3; shift 3
    # A module from this runtime group may not silently have been preloaded.
    live "$lm_name" && fail "unexpected already-Live runtime module $lm_name"
    say "BEGIN $lm_name"
    "$TIMEOUT" timeout -k 2 20 "$TIMEOUT" insmod "$lm_dir/$lm_file" "$@"
    lm_rc=$?
    [ "$lm_rc" -eq 0 ] || fail "insmod $lm_name rc=$lm_rc; no retry"
    require_live "$lm_name"
    say "LIVE $lm_name"
}
wait_firmware() {
    fw_wait=0
    while [ "$fw_wait" -lt 40 ]; do
        if [ -r /vendor/firmware/gen80200_aqe.fw ] &&
           [ -r /vendor/firmware/gen80200_sqe.fw ] &&
           [ -r /vendor/firmware/gen80200_gmu.bin ] &&
           [ -r /odm/firmware/gen80200_zap.mbn ]; then
            say 'normal GPU firmware paths readable; stock ueventd firmware routing retained'
            return 0
        fi
        sleep 1 || fail 'firmware wait sleep failed'
        fw_wait=$((fw_wait + 1))
    done
    fail 'normal GPU firmware paths unavailable after 40s'
}
[ "$#" -eq 1 ] || fail 'expected gki or vendor stage'
[ -r /proc/modules ] || fail 'proc modules unreadable'
choose_timeout
case "$1" in
gki)
    require_live iommu_logger
    require_live qcom_scm
    require_live qcom_iommu_util
    require_live arm_smmu
    require_live arm_smmu_pmu
    require_live debug_symbol
    require_live deferred_free_helper
    require_live gh_arm_drv
    require_live gh_dbl
    require_live gh_msgq
    require_live secure_buffer
    require_live gh_rm_drv
    require_live gh_mem_notifier
    require_live mem_prot
    require_live gh_rm_heap_manager
    require_live mem_buf_dev
    require_live msm_dma_iommu_mapping
    require_live qcom_dma_heaps
    require_live qcom_hwspinlock
    require_live smem
    require_live minidump
    require_live qcom_ipc_logging
    require_live bcl_pmic5
    require_live crm_v2
    require_live debug_regulator
    require_live proxy_consumer
    require_live gdsc_regulator
    require_live icc_clk
    require_live clk_qcom
    require_live cambistmclkcc_canoe
    require_live camcc_alor
    require_live camcc_canoe
    require_live clk_dummy
    require_live cmd_db
    require_live qcom_rpmh
    require_live clk_rpmh
    require_live clk_scmi
    require_live cpu_hotplug
    require_live cpu_phys_log_map
    require_live qcom_cpucp
    require_live qcom_scmi_vendor
    require_live qcom_scmi_client
    require_live socinfo
    require_live sched_walt
    require_live cpucp_fast
    require_live cqhci
    require_live dcvs_fp
    require_live debugcc_canoe
    require_live dispcc_canoe
    require_live eud
    require_live phy_generic
    require_live phy_msm_snps_hs
    require_live eom_driver
    require_live phy_msm_ssusb_qmp
    require_live redriver
    require_live repeater
    require_live qti_regmap_debugfs
    require_live wcd_usbss_i2c
    require_live dwc3_msm
    require_live evacc_canoe
    require_live gcc_alor
    require_live gcc_canoe
    require_live gh_vcpu_mgr
    require_live gic_intr_routing
    require_live gpucc_canoe
    require_live hwid
    require_live msm_gpi
    require_live i2c_msm_geni
    require_live icc_bcm_voter
    require_live icc_debug
    require_live icc_rpmh
    require_live llcc_qcom
    require_live mdt_loader
    require_live mem_buf_msgq
    require_live mem_buf
    require_live memory_dump_v2
    require_live miev
    require_live qcom_aoss
    require_live msm_qmp
    require_live nb7vpq904m
    require_live nvmem_qcom_spmi_sdam
    require_live qmi_helpers
    require_live qcom_pdr_msg
    require_live qcom_glink
    require_live qcom_glink_smem
    require_live qcom_smd
    require_live rproc_qcom_common
    require_live pdr_interface
    require_live phy_msm_m31_eusb2
    require_live phy_qcom_ufs
    require_live phy_qcom_ufs_qmp_v4_canoe
    require_live phy_qcom_ufs_qrbtc_sdm845
    require_live qcom_pdc
    require_live pinctrl_msm
    require_live pinctrl_alor
    require_live pinctrl_canoe
    require_live pinctrl_chora
    require_live pinctrl_spmi_gpio
    require_live pmic_pon_log
    require_live qcom_cpu_vendor_hooks
    require_live qcom_dcvs
    require_live qcom_dload_mode
    require_live qcom_ice
    require_live qcom_iommu_debug
    require_live qcom_ipcc
    require_live qcom_llcc_pmu
    require_live qcom_logbuf_boot_log
    require_live qcom_logbuf_vendor_hooks
    require_live qcom_pil_info
    require_live qcom_pmu_lib
    require_live qcom_sysmon
    require_live qcom_q6v5
    require_live qcom_ramdump
    require_live qcom_q6v5_pas
    require_live qcom_reboot_reason
    require_live qcom_sdei
    require_live qcom_wdt_core
    require_live qcom_soc_wdt
    require_live qcom_spmi_pmic
    require_live qcom_tsens
    require_live qnoc_qos
    require_live qnoc_alor
    require_live qnoc_canoe
    require_live qrtr
    require_live qseecom_proxy
    require_live qti_pmic_glink
    require_live repeater_qti_pmic_eusb2
    require_live rpmh_regulator
    require_live rtc_pm8xxx
    require_live sdhci_msm
    require_live sg
    require_live si_core_module
    require_live smcinvoke_dlkm
    require_live smp2p
    require_live spmi_pmic_arb
    require_live stub_regulator
    require_live tcsrcc_canoe
    require_live thermal_pause
    require_live ucsi_qti_glink
    require_live ufshcd_crypto_qti
    require_live ufs_qcom
    require_live videocc_canoe
    load_one zsmalloc /system_dlkm/lib/modules zsmalloc.ko
    load_one zram /system_dlkm/lib/modules zram.ko
    require_live zsmalloc
    require_live zram
    say 'GKI_COMPLETE 2/2'
    ;;
vendor)
    require_live iommu_logger
    require_live qcom_scm
    require_live qcom_iommu_util
    require_live arm_smmu
    require_live arm_smmu_pmu
    require_live debug_symbol
    require_live deferred_free_helper
    require_live gh_arm_drv
    require_live gh_dbl
    require_live gh_msgq
    require_live secure_buffer
    require_live gh_rm_drv
    require_live gh_mem_notifier
    require_live mem_prot
    require_live gh_rm_heap_manager
    require_live mem_buf_dev
    require_live msm_dma_iommu_mapping
    require_live qcom_dma_heaps
    require_live qcom_hwspinlock
    require_live smem
    require_live minidump
    require_live qcom_ipc_logging
    require_live bcl_pmic5
    require_live crm_v2
    require_live debug_regulator
    require_live proxy_consumer
    require_live gdsc_regulator
    require_live icc_clk
    require_live clk_qcom
    require_live cambistmclkcc_canoe
    require_live camcc_alor
    require_live camcc_canoe
    require_live clk_dummy
    require_live cmd_db
    require_live qcom_rpmh
    require_live clk_rpmh
    require_live clk_scmi
    require_live cpu_hotplug
    require_live cpu_phys_log_map
    require_live qcom_cpucp
    require_live qcom_scmi_vendor
    require_live qcom_scmi_client
    require_live socinfo
    require_live sched_walt
    require_live cpucp_fast
    require_live cqhci
    require_live dcvs_fp
    require_live debugcc_canoe
    require_live dispcc_canoe
    require_live eud
    require_live phy_generic
    require_live phy_msm_snps_hs
    require_live eom_driver
    require_live phy_msm_ssusb_qmp
    require_live redriver
    require_live repeater
    require_live qti_regmap_debugfs
    require_live wcd_usbss_i2c
    require_live dwc3_msm
    require_live evacc_canoe
    require_live gcc_alor
    require_live gcc_canoe
    require_live gh_vcpu_mgr
    require_live gic_intr_routing
    require_live gpucc_canoe
    require_live hwid
    require_live msm_gpi
    require_live i2c_msm_geni
    require_live icc_bcm_voter
    require_live icc_debug
    require_live icc_rpmh
    require_live llcc_qcom
    require_live mdt_loader
    require_live mem_buf_msgq
    require_live mem_buf
    require_live memory_dump_v2
    require_live miev
    require_live qcom_aoss
    require_live msm_qmp
    require_live nb7vpq904m
    require_live nvmem_qcom_spmi_sdam
    require_live qmi_helpers
    require_live qcom_pdr_msg
    require_live qcom_glink
    require_live qcom_glink_smem
    require_live qcom_smd
    require_live rproc_qcom_common
    require_live pdr_interface
    require_live phy_msm_m31_eusb2
    require_live phy_qcom_ufs
    require_live phy_qcom_ufs_qmp_v4_canoe
    require_live phy_qcom_ufs_qrbtc_sdm845
    require_live qcom_pdc
    require_live pinctrl_msm
    require_live pinctrl_alor
    require_live pinctrl_canoe
    require_live pinctrl_chora
    require_live pinctrl_spmi_gpio
    require_live pmic_pon_log
    require_live qcom_cpu_vendor_hooks
    require_live qcom_dcvs
    require_live qcom_dload_mode
    require_live qcom_ice
    require_live qcom_iommu_debug
    require_live qcom_ipcc
    require_live qcom_llcc_pmu
    require_live qcom_logbuf_boot_log
    require_live qcom_logbuf_vendor_hooks
    require_live qcom_pil_info
    require_live qcom_pmu_lib
    require_live qcom_sysmon
    require_live qcom_q6v5
    require_live qcom_ramdump
    require_live qcom_q6v5_pas
    require_live qcom_reboot_reason
    require_live qcom_sdei
    require_live qcom_wdt_core
    require_live qcom_soc_wdt
    require_live qcom_spmi_pmic
    require_live qcom_tsens
    require_live qnoc_qos
    require_live qnoc_alor
    require_live qnoc_canoe
    require_live qrtr
    require_live qseecom_proxy
    require_live qti_pmic_glink
    require_live repeater_qti_pmic_eusb2
    require_live rpmh_regulator
    require_live rtc_pm8xxx
    require_live sdhci_msm
    require_live sg
    require_live si_core_module
    require_live smcinvoke_dlkm
    require_live smp2p
    require_live spmi_pmic_arb
    require_live stub_regulator
    require_live tcsrcc_canoe
    require_live thermal_pause
    require_live ucsi_qti_glink
    require_live ufshcd_crypto_qti
    require_live ufs_qcom
    require_live videocc_canoe
    require_live zsmalloc
    require_live zram
    wait_firmware
    load_one altmode_glink /vendor_dlkm/lib/modules altmode-glink.ko
    load_one drm_display_helper /vendor_dlkm/lib/modules drm_display_helper.ko
    load_one fsa4480_i2c /vendor_dlkm/lib/modules fsa4480_i2c.ko
    load_one gh_irq_lend /vendor_dlkm/lib/modules gh_irq_lend.ko
    load_one hdcp_qseecom_dlkm /vendor_dlkm/lib/modules hdcp_qseecom_dlkm.ko
    load_one ipclite /vendor_dlkm/lib/modules ipclite.ko
    load_one msm_ext_display /vendor_dlkm/lib/modules msm_ext_display.ko
    load_one msm_hfi_core /vendor_dlkm/lib/modules msm_hfi_core.ko
    load_one msm_hw_fence /vendor_dlkm/lib/modules msm_hw_fence.ko
    load_one nvmem_qfprom /vendor_dlkm/lib/modules nvmem_qfprom.ko
    load_one panel_event_notifier /vendor_dlkm/lib/modules panel_event_notifier.ko
    load_one qcom_va_minidump /vendor_dlkm/lib/modules qcom_va_minidump.ko
    load_one qti_fixed_regulator /vendor_dlkm/lib/modules qti-fixed-regulator.ko
    load_one smmu_proxy_dlkm /vendor_dlkm/lib/modules smmu_proxy_dlkm.ko
    load_one sync_fence /vendor_dlkm/lib/modules sync_fence.ko
    load_one synx_driver /vendor_dlkm/lib/modules synx-driver.ko
    load_one msm_drm /vendor_dlkm/lib/modules msm_drm.ko dsi_display0=qcom,mdss_dsi_p11u_42_0d_0a_dsc_cmd: myron_r27_log_windows=1
    load_one coresight /vendor_dlkm/lib/modules coresight.ko
    load_one msm_performance /vendor_dlkm/lib/modules msm_performance.ko
    load_one msm_sysstats /vendor_dlkm/lib/modules msm_sysstats.ko
    load_one governor_msm_adreno_tz /vendor_dlkm/lib/modules governor_msm_adreno_tz.ko
    load_one governor_gpubw_mon /vendor_dlkm/lib/modules governor_gpubw_mon.ko
    load_one governor_msm_adreno_ro /vendor_dlkm/lib/modules governor_msm_adreno_ro.ko
    load_one msm_kgsl /vendor_dlkm/lib/modules msm_kgsl.ko
    say 'R53_ADSP_BEGIN count=9; dependency/CRC-audited r13 modules'
    load_one qrtr_smd /vendor_dlkm/lib/modules qrtr-smd.ko
    load_one glink_pkt /vendor_dlkm/lib/modules glink_pkt.ko
    load_one frpc_adsprpc /vendor_dlkm/lib/modules frpc-adsprpc.ko
    load_one snd_event_dlkm /vendor_dlkm/lib/modules snd_event_dlkm.ko
    load_one q6_pdr_dlkm /vendor_dlkm/lib/modules q6_pdr_dlkm.ko
    load_one q6_notifier_dlkm /vendor_dlkm/lib/modules q6_notifier_dlkm.ko
    load_one gpr_dlkm /vendor_dlkm/lib/modules gpr_dlkm.ko
    load_one spf_core_dlkm /vendor_dlkm/lib/modules spf_core_dlkm.ko
    load_one adsp_loader_dlkm /vendor_dlkm/lib/modules adsp_loader_dlkm.ko
    require_live qrtr_smd
    require_live glink_pkt
    require_live frpc_adsprpc
    require_live snd_event_dlkm
    require_live q6_pdr_dlkm
    require_live q6_notifier_dlkm
    require_live gpr_dlkm
    require_live spf_core_dlkm
    require_live adsp_loader_dlkm
    say 'R53_ADSP_MODULES_LIVE 9/9; DSP firmware/QMI readiness requires runtime evidence'
    say 'R54_AUDIO_BEGIN count=36; dependency/CRC-audited r13 modules'
    load_one qti_battery_charger /vendor_dlkm/lib/modules qti_battery_charger.ko
    load_one qcom_hv_haptics /vendor_dlkm/lib/modules qcom-hv-haptics.ko
    load_one audpkt_ion_dlkm /vendor_dlkm/lib/modules audpkt_ion_dlkm.ko
    load_one audio_pkt_dlkm /vendor_dlkm/lib/modules audio_pkt_dlkm.ko
    load_one q6_dlkm /vendor_dlkm/lib/modules q6_dlkm.ko
    load_one audio_prm_dlkm /vendor_dlkm/lib/modules audio_prm_dlkm.ko
    load_one wcd_core_dlkm /vendor_dlkm/lib/modules wcd_core_dlkm.ko
    load_one swr_dlkm /vendor_dlkm/lib/modules swr_dlkm.ko
    load_one swr_ctrl_dlkm /vendor_dlkm/lib/modules swr_ctrl_dlkm.ko
    load_one lpass_cdc_dlkm /vendor_dlkm/lib/modules lpass_cdc_dlkm.ko
    load_one lpass_cdc_rx_macro_dlkm /vendor_dlkm/lib/modules lpass_cdc_rx_macro_dlkm.ko
    load_one wsa884x_dlkm /vendor_dlkm/lib/modules wsa884x_dlkm.ko
    load_one wsa883x_dlkm /vendor_dlkm/lib/modules wsa883x_dlkm.ko
    load_one mbhc_dlkm /vendor_dlkm/lib/modules mbhc_dlkm.ko
    load_one wcd9xxx_dlkm /vendor_dlkm/lib/modules wcd9xxx_dlkm.ko
    load_one wcd939x_slave_dlkm /vendor_dlkm/lib/modules wcd939x_slave_dlkm.ko
    load_one wcd939x_dlkm /vendor_dlkm/lib/modules wcd939x_dlkm.ko
    load_one sdca_registers_dlkm /vendor_dlkm/lib/modules sdca_registers_dlkm.ko
    load_one wcd9378_dlkm /vendor_dlkm/lib/modules wcd9378_dlkm.ko
    load_one btfmcodec /vendor_dlkm/lib/modules btfmcodec.ko
    load_one wcd937x_dlkm /vendor_dlkm/lib/modules wcd937x_dlkm.ko
    load_one machine_dlkm /vendor_dlkm/lib/modules machine_dlkm.ko
    load_one pinctrl_lpi_dlkm /vendor_dlkm/lib/modules pinctrl_lpi_dlkm.ko
    load_one stub_dlkm /vendor_dlkm/lib/modules stub_dlkm.ko
    load_one swr_haptics_dlkm /vendor_dlkm/lib/modules swr_haptics_dlkm.ko
    load_one hdmi_dlkm /vendor_dlkm/lib/modules hdmi_dlkm.ko
    load_one lpass_cdc_wsa2_macro_dlkm /vendor_dlkm/lib/modules lpass_cdc_wsa2_macro_dlkm.ko
    load_one lpass_cdc_wsa_macro_dlkm /vendor_dlkm/lib/modules lpass_cdc_wsa_macro_dlkm.ko
    load_one lpass_cdc_va_macro_dlkm /vendor_dlkm/lib/modules lpass_cdc_va_macro_dlkm.ko
    load_one lpass_cdc_tx_macro_dlkm /vendor_dlkm/lib/modules lpass_cdc_tx_macro_dlkm.ko
    load_one smem_mailbox /vendor_dlkm/lib/modules smem-mailbox.ko
    load_one cnss_utils /vendor_dlkm/lib/modules cnss_utils.ko
    load_one rfkill /vendor_dlkm/lib/modules rfkill.ko
    load_one btpower /vendor_dlkm/lib/modules btpower.ko
    load_one bt_fm_swr /vendor_dlkm/lib/modules bt_fm_swr.ko
    load_one lpass_bt_swr_dlkm /vendor_dlkm/lib/modules lpass_bt_swr_dlkm.ko
    require_live qti_battery_charger
    require_live qcom_hv_haptics
    require_live audpkt_ion_dlkm
    require_live audio_pkt_dlkm
    require_live q6_dlkm
    require_live audio_prm_dlkm
    require_live wcd_core_dlkm
    require_live swr_dlkm
    require_live swr_ctrl_dlkm
    require_live lpass_cdc_dlkm
    require_live lpass_cdc_rx_macro_dlkm
    require_live wsa884x_dlkm
    require_live wsa883x_dlkm
    require_live mbhc_dlkm
    require_live wcd9xxx_dlkm
    require_live wcd939x_slave_dlkm
    require_live wcd939x_dlkm
    require_live sdca_registers_dlkm
    require_live wcd9378_dlkm
    require_live btfmcodec
    require_live wcd937x_dlkm
    require_live machine_dlkm
    require_live pinctrl_lpi_dlkm
    require_live stub_dlkm
    require_live swr_haptics_dlkm
    require_live hdmi_dlkm
    require_live lpass_cdc_wsa2_macro_dlkm
    require_live lpass_cdc_wsa_macro_dlkm
    require_live lpass_cdc_va_macro_dlkm
    require_live lpass_cdc_tx_macro_dlkm
    require_live smem_mailbox
    require_live cnss_utils
    require_live rfkill
    require_live btpower
    require_live bt_fm_swr
    require_live lpass_bt_swr_dlkm
    say 'R54_AUDIO_MODULES_LIVE 36/36; sound-card and DSP readiness require runtime evidence'
    require_live iommu_logger
    require_live qcom_scm
    require_live qcom_iommu_util
    require_live arm_smmu
    require_live arm_smmu_pmu
    require_live debug_symbol
    require_live deferred_free_helper
    require_live gh_arm_drv
    require_live gh_dbl
    require_live gh_msgq
    require_live secure_buffer
    require_live gh_rm_drv
    require_live gh_mem_notifier
    require_live mem_prot
    require_live gh_rm_heap_manager
    require_live mem_buf_dev
    require_live msm_dma_iommu_mapping
    require_live qcom_dma_heaps
    require_live qcom_hwspinlock
    require_live smem
    require_live minidump
    require_live qcom_ipc_logging
    require_live bcl_pmic5
    require_live crm_v2
    require_live debug_regulator
    require_live proxy_consumer
    require_live gdsc_regulator
    require_live icc_clk
    require_live clk_qcom
    require_live cambistmclkcc_canoe
    require_live camcc_alor
    require_live camcc_canoe
    require_live clk_dummy
    require_live cmd_db
    require_live qcom_rpmh
    require_live clk_rpmh
    require_live clk_scmi
    require_live cpu_hotplug
    require_live cpu_phys_log_map
    require_live qcom_cpucp
    require_live qcom_scmi_vendor
    require_live qcom_scmi_client
    require_live socinfo
    require_live sched_walt
    require_live cpucp_fast
    require_live cqhci
    require_live dcvs_fp
    require_live debugcc_canoe
    require_live dispcc_canoe
    require_live eud
    require_live phy_generic
    require_live phy_msm_snps_hs
    require_live eom_driver
    require_live phy_msm_ssusb_qmp
    require_live redriver
    require_live repeater
    require_live qti_regmap_debugfs
    require_live wcd_usbss_i2c
    require_live dwc3_msm
    require_live evacc_canoe
    require_live gcc_alor
    require_live gcc_canoe
    require_live gh_vcpu_mgr
    require_live gic_intr_routing
    require_live gpucc_canoe
    require_live hwid
    require_live msm_gpi
    require_live i2c_msm_geni
    require_live icc_bcm_voter
    require_live icc_debug
    require_live icc_rpmh
    require_live llcc_qcom
    require_live mdt_loader
    require_live mem_buf_msgq
    require_live mem_buf
    require_live memory_dump_v2
    require_live miev
    require_live qcom_aoss
    require_live msm_qmp
    require_live nb7vpq904m
    require_live nvmem_qcom_spmi_sdam
    require_live qmi_helpers
    require_live qcom_pdr_msg
    require_live qcom_glink
    require_live qcom_glink_smem
    require_live qcom_smd
    require_live rproc_qcom_common
    require_live pdr_interface
    require_live phy_msm_m31_eusb2
    require_live phy_qcom_ufs
    require_live phy_qcom_ufs_qmp_v4_canoe
    require_live phy_qcom_ufs_qrbtc_sdm845
    require_live qcom_pdc
    require_live pinctrl_msm
    require_live pinctrl_alor
    require_live pinctrl_canoe
    require_live pinctrl_chora
    require_live pinctrl_spmi_gpio
    require_live pmic_pon_log
    require_live qcom_cpu_vendor_hooks
    require_live qcom_dcvs
    require_live qcom_dload_mode
    require_live qcom_ice
    require_live qcom_iommu_debug
    require_live qcom_ipcc
    require_live qcom_llcc_pmu
    require_live qcom_logbuf_boot_log
    require_live qcom_logbuf_vendor_hooks
    require_live qcom_pil_info
    require_live qcom_pmu_lib
    require_live qcom_sysmon
    require_live qcom_q6v5
    require_live qcom_ramdump
    require_live qcom_q6v5_pas
    require_live qcom_reboot_reason
    require_live qcom_sdei
    require_live qcom_wdt_core
    require_live qcom_soc_wdt
    require_live qcom_spmi_pmic
    require_live qcom_tsens
    require_live qnoc_qos
    require_live qnoc_alor
    require_live qnoc_canoe
    require_live qrtr
    require_live qseecom_proxy
    require_live qti_pmic_glink
    require_live repeater_qti_pmic_eusb2
    require_live rpmh_regulator
    require_live rtc_pm8xxx
    require_live sdhci_msm
    require_live sg
    require_live si_core_module
    require_live smcinvoke_dlkm
    require_live smp2p
    require_live spmi_pmic_arb
    require_live stub_regulator
    require_live tcsrcc_canoe
    require_live thermal_pause
    require_live ucsi_qti_glink
    require_live ufshcd_crypto_qti
    require_live ufs_qcom
    require_live videocc_canoe
    require_live zsmalloc
    require_live zram
    require_live altmode_glink
    require_live drm_display_helper
    require_live fsa4480_i2c
    require_live gh_irq_lend
    require_live hdcp_qseecom_dlkm
    require_live ipclite
    require_live msm_ext_display
    require_live msm_hfi_core
    require_live msm_hw_fence
    require_live nvmem_qfprom
    require_live panel_event_notifier
    require_live qcom_va_minidump
    require_live qti_fixed_regulator
    require_live smmu_proxy_dlkm
    require_live sync_fence
    require_live synx_driver
    require_live msm_drm
    require_live coresight
    require_live msm_performance
    require_live msm_sysstats
    require_live governor_msm_adreno_tz
    require_live governor_gpubw_mon
    require_live governor_msm_adreno_ro
    require_live msm_kgsl
    # Only real kernel Live records satisfy the restricted readiness contract.
    # Do not force readiness when any selected module failed or is still Loading.
    setprop vendor.all.modules.ready 1 || fail 'ready property rejected'
    say 'SELECTED_READY 213/213; display/GPU, DSP and audio dependency trial, not full hardware support'
    # R55: selected-module readiness above remains a module-only statement.
    # This runs in the already-asynchronous vendor.modprobe service, never GKI.
    r55_late_dsp_start() (
        r55_log() { printf 'R55_DSP target=%s event=%s %s\n' "$1" "$2" "$3"; }
        r55_firmware_file() {
            # Only the existing stock ueventd firmware search directories.
            for r55_dir in /etc/firmware /odm/firmware /vendor/firmware /firmware/image \
                /vendor/firmware_mnt/image /vendor/modem_firmware/image \
                /vendor/soccp_firmware/image /vendor/vm-system; do
                if [ -r "$r55_dir/$1" ] && [ -s "$r55_dir/$1" ]; then
                    printf '%s\n' "$r55_dir/$1"
                    return 0
                fi
            done
            return 1
        }
        r55_identity() {
            r55_check_node=$1
            r55_check_base=${r55_check_node##*/}
            case "$r55_check_base" in
                remoteproc*) r55_check_index=${r55_check_base#remoteproc} ;;
                *) return 1 ;;
            esac
            case "$r55_check_index" in ''|*[!0-9]*) return 1 ;; esac
            [ "$("$TIMEOUT" cat "$r55_check_node/name" 2>/dev/null)" = "$r55_name" ] || return 1
            [ "$("$TIMEOUT" cat "$r55_check_node/firmware" 2>/dev/null)" = "$r55_firmware" ] || return 1
            r55_parent=/sys/devices/platform/soc/$r55_name
            [ "$("$TIMEOUT" readlink -f "$r55_check_node" 2>/dev/null)" = \
                "$r55_parent/remoteproc/$r55_check_base" ] || return 1
            [ "$("$TIMEOUT" readlink -f "$r55_parent/of_node" 2>/dev/null)" = \
                "/sys/firmware/devicetree/base/soc/$r55_of_name" ] || return 1
            [ "$("$TIMEOUT" tr '\000' '\n' < "$r55_parent/of_node/compatible" 2>/dev/null)" = \
                "$r55_compatible" ] || return 1
            [ -r "$r55_check_node/state" ] && [ -w "$r55_check_node/state" ]
        }
        r55_worker() (
            r55_target=$1
            case "$r55_target" in
                adsp)
                    r55_name=3000000.remoteproc-adsp
                    r55_of_name=remoteproc-adsp@03000000
                    r55_compatible=qcom,canoe-adsp-pas
                    r55_firmware=adsp.mdt
                    r55_dtb_firmware=adsp_dtb.mdt
                    ;;
                cdsp)
                    r55_name=32300000.remoteproc-cdsp
                    r55_of_name=remoteproc-cdsp@32300000
                    r55_compatible=qcom,canoe-cdsp-pas
                    r55_firmware=cdsp.mdt
                    r55_dtb_firmware=cdsp_dtb.mdt
                    ;;
                *) r55_log unknown REFUSED 'invalid_target'; return 1 ;;
            esac
            r55_log "$r55_target" WAIT_READY 'budget_s=15'
            r55_ready=0
            r55_tick=0
            while [ "$r55_tick" -lt 15 ]; do
                r55_fallback=$("$TIMEOUT" cat /proc/sys/kernel/firmware_config/force_sysfs_fallback 2>/dev/null) || r55_fallback=unreadable
                r55_ueventd=$(getprop init.svc.ueventd)
                r55_coldboot=$(getprop ro.cold_boot_done)
                r55_mdt=$(r55_firmware_file "$r55_firmware") || r55_mdt=
                r55_dtb=$(r55_firmware_file "$r55_dtb_firmware") || r55_dtb=
                if [ "$r55_fallback" = 1 ] && [ "$r55_ueventd" = running ] && \
                    [ "$r55_coldboot" = true ] && [ -n "$r55_mdt" ] && [ -n "$r55_dtb" ]; then
                    r55_ready=1
                    break
                fi
                sleep 1 || return 1
                r55_tick=$((r55_tick + 1))
            done
            if [ "$r55_ready" != 1 ]; then
                r55_log "$r55_target" NOT_READY "fallback=$r55_fallback ueventd=$r55_ueventd coldboot=$r55_coldboot mdt=$r55_mdt dtb=$r55_dtb; no_write"
                return 1
            fi
            r55_count=0
            r55_node=
            for r55_candidate in /sys/class/remoteproc/remoteproc*; do
                [ -e "$r55_candidate/name" ] || continue
                r55_candidate_name=$("$TIMEOUT" cat "$r55_candidate/name" 2>/dev/null) || continue
                [ "$r55_candidate_name" = "$r55_name" ] || continue
                r55_count=$((r55_count + 1))
                r55_node=$r55_candidate
            done
            if [ "$r55_count" -ne 1 ] || ! r55_identity "$r55_node"; then
                r55_log "$r55_target" IDENTITY_REFUSED "matches=$r55_count node=$r55_node; no_write"
                return 1
            fi
            r55_state=$("$TIMEOUT" cat "$r55_node/state" 2>/dev/null) || r55_state=unreadable
            case "$r55_state" in
                running) r55_log "$r55_target" ALREADY_RUNNING "node=$r55_node; no_write"; return 0 ;;
                offline) ;;
                *) r55_log "$r55_target" STATE_SKIPPED "node=$r55_node state=$r55_state; no_write"; return 1 ;;
            esac
            r55_identity "$r55_node" || { r55_log "$r55_target" IDENTITY_CHANGED 'no_write'; return 1; }
            r55_log "$r55_target" START_ONCE "node=$r55_node mdt=$r55_mdt dtb=$r55_dtb budget_s=20"
            # Read state again inside the timed child immediately before writing.
            # The kernel has no offline CAS: a competing user can add a power vote.
            # Never stop, detach, SSR, or retry to compensate for that narrow race.
            "$TIMEOUT" timeout -k 2 20 /vendor/bin/sh -c '
                IFS= read -r r55_now < "$1" || exit 4
                [ "$r55_now" = offline ] || exit 3
                printf "start\n" > "$1"
            ' r55-dsp-write "$r55_node/state"
            r55_write_rc=$?
            r55_after=$("$TIMEOUT" cat "$r55_node/state" 2>/dev/null) || r55_after=unreadable
            if [ "$r55_after" = running ]; then
                r55_log "$r55_target" RUNNING "node=$r55_node writer_rc=$r55_write_rc; firmware_QMI_audio_readiness_not_claimed"
                return 0
            fi
            r55_log "$r55_target" START_UNCONFIRMED "node=$r55_node state=$r55_after writer_rc=$r55_write_rc; no_retry"
            return 1
        )
        # choose_timeout already proved this applet before any module was loaded.
        # Repeat the no-op probe here; failure never revokes selected-module ready.
        if ! "$TIMEOUT" timeout -k 2 1 "$TIMEOUT" true >/dev/null 2>&1; then
            r55_log all TOOL_UNAVAILABLE 'timeout_probe_failed; no_write'
            return 1
        fi
        r55_log all BEGIN 'module_gate_already_complete=213/213 supervisor_budget_s=45'
        r55_worker adsp &
        r55_adsp_pid=$!
        r55_worker cdsp &
        r55_cdsp_pid=$!
        r55_elapsed=0
        r55_adsp_done=0
        r55_cdsp_done=0
        while [ "$r55_elapsed" -lt 45 ]; do
            if [ "$r55_adsp_done" = 0 ] && ! kill -0 "$r55_adsp_pid" 2>/dev/null; then
                wait "$r55_adsp_pid"; r55_rc=$?
                r55_log adsp WORKER_EXIT "rc=$r55_rc"
                r55_adsp_done=1
            fi
            if [ "$r55_cdsp_done" = 0 ] && ! kill -0 "$r55_cdsp_pid" 2>/dev/null; then
                wait "$r55_cdsp_pid"; r55_rc=$?
                r55_log cdsp WORKER_EXIT "rc=$r55_rc"
                r55_cdsp_done=1
            fi
            [ "$r55_adsp_done$r55_cdsp_done" = 11 ] && break
            sleep 1 || break
            r55_elapsed=$((r55_elapsed + 1))
        done
        for r55_pair in "adsp:$r55_adsp_pid:$r55_adsp_done" "cdsp:$r55_cdsp_pid:$r55_cdsp_done"; do
            r55_target=${r55_pair%%:*}
            r55_rest=${r55_pair#*:}
            r55_pid=${r55_rest%%:*}
            r55_done=${r55_rest##*:}
            if [ "$r55_done" = 0 ]; then
                r55_log "$r55_target" SUPERVISOR_TIMEOUT 'worker_state_unknown; no_wait_no_retry'
                kill -TERM "$r55_pid" 2>/dev/null || :
                kill -KILL "$r55_pid" 2>/dev/null || :
                # Do not wait: a kernel firmware write could be uninterruptible.
            fi
        done
        r55_log all END "elapsed_s=$r55_elapsed; selected_module_ready_unchanged DSP_result_in_per_target_markers"
        return 0
    )
    r55_late_dsp_start || say 'R55_DSP helper_failed; selected module readiness retained'
    ;;
*) fail 'unknown stage' ;;
esac
exit 0
