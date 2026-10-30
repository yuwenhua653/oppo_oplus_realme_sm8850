#!/bin/bash
# Preserve the successful envsetup/lunch handling: no inherited errexit/nounset.
set +e
set +u
set -o pipefail
adapt="$GITHUB_WORKSPACE/tools/myron-r99"
evidence="$RUNNER_TEMP/r99-evidence"
exec > >(tee "$evidence/build.log") 2>&1
cd "$RUNNER_TEMP/r97-aosp" || exit 1
export ALLOW_MISSING_DEPENDENCIES=true
source build/envsetup.sh
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
lunch twrp_sm8850
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
printf '%s\n' "TARGET_PRODUCT=$TARGET_PRODUCT" "TARGET_BUILD_VARIANT=$TARGET_BUILD_VARIANT" > "$evidence/product.txt"
python3 "$adapt/source_checks.py" "$RUNNER_TEMP/r97-aosp" baseline "$evidence/baseline-precompile-source.json"
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
m -j"${R99_BUILD_JOBS:-4}" init_second_stage.recovery
rc=$?
printf '%s\n' "$rc" > "$evidence/baseline-compiler-exit-code.txt"
[ "$rc" -eq 0 ] || exit "$rc"
python3 "$adapt/inspect-init.py" baseline
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
python3 "$adapt/apply-selector.py" "$RUNNER_TEMP/r97-aosp"
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
git -C system/core diff --binary -- init/selinux.cpp > "$evidence/system-core-selector.diff"
python3 "$adapt/source_checks.py" "$RUNNER_TEMP/r97-aosp" patched "$evidence/patched-precompile-source.json"
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
m -j"${R99_BUILD_JOBS:-4}" init_second_stage.recovery
rc=$?
printf '%s\n' "$rc" > "$evidence/patched-compiler-exit-code.txt"
[ "$rc" -eq 0 ] || exit "$rc"
python3 "$adapt/inspect-init.py" patched
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
echo 'Both init targets compiled. Baseline qualification, ELF review and local image assembly remain separate.'
