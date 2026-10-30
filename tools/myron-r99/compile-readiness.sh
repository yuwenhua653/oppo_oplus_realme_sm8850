#!/bin/bash
set +e
set +u
set -o pipefail
adapt="$GITHUB_WORKSPACE/tools/myron-r99"
evidence="$RUNNER_TEMP/r99-evidence"
exec > >(tee "$evidence/readiness-build.log") 2>&1
cd "$RUNNER_TEMP/r97-aosp" || exit 1
python3 "$adapt/prepare-readiness.py" "$RUNNER_TEMP/r97-aosp"
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
export ALLOW_MISSING_DEPENDENCIES=true
source build/envsetup.sh
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
lunch twrp_sm8850
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
m -j"${R99_BUILD_JOBS:-4}" r99_readiness_broker r99_readiness_client
rc=$?
printf '%s\n' "$rc" > "$evidence/readiness-compiler-exit-code.txt"
[ "$rc" -eq 0 ] || exit "$rc"
python3 "$adapt/collect-readiness.py"
