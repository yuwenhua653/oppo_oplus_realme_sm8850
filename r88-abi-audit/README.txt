R88 inactive artifact review preparation

These read-only auditors do not run CI, build an image or contact a device.
Every R88 CI head/run/attempt, frozen source/build SHA and downloaded artifact
ZIP SHA is a required CLI argument. No real R88 artifact has been qualified
while preparing these scripts.

audit_identity.py verifies successful reports/r88-status.json, the complete
artifact lock and both original ZIPs, exact R88 route inventory, three FG
writes (strategy C, private header, SOC C), ten unchanged R87 guards including
charger_partition.c, real47 action chains and actual disabled IC firmware
programming configuration. R88 must extend frozen R87 preparation ancestry
b25d73a0dc1f606e51c21214b0beafaa5dae4496. CP, quickchg, full BQ, USB, GLINK,
subpmic and the persistent-storage gate remain exact read-only guards.

Diagnostic ZIP scope follows the workflow: top-level r88-*.json/log/txt and
r88-host/**. Parent R85/R86/R87 nested host-report copies are still completely
checked against the validation artifact lock and ZIP; they are not required
by the diagnostic-upload globs. Optional original copies must match if present.

Run audit_closure.py --help for all required identity and location flags.
The baseline-dir must contain the actual healthy R84 runtime-contract.json,
both extracted dlkm partitions and their pinned runtime files. reference-dir
is the retained R67 review root (runtime-reference/, output-review/, gauge-review/).
elf-parser and retained-vendor-boot are explicit paths; their fixed reviewed
hashes are mandatory. The newly built CI Image is never a runtime replacement.

Closure reparses the actual retained Image exports and unsigned policies, all251
baseline KOs and real47 new KOs. Normal249 has247 vendor and2 system modules;
the two old readonly owners are omitted, while byte-identical hwid/miev are
reused. The equivalent static set is retained247 plus coherent47 =294. Strong
imports, CRCs, namespaces, license/unsigned rules, duplicate exports and both
dependency DAGs must pass. This is static ELF compatibility, not a semantic,
CFI-callsite, hardware binding, authentication or fast-charge qualification.

Outputs: ARTIFACT-IDENTITY.json, INACTIVE-FULL-MCA-CLOSURE.json,
BASELINE-ELF-REVIEWS.json, FULL-MCA-ELF-REVIEWS.json, FULL-MCA-BINDINGS.json,
and DOCUMENTATION-ONLY-MODULE-ORDER-294.json. Native freezing independently
requires the actual successful R88 identity and these exact bytes.

test_parser_fixture.py exercises the generic Graph parser against the known
historical R87 aquery and47 action reports. Its report explicitly states that
no R88 artifact is qualified; it never calls either real artifact auditor.
