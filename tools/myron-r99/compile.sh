#!/bin/bash
# Preserve the successful envsetup/lunch handling: no inherited errexit/nounset.
set +e
set +u
set -o pipefail
stage="${1:-}"
case "$stage" in
    baseline|patched) [ "$#" -eq 1 ] || exit 2 ;;
    *) echo 'Usage: compile.sh baseline|patched' >&2; exit 2 ;;
esac
adapt="$GITHUB_WORKSPACE/tools/myron-r99"
evidence="$RUNNER_TEMP/r99-evidence"
exec > >(tee "$evidence/$stage-build.log") 2>&1
resource_snapshot() {
    {
        date -u '+%Y-%m-%dT%H:%M:%SZ'
        df -h "$RUNNER_TEMP"
        free -h
        for file in /sys/fs/cgroup/memory.events /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.max; do
            if [ -r "$file" ]; then
                printf '%s\n' "$file"
                head -c 4096 "$file"
                printf '\n'
            fi
        done
    } 2>&1 | tee "$evidence/$stage-resources-$1.txt"
}
resource_snapshot before
trap 'build_rc=$?; resource_snapshot after; exit "$build_rc"' EXIT
cd "$RUNNER_TEMP/r97-aosp" || exit 1
export ALLOW_MISSING_DEPENDENCIES=true
source build/envsetup.sh
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
lunch twrp_sm8850
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
printf '%s\n' "TARGET_PRODUCT=$TARGET_PRODUCT" "TARGET_BUILD_VARIANT=$TARGET_BUILD_VARIANT" > "$evidence/$stage-product.txt"
if [ "$stage" = baseline ]; then
    python3 "$adapt/inspect-init.py" preflight
    rc=$?
    [ "$rc" -eq 0 ] || exit "$rc"
else
    # The workflow uploads the completed baseline before entering this stage.
    # Require its exact identity and original preflight; do not replace either.
    python3 - "$adapt" "$RUNNER_TEMP" <<'PY'
import json, runpy, sys
from pathlib import Path
adapt, temp = map(Path, sys.argv[1:])
source, evidence = temp/'r97-aosp', temp/'r99-evidence'
inspector = runpy.run_path(str(adapt/'inspect-init.py'))
lock = json.loads((adapt/'source-lock.json').read_text())
expected = {'bytes': lock['baseline_init_bytes'], 'sha256': lock['baseline_init_sha256']}
baseline = json.loads((evidence/'baseline-init.json').read_text())
if baseline.get('matches_known_REC_init') is not True or any(baseline.get(k) != v for k, v in expected.items()):
    raise ValueError('patched stage requires the qualified known baseline identity')
for path in (temp/'r99-deliver/baseline/init', source/'out/target/product/sm8850/recovery/root/system/bin/init'):
    if not path.is_file() or path.is_symlink() or inspector['identity'](path) != expected:
        raise ValueError('baseline compiler output changed before selector application')
preflight = json.loads((evidence/'toolchain-preflight.json').read_text())
if preflight.get('status') != 'PASS' or preflight['selected_toolchain'] != inspector['selected_toolchain'](source):
    raise ValueError('selected toolchain differs from preserved baseline preflight')
print('PASS preserved known baseline and original toolchain preflight')
PY
    rc=$?
    [ "$rc" -eq 0 ] || exit "$rc"
    python3 "$adapt/apply-selector.py" "$RUNNER_TEMP/r97-aosp"
    rc=$?
    [ "$rc" -eq 0 ] || exit "$rc"
    git -C system/core diff --binary -- init/selinux.cpp > "$evidence/system-core-selector.diff"
    rc=$?
    [ "$rc" -eq 0 ] || exit "$rc"
fi
python3 "$adapt/source_checks.py" "$RUNNER_TEMP/r97-aosp" "$stage" "$evidence/$stage-precompile-source.json"
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
m -j"${R99_BUILD_JOBS:-4}" init_second_stage.recovery
rc=$?
printf '%s\n' "$rc" > "$evidence/$stage-compiler-exit-code.txt"
[ "$rc" -eq 0 ] || exit "$rc"
python3 "$adapt/inspect-init.py" "$stage"
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
echo "$stage init target compiled and captured. Local image qualification remains separate."
