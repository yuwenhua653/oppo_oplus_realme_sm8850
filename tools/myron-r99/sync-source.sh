#!/bin/bash
set -eo pipefail
adapt="$GITHUB_WORKSPACE/tools/myron-r99"
prior="$GITHUB_WORKSPACE/twrp/myron-r97"
evidence="$RUNNER_TEMP/r99-evidence"
exec > >(tee "$evidence/sync.log") 2>&1
cd "$RUNNER_TEMP/r97-aosp"
git config --global user.name 'R99 init builder'
git config --global user.email 'r99-builder@users.noreply.github.com'
repo init -u https://github.com/TWRP-Test/platform_manifest_twrp_aosp.git \
    -b 814b553116ceedde197f70389cff9661d81d8337 --depth=1 --no-clone-bundle --no-use-superproject
test "$(git -C .repo/manifests rev-parse HEAD)" = 814b553116ceedde197f70389cff9661d81d8337
# The successful R97 resolved snapshot pins every project. Retain that exact
# default.xml during sync; do not re-resolve moving branch tips or superprojects.
cp "$adapt/resolved-manifest.xml" .repo/manifests/default.xml
test "$(sha256sum .repo/manifests/default.xml | cut -d' ' -f1)" = 5cae42baf25198ae0541061d87a7284c30807c396e5bceb1610de113f2b3578d
repo sync --no-manifest-update -c --no-clone-bundle --no-tags --fail-fast -j4
python3 "$adapt/verify-projects.py" "$RUNNER_TEMP/r97-aosp" "$evidence/projects.json"
repo manifest -r -o "$evidence/resolved-manifest.xml"
cp .repo/manifests/default.xml "$evidence/selected-manifest.xml"
repo version > "$evidence/repo-version.txt"
# Reproduce the successful product setup without uploading its private runtime.
python3 "$prior/ci/apply-compile-only.py" --source-root "$RUNNER_TEMP/r97-aosp"
git -C device/xiaomi/sm8850 diff --binary > "$evidence/device.diff"
git -C bootable/recovery diff --binary > "$evidence/recovery.diff"
cp device/xiaomi/sm8850/R97-COMPILE-ONLY.json "$evidence/"
df -h .
