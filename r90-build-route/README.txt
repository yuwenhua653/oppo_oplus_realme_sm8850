Problem and repair
------------------
R89 runtime reached the ATL cell selection but quickchg probe stopped at
stage=temp_count with dependency_errno=-EINVAL. The selected stock table has
seven rows of nine strings, while the source parser required eleven strings
per row. Consequently the quickchg device never bound even though the module
itself loaded and the preceding charger/FG devices were already bound.

The nine-column layout omits the explicit normal/FFC float-voltage columns;
it still contains both voltage-table names and both stage selectors. R90 maps
its columns 5/6 to the existing eleven-column positions 7/8 (voltage tables),
and columns 7/8 to positions 9/10 (stages). It derives the omitted float
voltages from the selected normal/FFC voltage tables' final stages, matching
the archived stock-module regulation's terminal-voltage lookup documented in
tests/ provenance.
No stage selector is discarded. Existing eleven-column tables retain their
explicit float-voltage values. Unsupported or malformed table formats remain
errors; this patch does not replace battery matching or raise charging limits.
The fixtures and source-level negative controls document the exact supported
schemas and verify the original R89 failure on the stock nine-column tables.

R90 extends the exact R89 charging sources in one production file only:
quickchg temperature-table schema parsing. The fixture/provenance and production
parser tests live in tests/. Battery identity recovery, FG regional policy
handling, authentication, device-tree battery selection, storage-write guards
and voltage/current/temperature protections are retained.

Build route
-----------
The SHA-pinned R88 build engine still owns source preparation, the R85-R88
production tests, aquery/action checks, effective configuration checks, target
compilation and collection of the unchanged 47-module MCA closure. At its one
prebuild verification boundary, R90 first verifies exact R88 postimages, applies
exact R89, runs the R89 production tests, applies the one R90 patch and runs the
R90 production tests. Only then may the original engine analyze or compile.
There is no second kernel build and no nested monkeypatch of the R89 runner.

Every inherited prepared source is verified against its exact final hash before
and after compilation; only declared R89 and R90 source hashes are overlaid.
The postbuild R88 apply(..., verify=True) call dispatches to this full final
source check. Final artifact snapshots, action source pins, configuration and
contracts bind the actual R90 production bytes. R88-prefixed engine logs remain
explicitly labelled inherited-engine evidence, not unchanged-R88-source claims.
R89 source tests are retained under r90-parent-r89-host in both reports and the
validation artifact. The workflow uploads the complete r90 report subtree.

Local qualification
-------------------
python3 -B r90-build-route/freeze_inputs.py
python3 -B r90-build-route/build_temp_schema.py --repo-root . --check-inputs
python3 -B r90-build-route/test_build_guards.py
The freeze command reconstructs only locked source bytes locally; it does not
compile a kernel. The production tests are invoked against the actual prepared
source by the build route. Host tests and target compilation are separate proof.

Output remains inactive compile evidence. Runtime module ABI, retained-kernel
assembly and physical charging behavior require subsequent verification. No
flashable image or successful hardware fast charge is asserted by this build.
