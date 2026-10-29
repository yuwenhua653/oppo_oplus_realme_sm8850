#!/system/bin/sh
exec >/tmp/r97-ui.log 2>&1
. /r97-runtime/common.sh
mkdir /tmp/r97-ui.claim || fail already_attempted
preflight
load_list ui
# This suppresses TWRP's OEM module scan. Hardware readiness has separate props.
prop twrp.modules.loaded true
prop sys.r97.ui.ready 1
echo R97_UI_READY
