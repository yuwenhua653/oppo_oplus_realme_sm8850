# R83 power compile validation

This route applies one bounded-cache change to the exact R75 `myron_mca_readonly` source on the frozen R79 source-preparation chain. A transient USB GET failure may retain the original complete snapshot only while its original lifetime remains valid. It never sends SET commands or extends the cache timestamp. Observed unplug, changed status, malformed values and lifecycle/epoch changes invalidate the snapshot.

The `r83-power-candidate` artifact contains exactly one KO, `myron_mca_readonly.ko`. The current R82 kernel, QTI transport, CNSS/WLAN and all other installed modules remain the runtime baseline. Compiled prerequisite KOs are excluded. Core Image, configuration, symvers and release are compile evidence, not replacement selections.

The separate `r83-validation-only` artifact contains the inactive full BQ fuel-gauge module and ADC/VADC providers. Those modules are not runtime candidates. Full BQ still has a known stock/source FG buffer-layout difference; this run does not enable full MCA, firmware updates or high-voltage charging. ADC activation requires its own exact retained-kernel/provider ABI and DT/load review. The actual ADC external config must disable `CONFIG_QCOM_SPMI_ADC5_GEN3_DEBUG_LOGGING`, which enables a panic-on-fault diagnostic path.

Both artifacts require exact source preimages/postimages and source locks. Bazel action graphs bind reviewed source inputs to actual target-owned KO/symvers outputs. The whole patched MCA production C translation unit runs under host kernel stubs with Werror, ASan and UBSan. The full BQ tests execute extracted exact production functions against controlled I2C behavior. These tests do not claim on-device validation. Neither artifact is flashable or runtime-ABI approved.

The only push trigger is this R83 workflow or files under `r83-build-route/` on `codex/myron-r61-battery`. Ancestor routes and prior workflows are not modified. The workflow checks the frozen contract before syncing sources, builds explicit reviewed targets and mandatory dependencies, and uploads the candidate and inactive validation outputs under different names. No device load or image assembly is performed.
