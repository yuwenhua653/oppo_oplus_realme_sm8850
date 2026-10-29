#!/bin/bash
set -eo pipefail
adapt="$GITHUB_WORKSPACE/twrp/myron-r97"
evidence="$RUNNER_TEMP/r97-evidence"
exec > >(tee "$evidence/sync.log") 2>&1
cd "$RUNNER_TEMP/r97-aosp"
git config --global user.name 'R97 TWRP builder'
git config --global user.email 'r97-builder@users.noreply.github.com'
repo init -u https://github.com/TWRP-Test/platform_manifest_twrp_aosp.git \
    -b 814b553116ceedde197f70389cff9661d81d8337 --depth=1 --no-clone-bundle
mkdir -p .repo/local_manifests
cat > .repo/local_manifests/myron-r97.xml <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <extend-project name="android_bootable_recovery" path="bootable/recovery"
    revision="8a58fc3b586b8a908337fa87529cfbbb119ec7bb" upstream="twrp-16.0" />
  <project name="lingqiqi5211/twrp_device_xiaomi_sm8850" path="device/xiaomi/sm8850"
    remote="github" revision="907b78a804f5a47c4ccd66da0e5dd776cefc077d"
    upstream="twrp-16.0" clone-depth="1" />
</manifest>
XML
repo sync -c --no-clone-bundle --no-tags --fail-fast -j4
test "$(git -C .repo/manifests rev-parse HEAD)" = 814b553116ceedde197f70389cff9661d81d8337
test "$(git -C bootable/recovery rev-parse HEAD)" = 8a58fc3b586b8a908337fa87529cfbbb119ec7bb
test "$(git -C device/xiaomi/sm8850 rev-parse HEAD)" = 907b78a804f5a47c4ccd66da0e5dd776cefc077d
repo manifest -r -o "$evidence/resolved-manifest.xml"
cp .repo/local_manifests/myron-r97.xml "$evidence/local-manifest.xml"
python3 "$adapt/ci/apply-compile-only.py" --source-root "$RUNNER_TEMP/r97-aosp"
git -C device/xiaomi/sm8850 diff --binary > "$evidence/device.diff"
git -C bootable/recovery diff --binary > "$evidence/recovery.diff"
cp device/xiaomi/sm8850/R97-COMPILE-ONLY.json "$evidence/"
df -h .
