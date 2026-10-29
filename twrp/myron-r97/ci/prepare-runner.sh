#!/bin/bash
set -eo pipefail
# Destructive cleanup is limited to disposable GitHub-hosted runner tools.
[ "$RUNNER_ENVIRONMENT" = github-hosted ] && [ "$RUNNER_OS" = Linux ] || exit 1
exec > >(tee "$RUNNER_TEMP/r97-evidence/runner.log") 2>&1
df -h /
free -h
sudo rm -rf /usr/local/lib/android /usr/share/dotnet /opt/ghc \
    /usr/local/share/boost /opt/hostedtoolcache/CodeQL \
    /usr/local/share/powershell /usr/share/swift
sudo docker system prune --all --force
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    repo git git-lfs gnupg flex bison build-essential zip unzip curl \
    zlib1g-dev libc6-dev-i386 lib32z1-dev lib32ncurses-dev \
    libncurses-dev x11proto-core-dev libx11-dev libgl1-mesa-dev \
    libxml2-utils xsltproc fontconfig python3 python-is-python3 \
    lz4 liblz4-1 zstd cpio rsync bc ca-certificates openjdk-17-jdk \
    gcc-aarch64-linux-gnu
sudo apt-get clean
# Supply bounded swap without replacing the runner's existing swap.
if [ "$(df --output=avail -k "$RUNNER_TEMP" | tail -1)" -lt 73400320 ]; then
    echo 'Need at least 70 GiB free before source sync; aborting before an expensive build.' >&2
    exit 1
fi
sudo fallocate -l 8G "$RUNNER_TEMP/r97.swap"
sudo chmod 600 "$RUNNER_TEMP/r97.swap"
sudo mkswap "$RUNNER_TEMP/r97.swap"
sudo swapon "$RUNNER_TEMP/r97.swap"
mkdir -p "$RUNNER_TEMP/r97-aosp"
df -h /
free -h
repo version
dpkg-query -W repo git gcc-aarch64-linux-gnu openjdk-17-jdk > "$RUNNER_TEMP/r97-evidence/host-packages.txt"
