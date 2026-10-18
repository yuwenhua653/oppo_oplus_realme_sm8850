#!/system/bin/sh
# Writes only fixed files under its unique, pre-created run directory.
dir=$1; token=$2; expected_boot=$3
case "$token" in ''|*[!0-9a-f]*) exit 64;; esac
[ "${#token}" = 32 ] || exit 64
[ "$dir" = "/data/local/tmp/r75-charge-$token" ] || exit 64
[ -d "$dir" ] && [ ! -L "$dir" ] || exit 65
umask 077
IFS= read -r boot < /proc/sys/kernel/random/boot_id || exit 88
[ "$boot" = "$expected_boot" ] || exit 89
script_sha=$(sha256sum "$dir/recorder.sh") || exit 66
script_sha=${script_sha%% *}
snapshot_sha=$(sha256sum "$dir/snapshot.sh") || exit 66
snapshot_sha=${snapshot_sha%% *}
IFS=' ' read -r start idle < /proc/uptime || exit 67
start=${start%%.*}
case "$start" in ''|*[!0-9]*) exit 67;; esac
# Claim must never be overwritten, including a duplicate launch.
(set -C; printf 'protocol=1\ntoken=%s\nboot_id=%s\nrecorder_sha256=%s\nsnapshot_sha256=%s\nstart_uptime_seconds=%s\n' "$token" "$expected_boot" "$script_sha" "$snapshot_sha" "$start" > "$dir/claim") || exit 68
(set -C; : > "$dir/periodic.log") || exit 68
round=0
status() {
  IFS=' ' read -r status_now status_idle < /proc/uptime || return 67
  status_now=${status_now%%.*}
  case "$status_now" in ''|*[!0-9]*) return 67;; esac
  [ ! -e "$dir/status.tmp" ] && [ ! -L "$dir/status.tmp" ] && [ ! -L "$dir/status" ] && [ ! -d "$dir/status" ] || return 70
  (set -C; printf 'protocol=1\ntoken=%s\nboot_id=%s\nrecorder_sha256=%s\nsnapshot_sha256=%s\nstate=%s\nrounds=%s\nstart_uptime_seconds=%s\nlast_uptime_seconds=%s\n' "$token" "$expected_boot" "$script_sha" "$snapshot_sha" "$1" "$round" "$start" "$status_now" > "$dir/status.tmp") && mv "$dir/status.tmp" "$dir/status"
}
status recording || exit 69
while [ "$round" -lt 75 ]; do
  IFS= read -r boot < /proc/sys/kernel/random/boot_id || { status boot_unavailable; exit 88; }
  [ "$boot" = "$expected_boot" ] || { status boot_changed; exit 89; }
  IFS=' ' read -r now idle < /proc/uptime || { status clock_unavailable; exit 67; }
  now=${now%%.*}
  case "$now" in ''|*[!0-9]*) status clock_unavailable; exit 67;; esac
  [ "$((now-start))" -lt 150 ] || break
  round=$((round+1))
  printf '\nROUND=%s\n' "$round" >> "$dir/periodic.log"
  # Inner timeout stays in the outer supervisor's process group.
  { /system/bin/toybox timeout --foreground -k 1 8 /system/bin/sh "$dir/snapshot.sh" "$token" "$expected_boot"; printf '\nSNAPSHOT_EXEC_RC=%s\n' "$?"; } 2>&1 | head -c 65536 >> "$dir/periodic.log"
  status recording || exit 69
  # Target a two-second start cadence; slow frames are never overlapped.
  IFS=' ' read -r after idle < /proc/uptime || { status clock_unavailable; exit 67; }
  after=${after%%.*}
  case "$after" in ''|*[!0-9]*) status clock_unavailable; exit 67;; esac
  delay=$((now+2-after))
  [ "$delay" -le 0 ] || sleep "$delay"
 done
status complete
