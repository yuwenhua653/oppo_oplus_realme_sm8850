# R72 charging transport and read-only telemetry compile route

This route compiles and collects exactly `qti_pmic_glink.ko` and
`myron_mca_readonly.ko`. It does not produce a flash package or enable either
module on a device. The 49-target R61 route, the R70 gauge and all boot images
remain unchanged.

The two target labels are:

- `//vendor/qcom/sm8850:canoe_perf/drivers/soc/qcom/qti_pmic_glink`
- `//vendor/qcom/sm8850:canoe_perf/drivers/power/supply/myron_mca_readonly/myron_mca_readonly`

A clean hosted runner still compiles the pinned common kernel and QTI's declared
DDK dependencies. It does not explicitly build the old MCA closure, the vendor
BQ module or camera. Only the two requested KOs are collected; prerequisite
symvers and the common Image/config/release metadata are retained as evidence.
The newly built Image is never substituted for the device's original Image.

## R72 fix1: exact device-tree node identity

The R72 capture showed successful module insertion followed by a failed bind.
The client compared `device_node.full_name` with an absolute DT path, but the
pinned kernel stores the node basename in that field. The old host fixture
incorrectly supplied an absolute name and missed this failure.

The fix resolves `/soc/pmic-glink/mca,adsp_glink` with
`of_find_node_by_path()`, requires that exact node pointer, and releases the
lookup reference. The fixture now uses real basename-style names and checks
rejection of missing or different nodes, including an identically named node
at another path. The QTI transport, six GET properties, request limits and
read-only loading policy are unchanged. A successful build still requires
actual module ABI review and a new device capture before claiming a working
bind or firmware GET response.

## Reproducible preparation

The workflow validates its exact contract digest, all new input hashes and the
unchanged R60/R61 source contracts before source sync. Production source host
tests and integration rejection tests run first. The existing verified R18
preparation and R13/R60/R61 source overlays are applied unchanged. A final R72
overlay has exactly six allowed destinations: QTI C/header, new client C, and
three append-only build fragments. Every Git revision and every preimage is
checked before any R72 write. Unexpected inputs stop the build.

The common source is `41a2024a9e2eb66ab0643a865d74943b4ee3cff8`; the QTI tree is
`557159b6a0d06f1c6f07ec4c1f22bc9309a113e4`. The inherited source lock also pins
Kleaf, Clang and every other source project. Mutable release or branch names
are not used for source sync.

The original public API and data layouts are preserved. The only new public
API is `pmic_glink_unregister_client_sync`, including its disabled-config stub.
The client must import this new symbol with no old unregister fallback. After
compilation, the actual two ELF files must expose/import it with matching CRCs.
This ensures the client cannot silently use an old transport lacking the new
contract, but is not a complete proof of runtime ABI compatibility.

## Remaining deployment gates

The compiled files need a separate review against the installed baseline:

- Original Image SHA256 `2fa774b4ffdd75064fb733bb2cad071b02b1813ad5cd54bae32bda2247ef18a7`.
- Kernel release `6.12.81-android16-6-maybe-dirty-4k`.
- Every module import, namespace, CRC and signature policy; original Image
  permitted imports and protected exports; callback CFI types.
- QTI's original exports and the retained consumers, including USB/Type-C.
- Safe loading/replacement sequence and live read-only protocol observations.

The runtime ABI status stays `NOT_YET_VALIDATED`. No real charging improvement,
charger status publication, successful GET or hardware test is asserted by CI.
Parent QTI transport hot-unbind remains outside the lifetime patch's scope.

## CI behavior

Only a push changing this workflow or `r72-build-route/**` triggers the new job.
Do not additionally dispatch a second run for the same push. The older R61
workflow watches its own file and `r61-build-route/**`, so these new files alone
do not trigger the old 49-target job.

Artifacts contain only the new R72 sources, compile outputs and diagnostic
reports. Existing vendor BQ/auth source files are not added to an upload path.
