R90 parser test scope

The host executes unchanged text extracted from the actual R89/R90 C definitions:
temperature, voltage, stage parsing and stage traversal. It also executes the pinned
production MCA count/string/u32 helpers. The relevant struct/enums/row limits are
extracted from the pinned production header; the prepared kernel workspace must
match those bytes before this suite can run. Only kernel OF, allocation, numeric
conversion and probe-diagnostic interfaces are replaced by host providers.

The three 63-string, nine-column stock tables are CN ATL, CN COS and global ATL.
They retain original voltage and stage properties. Each old table is rejected by
R89 with temp_count/-EINVAL; R90 accepts it and compares every temperature,
hysteresis, current, voltage and stage value with that stock fixture. Constructed
eleven-column equivalents validate the unchanged modern format. Explicit modern
FV values remain unchanged. The original stage entries are retained for BOTH
formats: legacy tables omit the two FV columns, not the stage columns.

PROVENANCE.json identifies the previously captured stock DT artifact, source ZIP,
exact member hashes and stock module disassembly that reads terminal FV from the
last voltage row. This is compatibility evidence, not a new live-DT capture or
proof that the entire replacement driver equals the stock driver.

Failure injection visits every allocation, string read, numeric parse and stage
array read reached by each valid table, for both roles and both storage modes.
It verifies no partially parsed output is published, previous output remains
unchanged, and every newly allocated object is released exactly once. Boundary
fixtures check row limits, malformed counts, absent tables and explicit FV.
AddressSanitizer and UBSan run. LeakSanitizer is disabled because restricted /proc
in the host sandbox prevents its process inspection; the allocation inventory
independently requires zero live allocations after each scenario.

The tests do not claim target compilation or physical fast charging. Existing
runtime ownership of an earlier successfully published table is unchanged.
