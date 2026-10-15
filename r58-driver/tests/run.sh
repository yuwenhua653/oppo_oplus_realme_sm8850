#!/bin/sh
set -eu
cd "$(dirname "$0")"
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT HUP INT TERM
${CC:-gcc} -std=c11 -Wall -Wextra -Werror -O1 -g \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  test_frame.c -o "$tmpdir/test_frame"
# This parser allocates no heap memory. The host's ptrace sandbox prevents
# LeakSanitizer /proc traversal; retain ASan bounds and UBSan instrumentation.
ASAN_OPTIONS=detect_leaks=0 "$tmpdir/test_frame"
