#!/system/bin/sh
exec >/tmp/r97-hardware.log 2>&1
. /r97-runtime/common.sh
mkdir /tmp/r97-hardware.claim || fail already_attempted
[ "$(/system/bin/getprop sys.r97.ui.ready)" = 1 ] || fail ui_not_ready
preflight
# Preserve the same gauge/charge-pump/owner identity restrictions as normal boot.
same_path /sys/bus/i2c/devices/5-0055/of_node /sys/firmware/devicetree/base/soc/qcom,qupv3_1_geni_se@ac0000/i2c@a94000/bq27z561_standlone@55 || fail gauge_path
dt_string /sys/bus/i2c/devices/5-0055/of_node/compatible ti,bq27z561_master || fail gauge_compatible
dt_string /sys/bus/i2c/devices/5-0055/of_node/status ok || fail gauge_status
u32 /sys/bus/i2c/devices/5-0055/of_node/ic_role 00000000 || fail gauge_role
dt_string /sys/bus/i2c/devices/5-006e/of_node/compatible sc8585_master || fail pump
dt_string /sys/bus/i2c/devices/5-006e/of_node/status ok || fail pump_status
u32 /sys/bus/platform/devices/soc:strategy-fg/of_node/fg_type 00000000 || fail fg_type
u32 /sys/bus/platform/devices/soc:strategy-fg/of_node/adapt_power 00000064 || fail adapt_power
same_path /sys/bus/platform/devices/soc:pmic-glink/driver /sys/bus/platform/drivers/pmic_glink || fail glink_driver
same_path /sys/bus/platform/devices/soc:pmic-glink/driver/module /sys/module/qti_pmic_glink || fail glink_module
for p in /sys/bus/i2c/devices/5-0055/of_node/co_by_gpio /sys/bus/i2c/devices/5-0055/of_node/batt_ctl \
    /sys/bus/i2c/devices/5-0055/driver /sys/bus/i2c/devices/5-006e/driver \
    /sys/bus/platform/devices/soc:pmic-glink:mca,adsp_glink/driver \
    /sys/class/power_supply/battery /sys/class/power_supply/usb \
    /sys/module/myron_bq_readonly /sys/module/myron_mca_readonly; do
    [ ! -e "$p" ] && [ ! -L "$p" ] || fail "owner already present $p"
done
load_list hardware
prop sys.r97.hardware.modules 1
# Haptics uses the input FF implementation in the pinned TWRP core.
if live qcom_hv_haptics; then prop sys.r97.haptics.module 1; fi
# ADSP startup and battery observation are separate services. An ADSP timeout
# never suppresses display, ADB or a physically present fuel gauge.
prop sys.r97.battery.check 1
prop sys.r97.adsp.check 1
echo R97_HARDWARE_MODULES_LIVE
