# R74 read-only USB and battery-status compile route

This route compiles and collects exactly three independently reviewed modules:

- `//vendor/qcom/sm8850:canoe_perf/drivers/soc/qcom/qti_pmic_glink`
- `//vendor/qcom/sm8850:canoe_perf/drivers/power/supply/myron_mca_readonly/myron_mca_readonly`
- `//vendor/qcom/sm8850:canoe_perf/drivers/power/supply/myron_bq_readonly`

It does not produce a flash package or install modules on a device. R74 extends
the GET-only MCA client with optional read-only Linux USB power-supply reporting
and extends the independent gauge with optional battery-status reporting through
the core power-supply interface. It adds no charging-control command, charger
policy, gauge authentication or firmware operation. Every reporting option is
separate from module build selection and remains subject to runtime review.

R73 device evidence established binding and valid replies for the six fixed GET
properties. Those observations do not qualify this changed R74 implementation,
prove high-power charging, or authorize increasing input current. The QTI
transport and its public header remain byte-identical to the R73 reviewed pair.
The R73 exact-device-tree-node lookup fix is retained.

## Reporting opt-ins and failure behavior

The MCA `enable_power_supply` option defaults to false and requires the existing
`enable_readonly` opt-in. With reporting disabled, the original diagnostic limit
of 60 rounds / 360 GET attempts is retained. With reporting enabled, the same six
GET properties refresh on delayed work scheduled five seconds after each round;
reporting can continue beyond 60 rounds. Cached supply data is accepted for at
most 15 seconds and is invalidated on disconnect, failed/incomplete rounds,
removal or counter exhaustion. Three consecutive timed-out rounds stop polling
and invalidate published data; an old successful snapshot is not kept as live
charging state. GET failures do not trigger charging-control writes.

The gauge `enable_status_readonly` option also defaults to false and requires
both `enable_readonly` and `enable_extended_readonly`. It forwards STATUS only
from the identified `usb` provider with MODEL_NAME `myron-mca-readonly`; missing,
removing, unrecognized or unreadable suppliers result in UNKNOWN. It sends no
firmware GET and does not infer charging state from gauge current or raw flags.
The existing SOC, voltage, temperature and optional current reads stay separate.
These opt-ins describe the implementation and do not authorize live module
insertion or change the compile-only scope of this route.

## Reproducible preparation

The workflow validates its exact contract digest, all new input hashes and the
unchanged R60/R61 source contracts before source sync. Whole production-source
host tests for transport, client and gauge, plus integration rejection tests,
run first. The existing verified R18 preparation and R13/R60/R61 overlays are
applied unchanged.

The final R74 overlay has exactly seven allowed destinations: QTI C/header,
independent client C, independent gauge C, and three appended build fragments.
The gauge replaces only the pinned independently written R61 gauge source
(preimage SHA256 `6b546907c6d24f164519b14e5e22ccfa78a7ff704c4cb969656b6ef42590b1f9`).
Its existing target registration and build selection are reused. Every Git
revision and every preimage is checked before any R74 write. Unexpected inputs
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
matching CRCs. The gauge must have no module dependencies or custom MCA/QTI
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

Only a push changing this workflow or `r74-build-route/**` triggers this job.
Do not dispatch a duplicate build for the same push. Older R61/R72 workflows
watch their own route paths and are not triggered by these new paths alone.

Artifacts contain only R74 independently written source/test/build files,
compile outputs, source-lock metadata and diagnostic reports. Existing vendor
BQ/auth sources are not added to any upload path. This route does not publish
or upload the unchanged R61 source preparation directory.
