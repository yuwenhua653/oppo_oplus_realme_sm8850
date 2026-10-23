R87 audit source preparation
===========================

These are local read-only artifact auditors. Neither script starts CI, changes
the candidate/baseline, builds an image, loads a module or authorizes flashing.
No real R87 audit was executed while preparing these scripts.

Exact submitted R87 identity:
  head: ae4bf5b38ae1771e0f440b8b26b02cd66a008231
  run: 39873532978
  attempt: 1
  source SHA256: 4a4be491f873447a5249f175b3f2e1254b529d7abf4258400c06bdc5d618cad7
  build SHA256: ec8e557f2486a97a6fd2577b82e10727a2b9a8e73c7ea0efc62bb580b36eecbe

After that exact run succeeds, independently download and record both artifact
ZIP pins. Expected GitHub artifact names are:
  myron-r87-mca-validation-only-output-39873532978-1
  myron-r87-fastcharge-reports-39873532978-1

Example local naming used by the command below:
  r87-success/r87-validation-only.zip
  r87-success/r87-reports.zip
  r87-success/r87-validation-only/  (extracted validation ZIP root)

Replace the two ZIP_SHA256 placeholders with the recorded download hashes.
They are intentionally not guessed or copied from any previous run. Execute
from /workspace/scratch/f1784ad54992:

python3 -B r87-success/abi-audit/audit_closure.py \
  --candidate r87-success/r87-validation-only \
  --ci-head ae4bf5b38ae1771e0f440b8b26b02cd66a008231 \
  --ci-run 39873532978 --ci-attempt 1 \
  --source-sha256 4a4be491f873447a5249f175b3f2e1254b529d7abf4258400c06bdc5d618cad7 \
  --build-sha256 ec8e557f2486a97a6fd2577b82e10727a2b9a8e73c7ea0efc62bb580b36eecbe \
  --validation-zip r87-success/r87-validation-only.zip \
  --validation-zip-sha256 VALIDATION_ZIP_SHA256 \
  --reports-zip r87-success/r87-reports.zip \
  --reports-zip-sha256 REPORTS_ZIP_SHA256 \
  --out r87-success/abi-audit

For identity alone, use audit_identity.py with exactly the same arguments.
Closure always reruns identity itself; it does not trust a previous PASS JSON.
Reruns require the actual attempt number and newly reviewed artifact ZIP pins.

Identity output: ARTIFACT-IDENTITY.json
  - Exact successful CI head/run/attempt and both contract pins.
  - Complete artifact-lock inventory, frozen route inventory, every source
    write and read-only guard snapshot (2 writes + 9 guards for this route).
  - Both ZIP pins; validation ZIP members compared byte-for-byte to extracted
    files; all copied reports compared with their original reports ZIP members.
  - Reconstructed source->KernelModule->staging->copied KO chains for all47,
    including CP, quickchg, BQ C/header and FG C/actual enum header.
  - Actual emitted config before/after compilation, shared config tree and
    target-owned setup script consumed by every actual compiler.
  - Firmware programming must be disabled. A frozen .bzl source snapshot is
    distinct from the emitted .config; no nonexistent DdkConfig execution-input
    edge is invented for Bazel's Starlark analysis inputs.
  - Unchanged action sources outside writes/guards retain CI-recorded pins, but
    have no independent compiled-source snapshots; this limit is explicit.

Closure outputs, compatible with native generator and assembler:
  ARTIFACT-IDENTITY.json
  INACTIVE-FULL-MCA-CLOSURE.json
  BASELINE-ELF-REVIEWS.json
  FULL-MCA-ELF-REVIEWS.json
  FULL-MCA-BINDINGS.json
  DOCUMENTATION-ONLY-MODULE-ORDER-294.json

The closure reparses the actual healthy R84 Image, all251 baseline ELF files
and actual47 new KOs. Normal249 includes247 vendor_dlkm and2 system_dlkm files;
the two readonly owners add2 vendor_dlkm files, making251 across both partitions.
Both fixed partition prefixes are accepted, with the same safe relative-path
and byte-pin checks. It checks true Image exports/unsigned-policy tables,
strong imports, CRCs, namespace/GPL/unsigned rules, duplicate exports, declared
dependencies and both full294/MCA47 dependency DAGs. Qualified ADC/VADC remain.
The static set is247+47=294; actual boot may equivalently retain normal249
including unchanged hwid/miev, skip readonly2 and add45. The documented DAG is
not a probe ordering prescription or a loader. Fixed healthy baseline hashes
are embedded; optional path flags only relocate the same exact files.

Source/ABI review boundary:
  These scripts establish bytes, action/config provenance and static ELF ABI.
  They do not assert semantic correctness, CFI callsite typing, successful DT
  probes, owner handover, battery authentication, thermal/power behavior,
  real fast charging or flash readiness. Existing independent source/native/
  image reviews and subsequent hardware evidence remain separate gates.

Preparation checks performed:
  - Python AST/import and both --help interfaces passed.
  - The generic Graph parser was compared with all47 existing real R86 action
    reports, including47 target-owned config setup checks: PASS.
  - This was a parser regression fixture only, not an R87 artifact audit;
    neither R87 audit function was run against R86 inputs and no PASS R87
    report was generated.
  - Actual healthy R84 baseline-only check: normal249 partition shape247+2,
    readonly2 addition, all251 source contract byte pins and actual ELF parser
    import/name/byte identity passed. This was not an R87 artifact audit.
