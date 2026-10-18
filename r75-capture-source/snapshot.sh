#!/system/bin/sh
# R75 candidate: cache-only MCA, verified battery and USB. No Type-C enumeration.
token=$1
expected_boot=$2
case "$token" in ''|*[!0-9a-f]*) exit 64;; esac
[ "${#token}" = 32 ] || exit 64
clock() {
  IFS=' ' read -r stamp idle < /proc/uptime || return 67
  case "$stamp:$idle" in *[!0-9.:]*|:*) return 67;; esac
  [ -n "$stamp" ] && [ -n "$idle" ]
}
boot_check() {
  IFS= read -r boot < /proc/sys/kernel/random/boot_id || return 88
  [ "$boot" = "$expected_boot" ] || return 89
}
boot_check || exit $?
clock || exit 67
printf 'SNAPSHOT_BEGIN token=%s boot_id=%s uptime=%s %s\n' "$token" "$boot" "$stamp" "$idle"
printf 'CORE_BEGIN protocol=1 token=%s boot_id=%s clock=BOOTTIME uptime=%s\n' "$token" "$boot" "$stamp"
# Save rc and truncation independently; success from head alone never proves a full value.
read_value() {
  clock || exit 67
  printf '\nREAD_TIMING_BEGIN path=%s clock=BOOTTIME uptime=%s\nPATH=%s\n' "$1" "$stamp" "$1"
  if [ ! -e "$1" ]; then printf 'EXISTS=0\n'; else printf 'EXISTS=1\n'; fi
  value=$(/system/bin/toybox timeout --foreground -k 1 1 head -c 257 "$1"); value_rc=$?
  truncated=0; [ "${#value}" -le 256 ] || truncated=1
  printf '%s\nREAD_RC=%s\n' "$value" "$value_rc"
  clock || exit 67
  printf 'READ_TIMING_END path=%s clock=BOOTTIME uptime=%s rc=%s truncated=%s\n' "$1" "$stamp" "$value_rc" "$truncated"
}
link_value() {
  target=$(/system/bin/toybox timeout --foreground -k 1 1 readlink -f "$1"); link_rc=$?
  printf 'LINK=%s\nTARGET=%s\nREADLINK_RC=%s\n' "$1" "$target" "$link_rc"
}
mca=/sys/bus/platform/devices/soc:pmic-glink:mca,adsp_glink
real=/sys/devices/platform/soc/soc:pmic-glink/soc:pmic-glink:mca,adsp_glink
mca_ok=1
for pair in "$mca|$real" "$mca/of_node|/sys/firmware/devicetree/base/soc/pmic-glink/mca,adsp_glink" "$mca/driver|/sys/bus/platform/drivers/myron_mca_readonly" "$mca/driver/module|/sys/module/myron_mca_readonly"; do
  link_value "${pair%%|*}"
  [ "$link_rc" = 0 ] && [ "$target" = "${pair#*|}" ] || mca_ok=0
 done
for parameter in enable_readonly enable_power_supply; do
  read_value "/sys/module/myron_mca_readonly/parameters/$parameter"
  [ "$value_rc" = 0 ] && [ "$truncated" = 0 ] && { [ "$value" = Y ] || [ "$value" = 1 ]; } || mca_ok=0
 done
if [ "$mca_ok" = 1 ]; then
  clock || exit 67
  printf 'MCA_TIMING_BEGIN clock=BOOTTIME uptime=%s\nMCA_CACHE_BEGIN\n' "$stamp"
  cache=$(/system/bin/toybox timeout --foreground -k 1 1 head -c 4097 "$mca/myron_mca_readonly/snapshot"); cache_rc=$?
  cache_truncated=0; [ "${#cache}" -le 4096 ] || cache_truncated=1
  printf '%s\nMCA_CACHE_READ_RC=%s\nMCA_CACHE_END\n' "$cache" "$cache_rc"
  clock || exit 67
  printf 'MCA_TIMING_END clock=BOOTTIME uptime=%s rc=%s truncated=%s\n' "$stamp" "$cache_rc" "$cache_truncated"
