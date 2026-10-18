# R75 read-only USB and battery-status compile route

This route compiles and collects exactly three independently reviewed modules:

- `//vendor/qcom/sm8850:canoe_perf/drivers/soc/qcom/qti_pmic_glink`
- `//vendor/qcom/sm8850:canoe_perf/drivers/power/supply/myron_mca_readonly/myron_mca_readonly`
- `//vendor/qcom/sm8850:canoe_perf/drivers/power/supply/myron_bq_readonly`

It does not produce a flash package or install modules on a device. Relative to
R74 fix1, only the MCA client's behavior changes: reporting rounds use a shorter
interval, changed/invalidated cache notifications do not wait an additional
fixed interval, and a separate default-off diagnostic opt-in admits one fixed
five-property GET sequence. QTI transport, public header and independent gauge
production sources remain byte-identical to the reviewed R74 inputs.

## Reporting opt-ins and failure behavior

`enable_readonly` and `enable_power_supply` still default to false. Reporting
mode schedules its next six-property core round 2000 ms after the current
work, including at most one optional diagnostic GET; notifications for changed or invalidated cached state are queued without
an additional fixed delay. This does not claim a hard two-second Android UI
response deadline. No UCSI notifier or charging-control path is introduced.
The ordinary seven-line core snapshot and power-supply property set are unchanged.

Without reporting enabled, the original 5000 ms delay and 60-round / 360-request
diagnostic limit are retained. Cache validity remains at most 15000 ms, and
three consecutive timed-out core rounds stop polling and invalidate state.
Disconnect, incomplete/invalid data, removal and counter exhaustion fail closed.

`enable_extra_diagnostics` also defaults to false and requires both existing
MCA opt-ins. It may run once per loaded module instance, only after fresh core
data first reports ONLINE=1 and raw USB_REAL_TYPE=11 (PD; no PPS or
authentication capability is inferred). After each
successful core publication it attempts at most one fixed GET with a four-byte
property-value payload:

| Raw property | ID |
| --- | --- |
| CHG_TYPE | `0x2002` |
| AICL_STATUS | `0x2029` |
| PPS_MAX_CUR | `0x21013` |
| PPS_APDO_MAX | `0x21014` |
| PPS_STATUS | `0x21019` |

The sequence has at most five total attempts. Any failure or core-context change
ends it without retry. Its cache and request accounting are separate from core
reporting; raw diagnostic values do not set battery or USB properties and are
not treated as proof of PPS or high-power charging. No property address or write
operation can be selected by the caller. Its separate read-only `diagnostics`
attribute has one header and five rows, explicitly marked `historical=1 atomic=0`.
A blocked diagnostic send can delay the next core round; the independent 1000 ms
expiry watchdog and direct property-read freshness checks remain active.

The unchanged independent gauge retains the default-off `enable_status_readonly`
option and its original telemetry opt-ins. It forwards STATUS only from the
identified `usb` provider with MODEL_NAME `myron-mca-readonly`; unavailable,
removing or unrecognized suppliers yield UNKNOWN. Current and raw gauge flags
do not imply charging status. CI neither enables these module options on a
phone nor claims that Android status latency or low charging power is repaired.

## Reproducible preparation

The workflow validates its exact contract digest, all new input hashes and the
unchanged R60/R61 source contracts before source sync. Whole production-source
host tests for transport, client and gauge, plus integration rejection tests,
run first. The existing verified R18 preparation and R13/R60/R61 overlays are
applied unchanged.

The final R75 overlay has exactly seven allowed destinations: QTI C/header,
independent client C, independent gauge C, and three appended build fragments.
The R74-identical gauge payload replaces only the pinned independent R61 source
(preimage SHA256 `6b546907c6d24f164519b14e5e22ccfa78a7ff704c4cb969656b6ef42590b1f9`).
Its existing target registration and build selection are reused. Every Git
revision and every preimage is checked before any R75 write. Unexpected inputs
stop the build. R61 source contracts and their locked files are not modified.

The common source is `41a2024a9e2eb66ab0643a865d74943b4ee3cff8`; the QTI tree is
`557159b6a0d06f1c6f07ec4c1f22bc9309a113e4`. The inherited source lock also pins
Kleaf, Clang and every other project. Mutable branch names are not used for
source sync.

A clean runner compiles the pinned common kernel and declared DDK prerequisites.
Only the three selected KOs are collected, together with prerequisite symvers
and common Image/config/release metadata. The newly built Image is evidence;
it must not replace the installed baseline Image during a later assembly.
The vendor BQ module, complete MCA framework and camera are not build targets.

## Compiler-output checks

The existing QTI public API and layouts are preserved. The reviewed additional
API remains `pmic_glink_unregister_client_sync`, including its disabled-config
stub. The MCA client must import this new symbol without an old-unregister
fallback. Actual compiled transport/client ELFs must export/import it with
matching CRCs. The actual client ELF must expose exactly the three reviewed
boolean opt-ins. Host compilation models the kernel `current` macro and enables
`-Wstrict-prototypes` to retain the R74 fix1 regression gate.
The gauge must have no module dependencies or custom MCA/QTI
imports; it obtains charger telemetry through the core power-supply API.

The action graph must connect each exact source set to its expected KO. All
three KOs and their symvers must be present, ELF identities must match, and the
output inventory must contain no extra KO. The candidate-complete marker is
written only after the complete artifact lock is created. This establishes
compile/source provenance; it is not a complete runtime ABI review.

## Remaining deployment gates

A separate assembly review must validate every compiled module against:

- Original Image SHA256 `2fa774b4ffdd75064fb733bb2cad071b02b1813ad5cd54bae32bda2247ef18a7`.
- Kernel release `6.12.81-android16-6-maybe-dirty-4k`.
- All imports, CRCs, namespaces, protected exports, signature policy and CFI.
- Retained QTI consumers, including USB and Type-C.
- Native loader contract, safe startup/unload order, freshness and disconnect
  behavior, Android state presentation and actual device observations.

Runtime ABI status stays `NOT_YET_VALIDATED`. CI does not claim hardware success,
real charging improvement or deployment authorization. Parent QTI hot-unbind
remains outside the transport lifetime patch's scope.

## CI and publication scope

Only a push changing this workflow or `r75-build-route/**` triggers this job.
Do not dispatch a duplicate build for the same push. Older R61/R72/R74 workflows
watch their own route paths and are not triggered by these new paths alone.

Artifacts contain only R75 independently written source/test/build files,
compile outputs, source-lock metadata and diagnostic reports. Existing vendor
BQ/auth sources are not added to any upload path. This route does not publish
or upload the unchanged R61 source preparation directory.

A separately reviewed `r75-capture-source/` directory may accompany the same
commit. It is collector source only, outside this kernel route and input lock;
it contains no flash image or flash entry point and is not a flashable package.
