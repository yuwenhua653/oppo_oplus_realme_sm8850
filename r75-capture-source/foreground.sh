#!/system/bin/sh
# R75 optional metadata, once before and once after recording; no BQ DT or CP getters.
IFS=' ' read -r stamp idle < /proc/uptime || exit 67
printf 'OPTIONAL_METADATA_BEGIN clock=BOOTTIME uptime=%s\n' "$stamp"
link_value() {
  printf '\nLINK=%s\n' "$1"
  if [ -L "$1" ]; then printf 'LINK_PRESENT=1\nTARGET='; /system/bin/toybox timeout --foreground -k 1 1 readlink -f "$1"; printf 'READLINK_RC=%s\n' "$?"; else echo LINK_PRESENT=0; fi
}
text_value() {
  printf '\nPATH=%s\n' "$1"
  value=$(/system/bin/toybox timeout --foreground -k 1 1 head -c 257 "$1"); rc=$?
  truncated=0; [ "${#value}" -le 256 ] || truncated=1
  printf '%s\nREAD_RC=%s\nVALUE_TRUNCATED=%s\n' "$value" "$rc" "$truncated"
}
dt_value() {
  printf '\nDT_PATH=%s\n' "$1"
  if [ -e "$1" ]; then echo EXISTS=1; /system/bin/toybox timeout --foreground -k 1 1 stat -c BYTES=%s "$1"; printf 'STAT_RC=%s\n' "$?"; else echo EXISTS=0; fi
  /system/bin/toybox timeout --foreground -k 1 1 od -An -tx1 -v -N 128 "$1"
  printf 'READ_RC=%s\n' "$?"
}
for node in /soc/pmic-glink/battery-charger /soc/pmic-glink/mca,adsp_glink /soc/mca_qcom_subpmic_proxy /soc/mca_business_charger /soc/mca_strategy_buckchg_class /soc/mca_strategy_quick_charge /soc/mca_platform_cp /soc/mca_bc12_class /soc/mca_protocol_core /soc/mca_qcom_pd_protocol /soc/mca_protocol_pd_class; do
  for attribute in compatible status; do dt_value "/sys/firmware/devicetree/base$node/$attribute"; done
 done
# This one extra DT field controls the reviewed UCSI power-supply scope.
for device in soc:pmic-glink soc:pmic-glink:ucsi-glink soc:pmic-glink:mca,adsp_glink soc:mca_qcom_subpmic_proxy; do
  path=/sys/bus/platform/devices/$device
  printf '\nPLATFORM=%s\n' "$path"; ls -ldn "$path"; printf 'META_RC=%s\n' "$?"
  for node in "$path/driver" "$path/driver/module" "$path/of_node"; do link_value "$node"; done
  text_value "$path/modalias"
  for attribute in compatible status; do dt_value "$path/of_node/$attribute"; done
 done
dt_value /sys/bus/platform/devices/soc:pmic-glink:ucsi-glink/of_node/scope
for driver in qti_battery_charger mca_adsp_glink qcom_subpmic business_charger ucsi_glink myron_mca_readonly; do
  path=/sys/bus/platform/drivers/$driver
  printf '\nDRIVER=%s\n' "$path"; ls -ldn "$path"; printf 'META_RC=%s\n' "$?"; link_value "$path/module"
 done
# Known clients only; gauge gets owner metadata, never DT properties.
for client in 5-0055 5-006e 5-0077; do
  path=/sys/bus/i2c/devices/$client
  printf '\nI2C=%s\n' "$path"; ls -ldn "$path"; printf 'META_RC=%s\n' "$?"
  text_value "$path/name"; text_value "$path/modalias"
  for node in "$path/driver" "$path/driver/module" "$path/of_node"; do link_value "$node"; done
  [ "$client" != 5-0055 ] || continue
  compatible_hex=$(/system/bin/toybox timeout --foreground -k 1 1 od -An -tx1 -v -N 256 "$path/of_node/compatible"); rc=$?
  compatible=$(printf '%s' "$compatible_hex" | tr -d ' \n')
  printf 'SELECTION_COMPATIBLE_HEX=%s\nSELECTION_RC=%s\n' "$compatible" "$rc"
  case "$rc:$compatible" in 0:73633835383100|0:7363383538355f6d617374657200|0:7363383538355f736c61766500)
    for attribute in compatible status reg; do dt_value "$path/of_node/$attribute"; done;;
    *) echo DT_SELECTION=not_in_exact_SC_allowlist;;
  esac
 done

# UCSI values describe negotiated/requested source properties, not battery current.
supply=/sys/class/power_supply/ucsi-source-psy-soc:pmic-glink:ucsi-glink1
printf '\nSUPPLY=%s\n' "$supply"
for node in "$supply" "$supply/device" "$supply/device/driver" "$supply/device/driver/module"; do link_value "$node"; done
driver=$(/system/bin/toybox timeout --foreground -k 1 1 readlink -f "$supply/device/driver")
module=$(/system/bin/toybox timeout --foreground -k 1 1 readlink -f "$supply/device/driver/module")
if [ "$driver" = /sys/bus/platform/drivers/ucsi_glink ] && [ "$module" = /sys/module/ucsi_qti_glink ]; then
  echo VALUE_SOURCE=ucsi_source_negotiated_not_battery_current
  for attribute in type scope online usb_type voltage_now voltage_max current_now current_max charge_type; do text_value "$supply/$attribute"; done
else echo MEASUREMENTS_SKIPPED=ucsi_owner_unverified; fi
count=0
for port in /sys/class/typec/*; do
  [ -e "$port" ] || continue
  count=$((count+1)); [ "$count" -le 16 ] || { echo TYPEC_ENUM_LIMIT=16; break; }
  printf '\nTYPEC=%s\n' "$port"
  for node in "$port" "$port/device" "$port/device/driver" "$port/device/driver/module"; do link_value "$node"; done
  for attribute in power_role data_role power_operation_mode; do text_value "$port/$attribute"; done
 done
count=0
for role in /sys/class/usb_role/*/role; do
  [ -e "$role" ] || continue
  count=$((count+1)); [ "$count" -le 8 ] || { echo USB_ROLE_ENUM_LIMIT=8; break; }
  text_value "$role"
 done
count=0
for state in /sys/class/udc/*/state; do
  [ -e "$state" ] || continue
  count=$((count+1)); [ "$count" -le 8 ] || { echo UDC_ENUM_LIMIT=8; break; }
  text_value "$state"
 done
IFS=' ' read -r stamp idle < /proc/uptime || exit 67
printf 'OPTIONAL_METADATA_END clock=BOOTTIME uptime=%s\n' "$stamp"
