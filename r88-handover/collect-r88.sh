#!/system/bin/sh
# R88: read-only status, bindings and bounded power diagnostics; no root.
# Run through adb shell sh -s; no file is installed or changed on the phone.

if command -v timeout >/dev/null 2>&1; then
    R88_TIMEOUT=1
else
    R88_TIMEOUT=0
fi

bounded() {
    r88_seconds=$1
    shift
    if [ "$R88_TIMEOUT" -ne 1 ]; then
        printf 'SKIPPED_NO_TIMEOUT command=%s\n' "${1-}"
        return 0
    fi
    timeout "$r88_seconds" "$@" 2>&1
    r88_result=$?
    if [ "$r88_result" -ne 0 ]; then
        printf '\nCOMMAND_STATUS %s (missing, denied or timed out; capture continues)\n' "$r88_result"
    fi
    return 0
}

metadata() {
    printf '\nPATH %s\n' "$1"
    bounded 3 ls -ldZ "$1"
}

read_small() {
    printf '\nREAD %s (raw text, maximum %s bytes)\n' "$1" "$2"
    bounded 3 head -c "$2" "$1"
    printf '\n'
}

property_hex() {
    printf '\nDT_PROPERTY %s (big-endian cells, maximum 128 bytes)\n' "$1"
    bounded 3 od -An -v -tx1 -N 128 "$1"
}

binding() {
    printf '\nDEVICE %s\n' "$1"
    metadata "$1"
    metadata "$1/driver"
    bounded 3 readlink -f "$1/driver"
    metadata "$1/driver/module"
    bounded 3 readlink -f "$1/driver/module"
    bounded 3 readlink -f "$1/of_node"
    property_hex "$1/of_node/compatible"
    property_hex "$1/of_node/status"
}

# Retain the R86 collector's restricted init-metadata parser. It prints service
# names/executable paths but never service arguments or executes init commands.
init_metadata() {
    r88_init_path=$1
    r88_init_line=0
    r88_init_shown=0
    while IFS= read -r r88_line || [ -n "$r88_line" ]; do
        r88_init_line=$((r88_init_line + 1))
        r88_line=${r88_line%%#*}
        set -f
        set -- $r88_line
        set +f
        case "${1-}" in
            service)
                printf '%s: service %s %s [arguments omitted]\n' "$r88_init_line" "${2-}" "${3-}"
                r88_init_shown=$((r88_init_shown + 1)) ;;
            user|group|seclabel|class|interface)
                printf '%s: %s\n' "$r88_init_line" "$r88_line"
                r88_init_shown=$((r88_init_shown + 1)) ;;
            chmod|chown|restorecon)
                case "$r88_line" in
                    *authentic*|*verify_digest*|*batt_power_match*|*xm_power/fuelgauge*)
                        printf '%s: %s\n' "$r88_init_line" "$r88_line"
                        r88_init_shown=$((r88_init_shown + 1)) ;;
                esac ;;
        esac
        [ "$r88_init_shown" -lt 64 ] || break
    done < "$r88_init_path"
}

printf 'R88_RUNTIME_CAPTURE_BEGIN\n'
printf 'Read-only R88 capture. Authentication attributes: metadata only.\n'
printf 'Raw power values are not a measurement of charger input power.\n'
printf 'Missing, denied or timed-out reads are recorded without requesting root.\n'
printf 'TIMEOUT_COMMAND_AVAILABLE %s\n' "$R88_TIMEOUT"
bounded 3 date '+TIME %Y-%m-%dT%H:%M:%S%z'
bounded 3 uname -a
read_small /proc/sys/kernel/random/boot_id 128
read_small /proc/uptime 128
for r88_key in ro.boot.dtbo_idx ro.boot.dtb_idx ro.hardware sys.boot_completed init.svc.batterysecret; do
    printf '\nPROP %s=' "$r88_key"
    bounded 3 getprop "$r88_key"
done
printf '\nROM fingerprint is not used to identify the running kernel.\n'

printf '\nSECTION R88_NATIVE_HANDOVER\n'
for r88_report in r88-mca.status r88-mca.claim r88-mca.log; do
    metadata "/vendor_dlkm/r36-report/$r88_report"
    read_small "/vendor_dlkm/r36-report/$r88_report" 65536
done
printf '\nSECTION LOADED_MODULES\n'
read_small /proc/modules 131072
for r88_module in myron_bq_readonly myron_mca_readonly bq27z561 sc8581 mca_adsp_glink mca_strategy_fg_comp mca_business_battery_comp mca_business_charger_comp mca_strategy_quickchg; do
    metadata "/sys/module/$r88_module"
done

printf '\nSECTION SEVEN_EXPECTED_DEVICE_BINDINGS\n'
for r88_device in \
    /sys/bus/i2c/devices/5-0055 \
    /sys/bus/i2c/devices/5-006e \
    /sys/bus/platform/devices/soc:pmic-glink:mca,adsp_glink \
    /sys/bus/platform/devices/soc:strategy-fg \
    /sys/bus/platform/devices/soc:mca_business_battery \
    /sys/bus/platform/devices/soc:mca_business_charger \
    /sys/bus/platform/devices/soc:mca_strategy_quick_charge; do
    binding "$r88_device"
