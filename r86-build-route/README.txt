R86 fast-charge mode initialization and error handling — compile proof only

Parent: successful R85 head9c932f7bc81d045e803f3b639fa12c9cf7f63a73,
run39689880487. The exact R85 build/source contracts and all inherited source
preparation remain pinned. The R86 overlay may alter only full BQ source,
its private chip-state header, and quick-charge strategy source.

The route first prepares and verifies R85 and executes its production-C suites.
It then applies the exact reviewed R86 patch, executes new real production-C
fault cases on the actual workspace, and builds the fixed inactive47 closure
plus core references exactly once. It does not rebuild retained R84 ADC/VADC
or readonly gauge modules as separate candidates.

The actual BQ compiler must consume the target-owned generated config with
CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING disabled. Both changed C files and the
private header are bound to actual action inputs and copied from their final
workspace postimages into the locked output artifact.

All outputs remain validation_only. There is no flash image, module activation,
charging-owner handover, authentication bypass, firmware programming, thermal
limit override, voltage/current policy change, or hot-unload procedure.
Current accepted R84 runtime remains the device baseline.

Local gate:
  python3 r86-build-route/build_control.py --repo-root . --check-inputs
  python3 r85-build-route/test_build_guards.py
  python3 r86-build-route/test_build_guards.py
  python3 r86-build-route/test_source.py --output <fresh-output>
