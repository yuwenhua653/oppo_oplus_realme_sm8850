R87 CP initialization and voltage-tuning error repair — compile proof only

Parent: successful R86 head 96f969059c9fb2ccfbf2f5ac83e1f864770da21c,
run 39726426245. Frozen R86 build/source contracts and all earlier source
preparation are checked before applying this round's two C source overlays.

Only sc8581.c and mca_strategy_quickchg.c may change. The actual SC8585
compatible and variant support already exist; no forced ID or alias is added.
The overlay propagates mandatory CP initialization failures and prevents
adapter voltage tuning from continuing after failed CP operations. Existing
thermal, voltage/current settings, firmware programming and authentication
policy are retained. The prior R84 USB supply failure handling is preserved
at its exact postimage, rather than reapplying an obsolete R61 preimage.

The true single/parallel FG enum is extracted from the pinned production
strategy_fg.h. Tests exercise type 0 as single and type 1 as parallel. The real
FG compile action must consume this exact header, while the BQ action must
consume its exact private header and generated external-module config.
CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING remains disabled in the actual config.

CI prepares and verifies R85 and R86, executes their source suites, then
applies R87 and executes the CP, voltage-tuning and corrected fanout suites.
It builds only the coherent inactive47 plus retained core references once.
It does not separately rebuild accepted ADC/VADC or readonly gauge targets.

Artifacts bind the actual changed sources and read-only guard snapshots,
action provenance, config, reports and every collected output byte. They are
validation_only: no runtime activation, flash image, owner handover, hot-unload,
authentication bypass or charging policy override is created by this route.

Local gate:
  python3 r87-build-route/build_safety.py --repo-root . --check-inputs
  python3 r87-build-route/test_build_guards.py
  python3 r87-build-route/test_source.py --output <fresh-output>
