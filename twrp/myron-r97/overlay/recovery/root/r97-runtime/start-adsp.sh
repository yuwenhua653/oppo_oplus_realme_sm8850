#!/system/bin/sh
exec >/tmp/r97-adsp.log 2>&1
. /r97-runtime/common.sh
mkdir /tmp/r97-adsp.claim || fail already_attempted
parent=/sys/devices/platform/soc/3000000.remoteproc-adsp
node=
count=0
for p in /sys/class/remoteproc/remoteproc*; do
    [ -r "$p/name" ] || continue
    [ "$(get "$p/name")" = 3000000.remoteproc-adsp ] || continue
    node=$p;count=$((count+1))
done
[ "$count" = 1 ] || fail ambiguous_adsp
identity() {
    same_path "$node" "$parent/remoteproc/${node##*/}" &&
    same_path "$parent/of_node" /sys/firmware/devicetree/base/soc/remoteproc-adsp@03000000 &&
    dt_string "$parent/of_node/compatible" qcom,canoe-adsp-pas &&
    [ "$(get "$node/firmware")" = adsp.mdt ]
}
identity || fail adsp_identity
state=$(get "$node/state") || fail adsp_state
if [ "$state" != running ]; then
    [ "$state" = offline ] || fail "adsp_state $state"
    [ -s /firmware/image/adsp.mdt ] && [ -s /firmware/image/adsp_dtb.mdt ] || fail firmware_absent
    [ "$(/system/bin/getprop init.svc.ueventd)" = running ] || fail ueventd
    [ "$(get /proc/sys/kernel/firmware_config/force_sysfs_fallback)" = 1 ] || fail firmware_fallback
    identity || fail adsp_identity_changed
    # One start only; never force SSR, stop or retry after an uncertain write.
    "$TB" timeout -k 2 20 /system/bin/sh -c '
        IFS= read -r state < "$1" || exit 2
        [ "$state" = offline ] || exit 3
        printf "start\n" > "$1"
    ' r97-adsp "$node/state" || fail adsp_start
fi
i=0
while [ "$i" -lt 30 ]; do
    identity || fail adsp_identity_changed
    if [ "$(get "$node/state")" = running ]; then prop twrp.adsp.ready true; exit 0; fi
    sleep 1;i=$((i+1))
done
fail adsp_timeout
