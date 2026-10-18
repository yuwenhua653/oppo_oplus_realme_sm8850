# R76 compile-only basic buck foundation

This is a source repair and build gate. It does not generate a flash package,
change the working R75 image, load original MCA modules, or raise charge current.
The authoritative runtime kernel remains the original Image with SHA256
`2fa774b4ffdd75064fb733bb2cad071b02b1813ad5cd54bae32bda2247ef18a7`.

The route builds on repository commit
`07201ea64edafef3ef3841e6386aba400ec4ca65`. It directly reuses the frozen
R75 checker, overlay, three whole-source host suites, compiled metadata checks,
and R61 preparation/build helpers. R75 contract SHA256 is
`d191be88cb0fb978e54becb894cceaa27a0c02962eafe99ddbe5711862d34d56`.
The R75 files and earlier contracts are not rewritten or copied into this route.

## Three exact new postimages

All paths below are relative to `vendor/qcom/sm8850` in the prepared workspace.
The new payload contains only these three charger source files.

| Production file | Change |
| --- | --- |
| `drivers/power/supply/mca/mca_common/mca_adsp_glink.c` | Reuse the reviewed R71 request state/error patch exactly. Admit requests while UP, report transport loss/timeout/remote rejection, and prevent failed reads from publishing data. |
| `drivers/power/supply/mca/mca_qcom_subpmic_proxy/mca_qcom_subpmic_proxy.c` | Return `mca_adsp_glink_write_prop` from ICL `0x2008`, FCC `0x2005`, charge-enable `0x2003`, and FV `0x2007` setters. IDs, payload widths, arguments and units are unchanged. |
| `drivers/power/supply/mca/mca_strategy/strategy_charger/mca_strategy_buckchg.c` | Initialize initial `online` to zero and require the getter to succeed before the initial connected event. Registrations, policy, and teardown remain unchanged. |

The R71 transport exact source SHA256 is
`b766aba518a331a2833f40caa402bfb767f59149e8c593699a27d14034115df5`.
Its preimage is
`02ee6caf120a010e712480e4b655376aff62183776f226b9f82dd69d37b7a8b9`.
The subpmic postimage is
`721a6bd66e2e03c70673ae35298171667cc516006ffbfd3727a4d8bf1ae06e19`;
the buck postimage is
`d30335d6bbc64e522c28fe799d41ecd0946688f4654ca86ff94a88165a6c54b7`.
All pre/postimages and inherited source bytes are locked in
`foundation-contract.json`.

## What CI actually builds and collects

Six explicit DDK targets are required: `qti_pmic_glink`,
`myron_mca_readonly`, `myron_bq_readonly`, `mca_adsp_glink`,
`mca_qcom_subpmic_proxy`, and `mca_strategy_buckchg`.
The first three retain their exact R75 source/target definitions.
The new sources must appear in their own target action chains before build.
Bazel builds their declared prerequisites: the retained registry has 30 local
targets in the three new targets' transitive closure, plus external QTI, SMEM
and SOCINFO targets. This is a compile dependency count, not a set selected
for installation. Only the six explicit KO files, their actual export/import
metadata, available dependency symvers, and core ABI evidence are collected.
No original fuel-gauge/authentication implementation or keys are uploaded.
Presence of a dependency symvers does not prove its KO was collected.

The build verifies the frozen R61 preparation, plans all seven R75 writes and
all three new writes before applying any overlay mutation, then verifies all
resulting workspace files before and after compilation. Collection checks six
unique actual ELF identities, release strings, the existing QTI/read-only pair,
and the new MCA transport/proxy read/write CRC pair. Its completion marker is
created only after those checks. It explicitly does not approve runtime ABI,
CFI, loading, hardware behavior, or a complete installable dependency closure.

The new workflow triggers only on its own workflow file or `r76-build-route/**`.
The reports upload is limited to this new source route, workflow, source lock,
and named build/test reports. The output upload is limited to the verified
compile artifact directory. No runtime images, previous capture files, private
source trees, or original BQ/authentication sources are included.

## Local checks

Use the full repository checkout at the pinned parent commit with this new
route overlaid, and a new empty report directory:

```sh
python3 r76-build-route/foundation_inputs.py --root "$PWD"
python3 r75-build-route/test_integration.py
python3 r76-build-route/test_integration.py
python3 r76-build-route/run_host_tests.py --root "$PWD" --reports /tmp/r76-new-reports
```

The three inherited whole-source suites retain the kernel `current` macro and
strict-prototypes regression gates. The migrated R71 transport suite tests its
whole source with the actual R75 public QTI header, ASan/UBSan and strict
prototypes. Its own MCA header is copied from the exact prepared source and
checked against the inherited R61 workspace lock. The new control harness
extracts the four complete setters and the complete production probe, tests
56 setter cases and 12 probe cases, and records full source hashes. The original
preimages fail the error-propagation and failed-getter/false-connect regressions.
These host stubs establish source behavior, not firmware behavior.

## Runtime limitations retained

The unchanged original buck/subpmic group is not a minimal passive addition.
The working R75 selected module set has no original MCA providers. Buck needs
registered fuel-gauge callbacks and event routing. Existing thermal code waits
for quick-charge voters even on its wired path; the proxy initialization also
queries CP state and attempts additional firmware SETs. Authentication votes
must not be bypassed or satisfied with fabricated success. The independent
read-only gauge does not register the original MCA fuel-gauge class callbacks.

These source fixes do not establish board protection, single-writer ownership,
genuine battery/auth support, charging policy, firmware limits, provider
registration safety, or unload/reprobe safety. The old late-probe and teardown
limitations remain; no registrations were moved to pretend otherwise.
Before any runtime control change, a separate constrained adaptation and actual
kernel/module ABI/CFI and board-policy review are required. R75 stays the device
baseline throughout this compile-only step.