done

printf '\nSECTION FG_OPTIONAL_DT_CONFIGURATION\n'
for r88_property in support_nvt1000_ota support-qbg; do
    r88_property_path="/sys/bus/platform/devices/soc:strategy-fg/of_node/$r88_property"
    metadata "$r88_property_path"
    if [ -e "$r88_property_path" ]; then
        printf 'DT_PROPERTY_PRESENT %s (empty boolean property still means present)\n' "$r88_property"
    else
        printf 'DT_PROPERTY_ABSENT_OR_INACCESSIBLE %s (not inferred as zero)\n' "$r88_property"
    fi
    property_hex "$r88_property_path"
done
printf '\nSECTION FG_DEFERRED_PROBE_REASON_IF_VISIBLE\n'
metadata /sys/kernel/debug/devices_deferred
if [ -r /sys/kernel/debug/devices_deferred ]; then
    read_small /sys/kernel/debug/devices_deferred 16384
else
    printf 'DEFERRED_PROBE_REASON_UNAVAILABLE (no elevated access requested)\n'
fi

printf '\nSECTION FG_EU_POLICY_READ_ONLY_STATUS\n'
metadata /sys/class/xm_power/fuelgauge/strategy_fg/eu_policy_status
read_small /sys/class/xm_power/fuelgauge/strategy_fg/eu_policy_status 256
printf 'valid=0 and is_eu_model=-1 indicate unknown policy; this is not a false EU value.\n'
printf 'This diagnostic contains no authentication value or digest.\n'

printf '\nSECTION AUTH_INTERFACE_METADATA_ONLY\n'
for r88_path in /sys/class/xm_power /sys/class/xm_power/fuelgauge /sys/class/xm_power/fuelgauge/strategy_fg; do
    metadata "$r88_path"
    bounded 3 readlink -f "$r88_path"
done
for r88_attribute in authentic slave_authentic verify_slave_flag verify_digest batt_power_match; do
    metadata "/sys/class/xm_power/fuelgauge/strategy_fg/$r88_attribute"
done
printf 'No authentication attribute value or digest is read. Presence is not authentication success.\n'

printf '\nSECTION POWER_SUPPLY_OWNERS_AND_RAW_VALUES\n'
printf 'Standard Linux power_supply units: voltage/current are normally microvolts/microamps, temp normally tenths of a degree C.\n'
printf 'Vendor-specific properties may differ. Values below are preserved without conversion, sign correction or power calculation.\n'
for r88_supply in /sys/class/power_supply/*; do
    [ -d "$r88_supply" ] || continue
    metadata "$r88_supply"
    bounded 3 readlink -f "$r88_supply"
    bounded 3 readlink -f "$r88_supply/device/driver"
    for r88_attribute in type usb_type real_type online present status health capacity voltage_now current_now voltage_max current_max input_current_limit input_voltage_limit temp charge_type; do
        [ -e "$r88_supply/$r88_attribute" ] || continue
        read_small "$r88_supply/$r88_attribute" 256
    done
done

printf '\nSECTION BATTERYSECRET_PROCESS_NAME\n'
bounded 4 sh -c 'ps -A -o NAME 2>&1 | grep -Ei "batterysecret|micharge|health|fuelgauge" | head -n 40'
printf 'No matching process name alone does not prove authentication failure.\n'
printf '\nSECTION BATTERYSECRET_INIT_METADATA\n'
metadata /vendor/etc/init/hw/init.batterysecret.rc
if [ -r /vendor/etc/init/hw/init.batterysecret.rc ]; then
    init_metadata /vendor/etc/init/hw/init.batterysecret.rc
fi

printf '\nSECTION DUMPSYS_BATTERY\n'
bounded 8 sh -c 'dumpsys battery 2>&1 | head -c 16384'
printf '\nSECTION DUMPSYS_THERMAL\n'
bounded 8 sh -c 'dumpsys thermalservice 2>&1 | head -c 24576'
printf '\nSECTION DUMPSYS_USB\n'
bounded 8 sh -c 'dumpsys usb 2>&1 | head -c 24576'
printf '\nSECTION SELECTED_SYSTEM_LOGCAT_TAGS\n'
printf 'Only BatteryService, UsbDeviceManager and health tags; no log clearing.\n'
bounded 8 logcat -b main -b system -d -v threadtime -t 400 'BatteryService:I' 'UsbDeviceManager:I' 'health:I' '*:S'
printf '\nCharger model, cable, battery percentage and meter input watts must be recorded by the tester.\n'
printf 'This capture does not declare that fast charging or authentication succeeded.\n'
printf '\nR88_RUNTIME_CAPTURE_END\n'
