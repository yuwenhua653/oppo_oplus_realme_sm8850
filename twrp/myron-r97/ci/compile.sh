#!/bin/bash
# Android envsetup/lunch run without nounset or errexit. Inspect their statuses
# explicitly; older vendor setup functions misbehave with inherited shell flags.
set +e
set +u
set -o pipefail
evidence="$RUNNER_TEMP/r97-evidence"
exec > >(tee "$evidence/build.log") 2>&1
cd "$RUNNER_TEMP/r97-aosp" || exit 1
export ALLOW_MISSING_DEPENDENCIES=true
source build/envsetup.sh
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
lunch twrp_sm8850
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
m -j"${R97_BUILD_JOBS:-4}" recoveryimage
rc=$?
printf '%s\n' "$rc" > "$evidence/compiler-exit-code.txt"
[ "$rc" -eq 0 ] || exit "$rc"
test -s out/target/product/sm8850/recovery.img || exit 1
echo 'Recovery compiler candidate completed; runtime injection and PID1/vendor_boot pairing remain mandatory.'
