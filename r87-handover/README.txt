R87 boot-only MCA handover preparation

This directory creates a fixed native module-loader candidate. It does not
build a vendor_boot image, contact a device, or authorize runtime activation.
The currently generated R86 draft has RUNTIME_FROZEN=0 and the actual helper
entry point refuses to insert any module. Real R87 CI plus an independently
reviewed retained-kernel ABI closure must replace that fixture before freezing.

Preserve the healthy R84 normal249 and every normal module path/hash, including
the already loaded, byte-identical hwid/miev. Stop invoking the two readonly
gauge/MCA helpers. Add only coherent full45 in the reviewed dependency order.
The equivalent provider set is 249+45=294, with exactly one gauge, battery and
GLINK owner. No old-owner unload, device unbind, retry or same-boot fallback is
implemented. Partial insertion is an explicitly partial state. A worker timeout
does not prove a blocked module initialization was cancelled or rolled back.

The sole helper path is /vendor_dlkm/r32/r87-mca-start. New modules are fixed
under /vendor_dlkm/r32/r87-mca/<name>.ko. Its generated contract is installed as
module-set.json in that directory. There are no CLI-controlled paths or module
arguments. Before any insertion, all normal249 and new45 file hashes are
verified, with the new45 descriptors kept for finit_module. Each insertion is
surrounded by same-boot, capability, unique-owner and exact Live-prefix checks.

In addition to ELF dependencies, the order binds subpmic before USB/business
charger, business battery before strategy FG's initial battery lookup, and the
gauge/FG/CP/business charger before quick-charge strategy. A finite post-load
wait requires actual BQ, CP, GLINK, FG, business-driver and quick-charge strategy
binding plus the
canonical battery/USB identities and five authentication-attribute metadata.
Battery/type must be Battery. USB identity is its canonical business-charger
path and driver/module binding; USB/type is adapter-dependent (including Unknown,
USB_DCP and USB_PD), so no fixed USB/type value is required or read by this gate.
Host tests exercise each binding, path, Battery/type and auth-metadata rejection
in the actual final condition chain, plus unchanged owners across USB type changes.
The actual quick-charge probe already defers until FG initialization, CP
readiness and required voters exist. No new pre-load gate changes that behavior.
The final check also requires the quick-charge device to bind to its exact
strtategy-quick-charge driver and mca_strategy_quickchg module, so a loaded but
unbound quick-charge module cannot produce a complete status.
This verifies presence and binding only. No digest is read, no challenge or
authentication flag is written, and authentication/fast-charge success is never
asserted. Full-source module probe functions perform their normal initialization
and may write charging hardware; this is not a read-only runtime experiment.

The only loader edit belongs at the existing two synchronous helper calls,
before vendor.all.modules.ready. Keep all normal-loader, TFA and later DSP
startup text/order. The existing batterysecret service is expected to start in
its normal class last_start after the interface is available; this code does
not restart it, override its permissions/domain, or claim its result is valid.

Example draft preparation (exact local artifact locations may differ):
  python3 -B generate_contract.py --runtime-contract <healthy-R84-contract> \
    --baseline-reviews <actual-R84-module-reviews> --candidate <compiled-MCA> \
    --abi <same-candidate-retained-kernel-ABI> --out <fresh-contract-directory>
  python3 -B prepare_native.py --contract <directory>/module-set.json \
    --toolchain <frozen-native-toolchain.json> --out <fresh-preparation-directory>

Runtime freeze additionally requires --freeze-reviewed-r87, an explicit
non-draft --build-id, --expected-ci-head and --expected-ci-run. The candidate
must contain successful reports/r87-status.json matching that reviewed identity.
Preparation records both reproducible AArch64 static builds and extracted native
guard tests with ASan/UBSan/Werror. Its status is native preparation only; image
assembly and device acceptance remain separate checks.
