#!/bin/bash
set -eo pipefail
adapt="$GITHUB_WORKSPACE/tools/myron-r99"
prior="$GITHUB_WORKSPACE/twrp/myron-r97"
mkdir -p "$RUNNER_TEMP/r99-evidence" "$RUNNER_TEMP/r99-deliver"
exec > >(tee "$RUNNER_TEMP/r99-evidence/input-check.log") 2>&1
python3 "$adapt/validate-inputs.py"
python3 "$adapt/prepare-readiness.py" --check-only
python3 "$adapt/test-controls.py" | tee "$RUNNER_TEMP/r99-evidence/CONTROL-TESTS.json"
python3 "$prior/validate_source.py"
python3 "$prior/test_runtime.py"
python3 "$prior/ci/apply-compile-only.py" --self-test
python3 "$adapt/selector/prepare_candidate.py"
python3 "$adapt/test-source-pipeline.py" "$prior" | tee "$RUNNER_TEMP/r99-evidence/SOURCE-PIPELINE-TESTS.json"
cp "$adapt/source-lock.json" "$RUNNER_TEMP/r99-evidence/"
cp "$adapt/selector/SOURCE-CANDIDATE-REVIEW.json" "$RUNNER_TEMP/r99-evidence/"
git -C "$GITHUB_WORKSPACE" rev-parse HEAD > "$RUNNER_TEMP/r99-evidence/adaptation-commit.txt"
echo 'Public source only; no private runtime modules or ROM data are transferred.'