else
  echo MCA_CACHE_SKIPPED=owner_or_parameter_mismatch
fi
battery=/sys/class/power_supply/battery
battery_ok=1
link_value "$battery/device"; case "$link_rc:$target" in 0:*/5-0055) :;; *) battery_ok=0;; esac
link_value "$battery/device/driver"; [ "$link_rc:$target" = 0:/sys/bus/i2c/drivers/myron_bq_readonly ] || battery_ok=0
link_value "$battery/device/driver/module"; [ "$link_rc:$target" = 0:/sys/module/myron_bq_readonly ] || battery_ok=0
if [ "$battery_ok" = 1 ]; then
  for parameter in enable_readonly enable_extended_readonly enable_status_readonly; do
    read_value "/sys/module/myron_bq_readonly/parameters/$parameter"
    [ "$value_rc" = 0 ] && [ "$truncated" = 0 ] && { [ "$value" = Y ] || [ "$value" = 1 ]; } || battery_ok=0
  done
fi
if [ "$battery_ok" = 1 ]; then
  echo VALUE_SOURCE=readonly_battery_signed_current_mca_status_raw_status
  for attribute in type status current_now voltage_now capacity temp health myron_readonly_diag/battery_status_raw; do read_value "$battery/$attribute"; done
else echo MEASUREMENTS_SKIPPED=battery_owner_or_parameter_mismatch; fi
usb=/sys/class/power_supply/usb
usb_ok=$mca_ok
for pair in "$usb/device|$real" "$usb/device/driver|/sys/bus/platform/drivers/myron_mca_readonly" "$usb/device/driver/module|/sys/module/myron_mca_readonly"; do
  link_value "${pair%%|*}"
  [ "$link_rc" = 0 ] && [ "$target" = "${pair#*|}" ] || usb_ok=0
 done
if [ "$usb_ok" = 1 ]; then
  read_value "$usb/type"; [ "$value_rc:$truncated:$value" = 0:0:USB ] || usb_ok=0
  read_value "$usb/model_name"; [ "$value_rc:$truncated:$value" = 0:0:myron-mca-readonly ] || usb_ok=0
fi
if [ "$usb_ok" = 1 ]; then
  echo VALUE_SOURCE=mca_cached_usb_input_not_battery_current
  for attribute in online status voltage_now current_now; do read_value "$usb/$attribute"; done
else echo MEASUREMENTS_SKIPPED=usb_owner_or_identity_mismatch; fi
boot_check || exit $?
clock || exit 67
# Marker means traversal ended; host still requires every expected read, rc and time.
printf 'CORE_END protocol=1 token=%s boot_id=%s clock=BOOTTIME uptime=%s\n' "$token" "$boot" "$stamp"
# Historical fixed diagnostics cannot delay or redefine CORE_END.
# Reading this file only copies already cached results; it never sends a GET.
if [ "$mca_ok" = 1 ]; then
  clock || exit 67
  printf 'DIAGNOSTICS_TIMING_BEGIN clock=BOOTTIME uptime=%s\nDIAGNOSTICS_CACHE_BEGIN\n' "$stamp"
  diagnostic=$(/system/bin/toybox timeout --foreground -k 1 1 head -c 4097 "$mca/myron_mca_readonly/diagnostics"); diagnostic_rc=$?
  diagnostic_truncated=0; [ "${#diagnostic}" -le 4096 ] || diagnostic_truncated=1
  printf '%s\nDIAGNOSTICS_CACHE_READ_RC=%s\nDIAGNOSTICS_CACHE_END\n' "$diagnostic" "$diagnostic_rc"
  clock || exit 67
  printf 'DIAGNOSTICS_TIMING_END clock=BOOTTIME uptime=%s rc=%s truncated=%s\n' "$stamp" "$diagnostic_rc" "$diagnostic_truncated"
else echo DIAGNOSTICS_CACHE_SKIPPED=owner_or_parameter_mismatch; fi
boot_check || exit $?
clock || exit 67
printf 'SNAPSHOT_END token=%s boot_id=%s uptime=%s %s\n' "$token" "$boot" "$stamp" "$idle"
