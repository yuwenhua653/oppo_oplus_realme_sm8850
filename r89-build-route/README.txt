R89 extends the exact R88 compiled charging sources in two files only:
BQ battery-cell metadata recovery and read-only quickchg probe diagnostics.

The R88 preparation/build engine is SHA-256 pinned and is not edited. It runs
the existing parent production suites before the R89 boundary. R89 applies only
after the R88 full postimage check, executes its own production tests against
the prepared source, and then uses the unchanged 47-module target/action/config
and build/collection code. Whole-source verification overlays only the two
declared R89 hashes; all inherited destinations remain checked.

R88-prefixed runner logs are preserved under reports/inherited-engine. They are
engine filenames, not a claim that R89 BQ/quickchg sources are unchanged. Final
R89 contracts, source snapshots, artifact locks and status bind the R89 hashes.
The original R88 artifact-finalizer is deliberately not used because its source
guards require unchanged BQ and quickchg files.

--check-overlay validates this round and the two parent contract hashes without
replaying all earlier repository imports. --check-inputs additionally runs the
complete frozen parent chain; CI requires this mode. Local snapshot/host tests
and a successful kernel compilation are separate evidence.

Outputs are inactive compile evidence. Hardware behavior, runtime module ABI,
vendor_boot assembly and physical fast-charge success still require independent
verification. No temperature/current/voltage, authentication, storage-write or
battery-parameter-matching protection is removed.
