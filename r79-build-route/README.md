# R79 repair candidates

R78 Runtime Fix1 remains the tested boot baseline, including its working audio
and brightness. This route applies the unchanged R13/R60/R61/R75/R76/R77/R78
preparation before the new, pinned source changes. It explicitly builds every
module that owns a modified production source and collects its real ELF and
Module.symvers. Compiling a module does not select it for installation.

The main-camera power-sequence fix was already present in R61 source, but the
R78 runtime still contained the old module with MAX=14. R79 explicitly builds
camera and requires the runtime assembler to replace and validate the module.
The source keeps Seq14=VANA1 and the original regulator/voltage validation.

The battery driver now exposes its existing, real temperature through the
kernel's standard tripless battery thermal zone. It changes no thresholds or
charging current. The display repair restores the missing flatmode validation
interface used by the sensor service's constructor; it retains the brightness
implementation and reads the current panel's own DT configuration.

Charging source repairs preserve firmware errors from protection setters,
propagate fuel-gauge authentication and adapter-power read failures, and
prevent replacing a live fuel-gauge provider. The original MCA charging stack
is not runtime-ready: the tested read-only gauge does not provide the complete
Myron battery, termination, authentication and thermal policy interfaces.
These fixes alone do not establish increased charging power or PPS support.

The Xiaomi touch framework gains bounded userspace operations, correct probe
failure propagation and publication/unwind ordering. Its FT3683 THP backend
and current HAL protocol are not yet connected. The current working direct
touch driver remains the runtime input path. The new xiaomi_touch module is a
compile-only prerequisite, not an enabled replacement.

Only camera, msm_drm and myron_bq_readonly are runtime replacement candidates.
Their actual installed-kernel ABI, source provenance and the complete retained
module set must pass the separate runtime assembler before creating an image.
The image retains the original kernel, DTB, boot configuration and the R78
Runtime Fix1 audio-load logic. Hardware behavior still requires device testing.

Run `python3 r79-build-route/r79_inputs.py --root .`, then
`python3 r79-build-route/test_integration.py` and
`python3 r79-build-route/run_tests.py --reports /absolute/reports`.
Tests use exact production functions or translation units, including old-source
negative controls; they do not replace the target kernel build or device tests.

For a local 8 GiB build host, use `build_repairs.py --jobs 2 --ram-mb 6144`
with the documented workspace/package/baseline/R18/repository arguments. The
default 10000 MiB budget is intended for the larger hosted CI runner.
