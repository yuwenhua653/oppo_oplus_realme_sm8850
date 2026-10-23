R88 boot-only MCA handover preparation

This source creates a fixed native loader only after actual R88 compilation and
retained-kernel ABI review. It does not build vendor_boot, contact a device or
claim authentication/fast-charge success. generate_contract.py defaults to a
non-activatable draft; --freeze-reviewed-r88 additionally requires explicit
reviewed CI head/run and successful matching reports/r88-status.json. The ABI
report must include PASS_R88_EXACT_ARTIFACT_IDENTITY. Old R87 outputs cannot
become an R88 runtime candidate.

Keep all normal249 files and paths, including identical hwid/miev. Skip both
old readonly-owner loader calls and add exactly45 coherent modules under
/vendor_dlkm/r32/r88-mca/<name>.ko using /vendor_dlkm/r32/r88-mca-start. The
normal249 plus45 provider set is294. No unload, unbind, hot retry or same-boot
old-owner fallback is provided. A partial insert remains a partial state.

The helper verifies every file before insertion, uses held verified module
file descriptors, checks the exact Live prefix and exclusive owners, and then
requires seven actual bindings, canonical battery/USB/auth paths, Battery/type
and the five authentication-attribute metadata. USB/type is adapter-dependent
and not fixed. The final failure log enumerates every missing binding, path,
Battery/type and auth metadata once; it reads no auth digest or flag contents.

The only loader edit replaces the old two synchronous owner calls before
vendor.all.modules.ready. Normal modules, TFA and later ready/DSP text and order
remain byte-identical. batterysecret keeps its normal service lifecycle.
Source module probes may write charging hardware; this is not a read-only
runtime experiment. Storage gates, auth and protection policies are not bypassed.

Usage:
  python3 -B generate_contract.py --runtime-contract <R84-contract>
    --baseline-reviews <actual-R84-ELF-reviews> --candidate <actual-R88-output>
    --abi <same-output-static294-review> --out <fresh-contract-directory>
    --freeze-reviewed-r88 --build-id <R88-ID> --expected-ci-head <R88-head>
    --expected-ci-run <R88-run>
  python3 -B prepare_native.py --contract <directory>/module-set.json
    --toolchain <verified-native-toolchain.json> --out <fresh-native-directory>

prepare_native.py double-builds and strips AArch64 static helpers byte-identically
and executes real native C tests under ASan/UBSan/Werror. Preparation records
all three source C/H pins and the exact toolchain-manifest pin for assembler
cross-checking. Image assembly and
independent final review remain separate gates.

test_native_guards.py accepts the exact historical R87 module-set solely as
non-activatable unit-test data. It forces RUNTIME_FROZEN=0, changes only the test
identity/path namespace and tests the real new C. It produces no runtime module
contract, R88 compatibility proof, helper release or image.
