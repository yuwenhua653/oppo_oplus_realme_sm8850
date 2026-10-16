# SPDX-License-Identifier: GPL-2.0-only
# Myron experimental source modules. Loaded in the SoC root Bazel package.
def register_modules(registry):
    registry.register(
        name = "drivers/input/fingerprint/mi_fp",
        out = "mi_fp.ko",
        config = "CONFIG_FINGERPRINT_MI_FP",
        srcs = [
            "drivers/input/fingerprint/mi_fp/fp_driver.c",
            "drivers/input/fingerprint/mi_fp/fp_platform.c",
            "drivers/input/fingerprint/mi_fp/fp_netlink.c",
            "drivers/input/fingerprint/mi_fp/fp_input.c",
            "drivers/input/fingerprint/mi_fp/fp_driver.h",
            "drivers/input/fingerprint/mi_fp/fp_ultra.h",
        ],
        deps = ["drivers/soc/qcom/panel_event_notifier"],
    )
    registry.register(
        name = "drivers/xiaomi/mi_stack",
        out = "mi_stack.ko",
        config = "CONFIG_MI_STACK",
        srcs = ["drivers/xiaomi/mi_stack/mi_stack.c"],
    )
    registry.register(
        name = "drivers/xiaomi/mi_ubt",
        out = "mi_ubt.ko",
        config = "CONFIG_MI_UBT",
        srcs = ["drivers/xiaomi/mi_ubt/mi_ubt.c"],
    )
    registry.register(
        name = "drivers/xiaomi/printk_enhance",
        out = "printk_enhance.ko",
        config = "CONFIG_PRINTK_ENHANCE",
        srcs = ["drivers/xiaomi/printk_enhance/printk_enhance.c"],
    )
    registry.register(
        name = "drivers/misc/hwid/hwid",
        out = "hwid.ko",
        config = "CONFIG_MI_HARDWARE_ID",
        srcs = [
            "drivers/misc/hwid/hwid.c",
            "drivers/misc/hwid/hwid.h",
            "include/soc/qcom/socinfo.h",
        ],
        includes = ["include"],
        deps = ["drivers/soc/qcom/socinfo"],
    )
    registry.register(
        name = "drivers/misc/miev/miev",
        out = "miev.ko",
        config = "CONFIG_MIEV",
        srcs = [
            "drivers/misc/miev/midevice.c",
            "drivers/misc/miev/midevice.h",
            "drivers/misc/miev/mievent.c",
            "include/miev/mievent.h",
        ],
        includes = ["include"],
    )
    registry.register(
        name = "drivers/input/touchscreen/xiaomi/xiaomi_touch",
        out = "xiaomi_touch.ko",
        config = "CONFIG_TOUCHSCREEN_XIAOMI_TOUCHFEATURE",
        srcs = [
            "drivers/input/touchscreen/xiaomi/xiaomi_touch_core.c",
            "drivers/input/touchscreen/xiaomi/xiaomi_touch_device.c",
            "drivers/input/touchscreen/xiaomi/xiaomi_touch_evdev.c",
            "drivers/input/touchscreen/xiaomi/xiaomi_touch_knock_data.c",
            "drivers/input/touchscreen/xiaomi/xiaomi_touch_mode.c",
            "drivers/input/touchscreen/xiaomi/xiaomi_touch_operations.c",
            "drivers/input/touchscreen/xiaomi/xiaomi_touch_proc.c",
            "drivers/input/touchscreen/xiaomi/xiaomi_touch_sys.c",
            "drivers/input/touchscreen/xiaomi/xiaomi_touch.h",
            "drivers/input/touchscreen/xiaomi/xiaomi_touch_type_common.h",
            "include/linux/soc/qcom/panel_event_notifier.h",
            "include/miev/mievent.h",
        ],
        includes = [
            "include",
        ],
        deps = [
            "drivers/soc/qcom/panel_event_notifier",
            "drivers/misc/miev/miev",
        ],
        copts = [
            "-DTOUCH_THP_SUPPORT",
            "-DTOUCH_FOD_SUPPORT",
        ],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_common/mca_sysfs",
        out = "mca_sysfs.ko",
        config = "CONFIG_MYRON_MCA_BASE",
        srcs = [
            "drivers/power/supply/mca/mca_common/mca_sysfs.c",
            "drivers/power/supply/mca/include/mca/common/mca_sysfs.h",
        ],
        includes = [
            "drivers/power/supply/mca/include",
        ],
        deps = [
        ],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_common/mca_event",
        out = "mca_event.ko",
        config = "CONFIG_MYRON_MCA_BASE",
        srcs = [
            "drivers/power/supply/mca/mca_common/mca_event.c",
            "drivers/power/supply/mca/include/mca/common/mca_sysfs.h",
            "drivers/power/supply/mca/include/mca/common/mca_event.h",
        ],
        includes = [
            "drivers/power/supply/mca/include",
        ],
        deps = [
            "drivers/power/supply/mca/mca_common/mca_sysfs",
        ],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_common/mca_log",
        out = "mca_log.ko",
        config = "CONFIG_MYRON_MCA_BASE",
        srcs = [
            "drivers/power/supply/mca/mca_common/mca_log.c",
            "drivers/power/supply/mca/include/mca/common/mca_sysfs.h",
            "drivers/power/supply/mca/include/mca/common/mca_event.h",
            "drivers/power/supply/mca/include/mca/common/mca_log.h",
        ],
        includes = [
            "drivers/power/supply/mca/include",
        ],
        deps = [
            "drivers/power/supply/mca/mca_common/mca_event",
            "drivers/power/supply/mca/mca_common/mca_sysfs",
        ],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_common/mca_parse_dts",
        out = "mca_parse_dts.ko",
        config = "CONFIG_MYRON_MCA_BASE",
        srcs = [
            "drivers/power/supply/mca/mca_common/mca_parse_dts.c",
            "drivers/power/supply/mca/include/mca/common/mca_log.h",
            "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h",
        ],
        includes = [
            "drivers/power/supply/mca/include",
        ],
        deps = [
            "drivers/power/supply/mca/mca_common/mca_log",
        ],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_common/mca_voter",
        out = "mca_voter.ko",
        config = "CONFIG_MYRON_MCA_BASE",
        srcs = [
            "drivers/power/supply/mca/mca_common/mca_voter.c",
            "drivers/power/supply/mca/include/mca/common/mca_log.h",
            "drivers/power/supply/mca/include/mca/common/mca_voter.h",
        ],
        includes = [
            "drivers/power/supply/mca/include",
        ],
        deps = [
            "drivers/power/supply/mca/mca_common/mca_log",
        ],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_common/mca_workqueue",
        out = "mca_workqueue.ko",
        config = "CONFIG_MYRON_MCA_BASE",
        srcs = [
            "drivers/power/supply/mca/mca_common/mca_workqueue.c",
            "drivers/power/supply/mca/include/mca/common/mca_log.h",
        ],
        includes = [
            "drivers/power/supply/mca/include",
        ],
        deps = [
            "drivers/power/supply/mca/mca_common/mca_log",
        ],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_common/mca_hwid",
        out = "mca_hwid.ko",
        config = "CONFIG_MYRON_MCA_BASE",
        srcs = [
            "drivers/power/supply/mca/mca_common/mca_hwid.c",
            "drivers/power/supply/mca/include/mca/common/mca_hwid.h",
            "drivers/power/supply/mca/include/mca/common/mca_log.h",
            "drivers/misc/hwid/hwid.h",
        ],
        includes = [
            "drivers/power/supply/mca/include",
            "drivers/misc/hwid",
        ],
        deps = [
            "drivers/misc/hwid/hwid",
            "drivers/power/supply/mca/mca_common/mca_log",
        ],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_common/mca_charge_interface",
        out = "mca_charge_interface.ko",
        config = "CONFIG_MYRON_MCA_INTERFACE",
        srcs = ["drivers/power/supply/mca/mca_common/mca_charge_interface.c", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_event.h"],
        includes = ["drivers/power/supply/mca/include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_sysfs", "drivers/power/supply/mca/mca_common/mca_event"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_protocol/mca_protocol_class",
        out = "mca_protocol_class.ko",
        config = "CONFIG_MYRON_MCA_PLATFORM",
        srcs = ["drivers/power/supply/mca/mca_protocol/mca_protocol_class.c", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h"],
        includes = ["drivers/power/supply/mca/include"],
        deps = [],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_protocol/protocol_qc/mca_protocol_qc_class",
        out = "mca_protocol_qc_class.ko",
        config = "CONFIG_MYRON_MCA_PLATFORM",
        srcs = ["drivers/power/supply/mca/mca_protocol/protocol_qc/mca_protocol_qc_class.c", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h"],
        includes = ["drivers/power/supply/mca/include"],
        deps = ["drivers/power/supply/mca/mca_protocol/mca_protocol_class"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_platform/mca_platform_loadsw_class",
        out = "mca_platform_loadsw_class.ko",
        config = "CONFIG_MYRON_MCA_PLATFORM",
        srcs = ["drivers/power/supply/mca/mca_platform/mca_platform_loadsw_class.c", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h"],
        includes = ["drivers/power/supply/mca/include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_sysfs", "drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_parse_dts"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_platform/mca_platform_cp_class",
        out = "mca_platform_cp_class.ko",
        config = "CONFIG_MYRON_MCA_PLATFORM",
        srcs = ["drivers/power/supply/mca/mca_platform/mca_platform_cp_class.c", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h"],
        includes = ["drivers/power/supply/mca/include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_sysfs", "drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_parse_dts"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_platform/mca_platform_buckchg_class",
        out = "mca_platform_buckchg_class.ko",
        config = "CONFIG_MYRON_MCA_PLATFORM",
        srcs = ["drivers/power/supply/mca/mca_platform/mca_platform_buckchg_class.c", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h"],
        includes = ["drivers/power/supply/mca/include"],
        deps = [],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_protocol/protocol_pd/mca_protocol_pd_class",
        out = "mca_protocol_pd_class.ko",
        config = "CONFIG_MYRON_MCA_PLATFORM",
        srcs = ["drivers/power/supply/mca/mca_protocol/protocol_pd/mca_protocol_pd_class.c", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h"],
        includes = ["drivers/power/supply/mca/include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_sysfs", "drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_parse_dts", "drivers/power/supply/mca/mca_common/mca_event", "drivers/power/supply/mca/mca_protocol/mca_protocol_class"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_platform/mca_platform_bc12_class",
        out = "mca_platform_bc12_class.ko",
        config = "CONFIG_MYRON_MCA_PLATFORM",
        srcs = ["drivers/power/supply/mca/mca_platform/mca_platform_bc12_class.c", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h"],
        includes = ["drivers/power/supply/mca/include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_protocol/mca_protocol_class", "drivers/power/supply/mca/mca_protocol/protocol_pd/mca_protocol_pd_class"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_platform/mca_platform_fg_ic_ops",
        out = "mca_platform_fg_ic_ops.ko",
        config = "CONFIG_MYRON_MCA_PLATFORM",
        srcs = ["drivers/power/supply/mca/mca_platform/mca_platform_fg_ic_ops.c", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h"],
        includes = ["drivers/power/supply/mca/include"],
        deps = [],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_common/mca_qcom_smem",
        out = "mca_qcom_smem.ko",
        config = "CONFIG_MYRON_MCA_PLATFORM",
        srcs = ["drivers/power/supply/mca/mca_common/mca_qcom_smem.c", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_log.h"],
        includes = ["drivers/power/supply/mca/include", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_log", "drivers/soc/qcom/smem"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_common/mca_charge_mievent",
        out = "mca_charge_mievent.ko",
        config = "CONFIG_MYRON_MCA_PLATFORM",
        srcs = ["drivers/power/supply/mca/mca_common/mca_charge_mievent.c", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "include/miev/mievent.h"],
        includes = ["drivers/power/supply/mca/include", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_event", "drivers/misc/miev/miev"],
    )
    registry.register(
        name = "drivers/ir-spi/ir-spi",
        out = "ir-spi.ko",
        config = "CONFIG_MYRON_MISC",
        srcs = ["drivers/ir-spi/ir-spi.c"],
        includes = [],
        deps = [],
    )
    registry.register(
        name = "drivers/misc/st54se/stm_st54se_gpio",
        out = "stm_st54se_gpio.ko",
        config = "CONFIG_MYRON_MISC",
        srcs = ["drivers/misc/st54se/st54spi_gpio.c"],
        includes = [],
        deps = [],
    )
# Generated registration entries; append inside register_modules(registry).
    registry.register(
        name = "drivers/power/supply/mca/mca_common/mca_adsp_glink",
        out = "mca_adsp_glink.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_common/mca_adsp_glink.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_log", "drivers/soc/qcom/qti_pmic_glink"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_hardware_monitor/mca_bmd",
        out = "mca_bmd.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_hardware_monitor/mca_bmd.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_charge_mievent", "drivers/power/supply/mca/mca_common/mca_event", "drivers/power/supply/mca/mca_common/mca_hwid", "drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_parse_dts", "drivers/power/supply/mca/mca_common/mca_sysfs", "drivers/power/supply/mca/mca_platform/mca_platform_buckchg_class", "drivers/power/supply/mca/mca_platform/mca_platform_wireless_class", "drivers/power/supply/mca/mca_strategy/mca_strategy_class", "drivers/power/supply/mca/mca_strategy/strategy_fg/mca_strategy_fg_class"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_business/business_battery/mca_business_battery_comp",
        out = "mca_business_battery_comp.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_business/business_battery/mca_business_battery.c", "drivers/power/supply/mca/mca_business/business_battery/mca_battery_psy.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_event", "drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_parse_dts", "drivers/power/supply/mca/mca_common/mca_voter", "drivers/power/supply/mca/mca_platform/mca_platform_buckchg_class", "drivers/power/supply/mca/mca_strategy/strategy_fg/mca_strategy_fg_class"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_business/business_misc/mca_business_misc_comp",
        out = "mca_business_misc_comp.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_business/business_misc/mca_business_votable.c", "drivers/power/supply/mca/mca_business/business_misc/mca_business_misc.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_voter"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_hardware_monitor/mca_connector_antiburn",
        out = "mca_connector_antiburn.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_hardware_monitor/mca_connector_antiburn.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_charge_mievent", "drivers/power/supply/mca/mca_common/mca_event", "drivers/power/supply/mca/mca_common/mca_hwid", "drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_parse_dts", "drivers/power/supply/mca/mca_common/mca_sysfs", "drivers/power/supply/mca/mca_common/mca_workqueue", "drivers/power/supply/mca/mca_platform/mca_platform_buckchg_class", "drivers/power/supply/mca/mca_protocol/mca_protocol_class", "drivers/power/supply/mca/mca_protocol/protocol_pd/mca_protocol_pd_class"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_hardware_monitor/mca_ibat_ocp_monitor",
        out = "mca_ibat_ocp_monitor.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_hardware_monitor/mca_ibat_ocp_monitor.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_charge_mievent", "drivers/power/supply/mca/mca_common/mca_event", "drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_parse_dts", "drivers/power/supply/mca/mca_common/mca_sysfs", "drivers/power/supply/mca/mca_platform/mca_platform_buckchg_class", "drivers/power/supply/mca/mca_platform/mca_platform_fg_ic_ops", "drivers/power/supply/mca/mca_platform/mca_platform_loadsw_class", "drivers/power/supply/mca/mca_platform/mca_platform_wireless_class", "drivers/power/supply/mca/mca_strategy/strategy_fg/mca_strategy_fg_class"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_hardware_monitor/mca_lpd_detect",
        out = "mca_lpd_detect.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_hardware_monitor/mca_lpd_detect.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_sysfs", "drivers/power/supply/mca/mca_platform/mca_platform_buckchg_class"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_hardware_monitor/mca_path_control",
        out = "mca_path_control.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_hardware_monitor/mca_path_control.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_parse_dts", "drivers/power/supply/mca/mca_common/mca_sysfs", "drivers/power/supply/mca/mca_platform/mca_platform_buckchg_class", "drivers/power/supply/mca/mca_platform/mca_platform_cp_class", "drivers/power/supply/mca/mca_platform/mca_platform_wireless_class", "drivers/power/supply/mca/mca_strategy/strategy_wireless/mca_wireless_revchg"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_strategy/strategy_pd/mca_pd_auth",
        out = "mca_pd_auth.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_strategy/strategy_pd/mca_pd_auth.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_charge_mievent", "drivers/power/supply/mca/mca_common/mca_event", "drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_sysfs", "drivers/power/supply/mca/mca_platform/mca_platform_buckchg_class", "drivers/power/supply/mca/mca_protocol/protocol_pd/mca_protocol_pd_class"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_platform/mca_platform_base",
        out = "mca_platform_base.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_platform/mca_platform_base.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_log"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_platform/mca_platform_wireless_class",
        out = "mca_platform_wireless_class.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_platform/mca_platform_wireless_class.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_parse_dts", "drivers/power/supply/mca/mca_common/mca_sysfs"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_common/mca_qcom_panel",
        out = "mca_qcom_panel.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_common/mca_qcom_panel.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_event", "drivers/power/supply/mca/mca_common/mca_log", "drivers/soc/qcom/panel_event_notifier"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_qcom_subpmic_proxy/mca_qcom_subpmic_proxy",
        out = "mca_qcom_subpmic_proxy.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_qcom_subpmic_proxy/mca_qcom_subpmic_proxy.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_adsp_glink", "drivers/power/supply/mca/mca_common/mca_charge_mievent", "drivers/power/supply/mca/mca_common/mca_event", "drivers/power/supply/mca/mca_common/mca_hwid", "drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_parse_dts", "drivers/power/supply/mca/mca_platform/mca_platform_bc12_class", "drivers/power/supply/mca/mca_platform/mca_platform_buckchg_class", "drivers/power/supply/mca/mca_platform/mca_platform_cp_class", "drivers/power/supply/mca/mca_protocol/protocol_pd/mca_protocol_pd_class", "drivers/power/supply/mca/mca_protocol/protocol_qc/mca_protocol_qc_class", "drivers/power/supply/mca/mca_strategy/mca_strategy_class"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_strategy/mca_strategy_class",
        out = "mca_strategy_class.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_strategy/mca_strategy_class.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = [],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_strategy/strategy_fg/mca_strategy_fg_class",
        out = "mca_strategy_fg_class.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_strategy/strategy_fg/mca_strategy_fg_class.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = [],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_hardware_monitor/mca_vbat_ovp_monitor",
        out = "mca_vbat_ovp_monitor.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_hardware_monitor/mca_vbat_ovp_monitor.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_event", "drivers/power/supply/mca/mca_common/mca_hwid", "drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_parse_dts", "drivers/power/supply/mca/mca_common/mca_sysfs", "drivers/power/supply/mca/mca_platform/mca_platform_buckchg_class", "drivers/power/supply/mca/mca_platform/mca_platform_wireless_class", "drivers/power/supply/mca/mca_strategy/strategy_fg/mca_strategy_fg_class"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_strategy/strategy_wireless/mca_wireless_revchg",
        out = "mca_wireless_revchg.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_strategy/strategy_wireless/mca_wireless_revchg.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_charge_mievent", "drivers/power/supply/mca/mca_common/mca_event", "drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_common/mca_parse_dts", "drivers/power/supply/mca/mca_common/mca_sysfs", "drivers/power/supply/mca/mca_common/mca_voter", "drivers/power/supply/mca/mca_hardware_monitor/mca_bmd", "drivers/power/supply/mca/mca_platform/mca_platform_buckchg_class", "drivers/power/supply/mca/mca_platform/mca_platform_cp_class", "drivers/power/supply/mca/mca_platform/mca_platform_wireless_class", "drivers/power/supply/mca/mca_protocol/mca_protocol_class", "drivers/power/supply/mca/mca_strategy/mca_strategy_class", "drivers/power/supply/mca/mca_strategy/strategy_fg/mca_strategy_fg_class"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_protocol/protocol_pd/qcom_tcpc/qcom_adsp_pd_protocol",
        out = "qcom_adsp_pd_protocol.ko",
        config = "CONFIG_MYRON_MCA_SERVICES",
        srcs = ["drivers/power/supply/mca/mca_protocol/protocol_pd/qcom_tcpc/qcom_adsp_pd_protocol.c", "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h", "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h", "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h", "drivers/power/supply/mca/include/mca/common/mca_event.h", "drivers/power/supply/mca/include/mca/common/mca_hwid.h", "drivers/power/supply/mca/include/mca/common/mca_log.h", "drivers/power/supply/mca/include/mca/common/mca_panel.h", "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h", "drivers/power/supply/mca/include/mca/common/mca_smem.h", "drivers/power/supply/mca/include/mca/common/mca_sysfs.h", "drivers/power/supply/mca/include/mca/common/mca_voter.h", "drivers/power/supply/mca/include/mca/common/mca_workqueue.h", "drivers/power/supply/mca/include/mca/hardware/hw_path_control.h", "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h", "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h", "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h", "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h", "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h", "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h", "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h", "drivers/power/supply/mca/include/mca/shared_memory/charger_partition_class.h", "drivers/power/supply/mca/include/mca/smartchg/smart_chg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_fg_class.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit.h", "drivers/power/supply/mca/include/mca/strategy/strategy_soc_limit_stepper.h", "drivers/power/supply/mca/include/mca/strategy/strategy_wireless_class.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_battery_psy.h", "drivers/power/supply/mca/mca_business/business_battery/inc/mca_business_battery.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_business_charger.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_usb_psy.h", "drivers/power/supply/mca/mca_business/business_charger/inc/mca_charger_wireless_psy.h", "drivers/power/supply/mca/mca_business/business_misc/inc/mca_business_misc.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_bmd.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_connector_antiburn.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_ibat_ocp_monitor.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_lpd_detect.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_path_control.h", "drivers/power/supply/mca/mca_hardware_monitor/inc/mca_vbat_ovp_monitor.h", "drivers/power/supply/mca/mca_shared_memory/inc/charger_partition.h", "drivers/power/supply/mca/mca_smart_charge/inc/mca_smart_charge.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_buckchg_jeita.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_charger_thermal.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_quick_charger.h", "drivers/power/supply/mca/mca_strategy/strategy_charger/inc/mca_strategy_buckchg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_battery_shutdown.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_limit.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/mca_soc_smooth.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h", "drivers/power/supply/mca/mca_strategy/strategy_fg/inc/xm_battery_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_pd/pd_auth.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_basic_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_quick_wireless.h", "drivers/power/supply/mca/mca_strategy/strategy_wireless/inc/mca_wireless_revchg.h", "drivers/misc/hwid/hwid.h", "include/linux/soc/qcom/panel_event_notifier.h", "include/linux/soc/qcom/qti_pmic_glink.h"],
        includes = ["drivers/power/supply/mca/include", "drivers/misc/hwid", "include"],
        deps = ["drivers/power/supply/mca/mca_common/mca_adsp_glink", "drivers/power/supply/mca/mca_common/mca_event", "drivers/power/supply/mca/mca_common/mca_log", "drivers/power/supply/mca/mca_protocol/protocol_pd/mca_protocol_pd_class"],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_hardware_ic/boost_ic/hl7603/hl7603",
        out = "hl7603.ko",
        config = "CONFIG_MYRON_CHARGE_IC",
        srcs = [
            "drivers/power/supply/mca/mca_hardware_ic/boost_ic/hl7603/hl7603.c",
            "drivers/power/supply/mca/mca_hardware_ic/boost_ic/hl7603/inc/hl7603.h",
            "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h",
            "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h",
            "drivers/power/supply/mca/include/mca/common/mca_event.h",
            "drivers/power/supply/mca/include/mca/common/mca_hwid.h",
            "drivers/power/supply/mca/include/mca/common/mca_log.h",
            "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h",
            "drivers/power/supply/mca/include/mca/common/mca_smem.h",
            "drivers/power/supply/mca/include/mca/common/mca_sysfs.h",
            "drivers/power/supply/mca/include/mca/common/mca_voter.h",
            "drivers/power/supply/mca/include/mca/common/mca_workqueue.h",
            "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h",
            "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h",
            "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h",
            "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h",
            "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h",
            "drivers/power/supply/mca/include/mca/protocol/protocol_class.h",
            "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h",
            "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h",
            "drivers/power/supply/mca/include/mca/common/mca_panel.h",
            "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h",
            "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h",
            "drivers/power/supply/mca/include/mca/strategy/strategy_class.h",
            "drivers/misc/hwid/hwid.h"
        ],
        includes = [
            "drivers/power/supply/mca/include",
            "drivers/misc/hwid"
        ],
        deps = [
            "drivers/power/supply/mca/mca_common/mca_event",
            "drivers/power/supply/mca/mca_common/mca_log",
            "drivers/power/supply/mca/mca_common/mca_parse_dts",
            "drivers/power/supply/mca/mca_common/mca_sysfs"
        ],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_hardware_ic/charge_pump_ic/sc8581/sc8581",
        out = "sc8581.ko",
        config = "CONFIG_MYRON_CHARGE_IC",
        srcs = [
            "drivers/power/supply/mca/mca_hardware_ic/charge_pump_ic/sc8581/sc8581.c",
            "drivers/power/supply/mca/mca_hardware_ic/charge_pump_ic/sc8581/inc/sc8581.h",
            "drivers/power/supply/mca/mca_hardware_ic/charge_pump_ic/sc8581/inc/sc8581_reg.h",
            "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h",
            "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h",
            "drivers/power/supply/mca/include/mca/common/mca_event.h",
            "drivers/power/supply/mca/include/mca/common/mca_hwid.h",
            "drivers/power/supply/mca/include/mca/common/mca_log.h",
            "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h",
            "drivers/power/supply/mca/include/mca/common/mca_smem.h",
            "drivers/power/supply/mca/include/mca/common/mca_sysfs.h",
            "drivers/power/supply/mca/include/mca/common/mca_voter.h",
            "drivers/power/supply/mca/include/mca/common/mca_workqueue.h",
            "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h",
            "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h",
            "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h",
            "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h",
            "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h",
            "drivers/power/supply/mca/include/mca/protocol/protocol_class.h",
            "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h",
            "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h",
            "drivers/power/supply/mca/include/mca/common/mca_panel.h",
            "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h",
            "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h",
            "drivers/power/supply/mca/include/mca/strategy/strategy_class.h",
            "drivers/misc/hwid/hwid.h"
        ],
        includes = [
            "drivers/power/supply/mca/include",
            "drivers/misc/hwid"
        ],
        deps = [
            "drivers/power/supply/mca/mca_common/mca_event",
            "drivers/power/supply/mca/mca_common/mca_hwid",
            "drivers/power/supply/mca/mca_common/mca_log",
            "drivers/power/supply/mca/mca_common/mca_parse_dts",
            "drivers/power/supply/mca/mca_platform/mca_platform_cp_class",
            "drivers/power/supply/mca/mca_common/mca_sysfs"
        ],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561",
        out = "bq27z561.ko",
        config = "CONFIG_MYRON_CHARGE_IC",
        srcs = [
            "drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561.c",
            "drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/inc/bq27z561.h",
            "drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/inc/bq27z561_nfg1000_fw.h",
            "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h",
            "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h",
            "drivers/power/supply/mca/include/mca/common/mca_event.h",
            "drivers/power/supply/mca/include/mca/common/mca_hwid.h",
            "drivers/power/supply/mca/include/mca/common/mca_log.h",
            "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h",
            "drivers/power/supply/mca/include/mca/common/mca_smem.h",
            "drivers/power/supply/mca/include/mca/common/mca_sysfs.h",
            "drivers/power/supply/mca/include/mca/common/mca_voter.h",
            "drivers/power/supply/mca/include/mca/common/mca_workqueue.h",
            "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h",
            "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h",
            "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h",
            "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h",
            "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h",
            "drivers/power/supply/mca/include/mca/protocol/protocol_class.h",
            "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h",
            "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h",
            "drivers/power/supply/mca/include/mca/common/mca_panel.h",
            "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h",
            "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h",
            "drivers/power/supply/mca/include/mca/strategy/strategy_class.h",
            "drivers/misc/hwid/hwid.h"
        ],
        includes = [
            "drivers/power/supply/mca/include",
            "drivers/misc/hwid"
        ],
        deps = [
            "drivers/power/supply/mca/mca_common/mca_hwid",
            "drivers/power/supply/mca/mca_common/mca_log",
            "drivers/power/supply/mca/mca_common/mca_parse_dts",
            "drivers/power/supply/mca/mca_platform/mca_platform_fg_ic_ops",
            "drivers/power/supply/mca/mca_strategy/mca_strategy_class",
            "drivers/power/supply/mca/mca_common/mca_sysfs"
        ],
    )
    registry.register(
        name = "drivers/power/supply/mca/mca_hardware_ic/wireless_ic/sc96281/sc96281_charger",
        out = "sc96281_charger.ko",
        config = "CONFIG_MYRON_CHARGE_IC",
        srcs = [
            "drivers/power/supply/mca/mca_hardware_ic/wireless_ic/sc96281/sc96281_core.c",
            "drivers/power/supply/mca/mca_hardware_ic/wireless_ic/sc96281/sc96281_mtp_program.c",
            "drivers/power/supply/mca/mca_hardware_ic/wireless_ic/sc96281/inc/sc96281_firmware.h",
            "drivers/power/supply/mca/mca_hardware_ic/wireless_ic/sc96281/inc/sc96281_mtp_program.h",
            "drivers/power/supply/mca/mca_hardware_ic/wireless_ic/sc96281/inc/sc96281_pgm.h",
            "drivers/power/supply/mca/mca_hardware_ic/wireless_ic/sc96281/inc/sc96281_reg.h",
            "drivers/power/supply/mca/include/mca/common/mca_charge_interface.h",
            "drivers/power/supply/mca/include/mca/common/mca_charge_mievent.h",
            "drivers/power/supply/mca/include/mca/common/mca_event.h",
            "drivers/power/supply/mca/include/mca/common/mca_hwid.h",
            "drivers/power/supply/mca/include/mca/common/mca_log.h",
            "drivers/power/supply/mca/include/mca/common/mca_parse_dts.h",
            "drivers/power/supply/mca/include/mca/common/mca_smem.h",
            "drivers/power/supply/mca/include/mca/common/mca_sysfs.h",
            "drivers/power/supply/mca/include/mca/common/mca_voter.h",
            "drivers/power/supply/mca/include/mca/common/mca_workqueue.h",
            "drivers/power/supply/mca/include/mca/platform/platform_bc12_class.h",
            "drivers/power/supply/mca/include/mca/platform/platform_buckchg_class.h",
            "drivers/power/supply/mca/include/mca/platform/platform_cp_class.h",
            "drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h",
            "drivers/power/supply/mca/include/mca/platform/platform_loadsw_class.h",
            "drivers/power/supply/mca/include/mca/protocol/protocol_class.h",
            "drivers/power/supply/mca/include/mca/protocol/protocol_pd_class.h",
            "drivers/power/supply/mca/include/mca/protocol/protocol_qc_class.h",
            "drivers/power/supply/mca/include/mca/common/mca_panel.h",
            "drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h",
            "drivers/power/supply/mca/include/mca/platform/platform_wireless_class.h",
            "drivers/power/supply/mca/include/mca/strategy/strategy_class.h",
            "drivers/misc/hwid/hwid.h"
        ],
        includes = [
            "drivers/power/supply/mca/include",
            "drivers/misc/hwid"
        ],
        deps = [
            "drivers/power/supply/mca/mca_common/mca_adsp_glink",
            "drivers/power/supply/mca/mca_common/mca_event",
            "drivers/power/supply/mca/mca_common/mca_log",
            "drivers/power/supply/mca/mca_common/mca_parse_dts",
            "drivers/power/supply/mca/mca_platform/mca_platform_wireless_class",
            "drivers/power/supply/mca/mca_strategy/mca_strategy_class"
        ],
    )
