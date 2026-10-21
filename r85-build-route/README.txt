R85 full-BQ safety source repair — compile proof only

Parent: published R84 commit5e4568f2ff6ed8257a3c9f5974605cafab8e956a.
The new route retains every frozen R84 preparation input and applies one exact
full-BQ source patch after the complete inherited preparation chain. A mismatch
in any inherited source postimage, new patch, fixture, header, or source config
stops before compilation.

Only the47 declared full-MCA source modules and the retained core reference
targets are built. The accepted R84 ADC/VADC/readonly gauge targets are not
rebuilt as separate candidates. All outputs remain validation_only with no
runtime candidates, no activation permission, and no flashable image.

The actual BQ action must consume the generated canoe_perf config and its
target-owned setup. CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING must remain disabled;
the actual external .config is included in the output artifact. This check
does not replace later retained-kernel ABI, runtime ownership, or device tests.

The CI production gate includes the three author fault-injection suites and
the independent composed-production matrix. These execute extracted production
C, including the original-source negative proofs; they do not replace target
kernel compilation or real hardware acceptance.

Local preparation after the composed patch and production suites are reviewed:
  python3 r85-build-route/freeze_inputs.py --source-after <composed.c> \
    --patch <composed.patch> --test-contract <test-contract.json>
  python3 r85-build-route/build_bq.py --repo-root . --check-inputs
  python3 r85-build-route/test_build_guards.py
  python3 r85-build-route/test_source.py --output <fresh-output>

Do not upload or dispatch an unfrozen route. The workflow SHA placeholder and
missing build contract deliberately prevent a draft from passing preflight.
The route creates no charging-control handover, authentication bypass, voltage
or current policy change, firmware update, or hot-unload procedure. The accepted
R84 runtime remains the device baseline until a separate image is qualified.
