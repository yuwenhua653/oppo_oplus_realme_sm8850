#!/bin/bash
set -eo pipefail
adapt="$GITHUB_WORKSPACE/twrp/myron-r97"
mkdir -p "$RUNNER_TEMP/r97-evidence"
exec > >(tee "$RUNNER_TEMP/r97-evidence/input-check.log") 2>&1
python3 "$adapt/validate_source.py"
python3 "$adapt/test_runtime.py"
python3 "$adapt/ci/apply-compile-only.py" --self-test
cp "$adapt/source-lock.json" "$RUNNER_TEMP/r97-evidence/"
echo 'Public-source compiler candidate only; no private runtime bytes are present.'
