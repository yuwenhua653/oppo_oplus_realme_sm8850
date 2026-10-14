# R55 targeted PAS source build

The workflow `build-myron-dsp-r55.yml` runs on pushes to
`codex/myron-r55-dsp-autoboot` and also supports manual dispatch.

It extracts the exact R18 archive already in the repository, synchronizes the
same source/toolchain lock, runs the unchanged R18 preparation steps, and applies
the R13 adaptation followed by the R18 SOCCP fix and the R55 DSP descriptor fix.
The five `hotfix_*.sh` bodies are copied verbatim from the existing R18 workflow
at commit `663a72185cdf479e5945a6822b4b8954b80ce314`; their hashes and original
step names are in `legacy-preparation-lock.json`.

The sole build command requests these three targets:

- `//vendor/qcom/sm8850:canoe_perf/drivers/remoteproc/qcom_q6v5_pas`
- `//common:kernel_aarch64`
- `//myron_artifact_metadata:kernel_release`

Bazel builds their declared prerequisites, including a cold core-kernel build.
The 142-module boot and full-device aggregate targets are never invoked.

The output artifact retains the fresh PAS module, its required Module.symvers,
core Image/config/release/symvers, patched C source, source lock, and descriptor
validator. Cquery enumerates the selected dependency graph; aquery must identify
the patched C source as an input of the action producing the requested PAS KO.
The descriptor validator checks the two auto-boot fields and preserved fields,
relocations, OF mappings, and the assignment into the remoteproc structure.

`r55-targeted-status.json` identifies the GitHub commit, run and attempt.
`artifact-lock.json` hashes all retained output, source and report files. A failed
retry starts with a false status and removes only this driver's prior output;
fresh outputs are retained when a later action or descriptor gate fails.

These are diagnostic compilation artifacts, not flashable images. The new core
Image is build evidence. Acceptance against the existing kernel/module ABI and
boot-image assembly happen separately after this workflow succeeds.
