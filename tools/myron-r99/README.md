# R99 Recovery init source build

Source bytes are checked against both SHA256 and official Git blob identities
after environment setup/lunch and before each compiler invocation. The baseline
fixtures preserve upstream EOF bytes exactly. Source records are checked again
after compilation. If any capture check fails, raw init/symbol outputs and
actual source evidence are retained as unqualified diagnostics, with no success
metadata and no change to the known baseline binary qualification.

Before compiling, the selected Clang from the pinned Soong configuration and
the required ELF inspection tools must run successfully. Unused legacy Clang
installations are listed without execution. After compiling, the selected
compiler identity must remain unchanged and its producer string must appear
in the matching-text symbol file. Optional Ninja command capture records any
failure as diagnostic evidence. Capture regression tests cover the legacy
compiler failure and the full metadata path through symbol disassembly.

This build addresses the unobserved Recovery-header SELinux selector from the
R98 phone test. It compiles the existing Recovery `init` from the successful
396-project R97 snapshot, then rebuilds the same target with a Recovery-only
enforcement selector. Android system init remains outside this build.

The source patch preserves the existing fatal error handling around
`security_setenforce`. The host tests extract and execute the production function
for both normal and `RECOVERY` builds. These tests do not replace an Android build
or a phone test.

The workflow runs on pushes to `codex/myron-r99-selinux` which change this directory
or its workflow, and supports manual dispatch. It builds only
`init_second_stage.recovery` plus required dependencies. The initial full source
sync and Soong graph are still needed on a new runner.

Baseline and selector compilation are separate workflow steps on the same runner
and output tree. The complete baseline binary, symbols and evidence are uploaded
immediately before the selector build. This checkpoint is not a flash image or
a full build cache. It protects completed evidence if a later runner shutdown
prevents even `always()` cleanup steps from running; it cannot prevent shutdown.
The selector stage requires the known baseline identity and unchanged original
compiler preflight before applying its patch. Stage logs and bounded resource
snapshots remain separate. Both stages retain the normal `m` build path.
A newer reviewed push or manual run requests cancellation of the older run in
the same concurrency group, including a run whose runner stopped while GitHub
still reports it active. The group remains shared to avoid parallel builds;
this cancellation request is not a fix for the runner shutdown itself.

After preserving both init outputs, the same source checkout also compiles the
fixed-interface `r99_readiness_broker` and `r99_readiness_client` targets. They are
separate static native compiler candidates. No service, file/property context or
phone-image integration is performed, and a readiness compile failure does not
remove the already uploaded init evidence.

No private ROM dumps, modules, runtime images or credentials are uploaded.
Outputs are the original and modified init binaries and their source/ELF/library
evidence. They cannot be flashed directly. A baseline hash mismatch is retained
in the baseline checkpoint and then blocks the selector stage. Final baseline
qualification also remains required; a mismatch is never accepted as equivalent.

Keep the shared Android/REC boot setting Permissive until a locally assembled
candidate and its independent source/ELF/image review are complete. The known
R98 fix1 image remains the functional baseline.
