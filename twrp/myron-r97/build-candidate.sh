#!/bin/bash
# Run from a fully synced TWRP checkout after apply.py. Produces a candidate,
# not a released/flashing pair. Avoid nounset around Android envsetup/lunch.
if [ ! -s device/xiaomi/sm8850/recovery/root/r97-runtime/module-plan.json ]; then
    echo 'Missing prepared R96 runtime. Run prepare_runtime.py and apply.py.' >&2
    exit 1
fi
if [ ! -f device/xiaomi/sm8850/R97-SOURCE-REVIEW.json ]; then
    echo 'Source overlay has not been applied.' >&2
    exit 1
fi
source build/envsetup.sh || exit 1
lunch twrp_sm8850 || exit 1
m recoveryimage || exit 1
echo 'Candidate built: out/target/product/sm8850/recovery.img'
echo 'NOT FLASH-QUALIFIED: new init/recovery/RC pins require a matching PID1/vendor_boot.'
