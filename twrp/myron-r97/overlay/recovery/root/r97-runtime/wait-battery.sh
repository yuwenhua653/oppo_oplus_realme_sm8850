#!/system/bin/sh
exec >/tmp/r97-battery.log 2>&1
. /r97-runtime/common.sh
check_battery() {
    same_path /sys/bus/i2c/devices/5-0055/driver /sys/bus/i2c/drivers/bq27z561 &&
    same_path /sys/bus/i2c/devices/5-0055/driver/module /sys/module/bq27z561 &&
    same_path /sys/bus/platform/devices/soc:strategy-fg/driver /sys/bus/platform/drivers/strategy_fg &&
    same_path /sys/bus/platform/devices/soc:strategy-fg/driver/module /sys/module/mca_strategy_fg_comp &&
    same_path /sys/class/power_supply/battery /sys/devices/platform/soc/soc:mca_business_battery/power_supply/battery &&
    same_path /sys/bus/platform/devices/soc:mca_business_battery/driver /sys/bus/platform/drivers/business_battery &&
    same_path /sys/bus/platform/devices/soc:mca_business_battery/driver/module /sys/module/mca_business_battery_comp &&
    [ "$(get /sys/class/power_supply/battery/type)" = Battery ] &&
    [ "$(get /sys/class/power_supply/battery/present)" = 1 ] || return 1
    cap=$(get /sys/class/power_supply/battery/capacity) || return 1
    case "$cap" in ''|*[!0-9]*) return 1;; esac
    [ "$cap" -le 100 ] || return 1
    echo "battery_capacity=$cap"
}
i=0
while [ "$i" -lt 30 ]; do
    if check_battery; then prop sys.r97.battery.ready 1; exit 0; fi
    sleep 1; i=$((i+1))
done
fail battery_not_ready
