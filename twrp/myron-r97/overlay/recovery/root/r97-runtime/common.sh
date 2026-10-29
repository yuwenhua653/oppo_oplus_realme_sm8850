#!/system/bin/sh
# Recovery-only runtime. Normal Android keeps the unmodified R94/R96 MCA helper.
set -u
PATH=/system/bin
export PATH
TB=/system/bin/toybox
BASE=/r97-runtime
fail() { echo "R97_FAIL $*"; exit 1; }
prop() { /system/bin/setprop "$1" "$2" || fail "setprop $1"; }
live() { "$TB" grep -q "^$1 .* Live " /proc/modules; }
get() { "$TB" timeout -k 1 2 "$TB" cat "$1"; }
canonical() { "$TB" readlink -f "$1"; }
same_path() { [ "$(canonical "$1")" = "$2" ]; }
dt_string() { [ "$("$TB" tr '\000' '\n' < "$1")" = "$2" ]; }
u32() { [ "$("$TB" od -An -tx1 -N4 "$1" | "$TB" tr -d ' \n')" = "$2" ]; }
loaded_guard() (
    while read -r n size refs deps state rest; do
        [ "$state" = Live ] || fail "non-live $n"
        "$TB" grep -qx "$n" "$BASE/allowed-live.txt" || fail "unexpected module $n"
    done < /proc/modules
)
preflight() {
    [ "$("$TB" uname -r)" = '6.12.81-android16-6-maybe-dirty-4k' ] || fail kernel
    [ "$(/system/bin/getprop ro.boot.hardware.sku)" = myron ] || fail sku
    dt_string /sys/firmware/devicetree/base/model 'Qualcomm Technologies, Inc. Myron based on SM8850' || fail model
    "$TB" timeout -k 1 1 "$TB" true || fail timeout
    [ "$(get /proc/sys/kernel/modules_disabled)" = 0 ] || fail modules_disabled
    (cd "$BASE" && "$TB" sha256sum -c modules.sha256) || fail module_hash
    while read -r n; do live "$n" || fail "firststage $n"; done < "$BASE/firststage.txt"
    loaded_guard || fail live_set
}
load_list() {
    while IFS='|' read -r n file args; do
        [ -n "$n" ] || continue
        if live "$n"; then continue; fi
        loaded_guard || fail live_set
        # args are a generated, reviewed list of simple module parameters.
        set -f
        "$TB" timeout -k 2 20 "$TB" insmod "$BASE/modules/$file" $args || fail "insert $n"
        set +f
        live "$n" || fail "not-live $n"
        echo "LOADED $n"
    done < "$BASE/$1.list"
}
