R88 local vendor_boot assembly preparation

assemble.py creates no output until all actual R88 inputs agree: successful
exact CI head/run/attempt, local frozen R88 source/build contracts, complete
artifact lock,47 actual KOs with the three FG source snapshots, static294 ABI
against the retained healthy R84 kernel, and a frozen R88 native helper plus
reproducible preparation proof. Old R87 CI or helper inputs are rejected.

All recovered file locations are explicit CLI arguments (--help lists them):
baseline-dir, retained-vendor-boot, runtime-contract, foundation, pid1-source,
toolchain, reproduction and elf-parser. Their fixed healthy R84 image, contract,
retained kernel and ELF-parser byte pins are not configurable. workspace-root
bounds a fresh output path. The exact local r88-build-route is derived from this
script's repository, never from an old scratch-workspace alias.

The loader preserves every normal249 path/hash, modules.* metadata, TFA and
brightness/audio/Wi-Fi/CNSS behavior, plus ready/DSP order. Only the two old
synchronous readonly-owner calls become one /vendor_dlkm/r32/r88-mca-start.
45 coherent additions live under /vendor_dlkm/r32/r88-mca/. Old readonly files
remain inert. The final selected294 files are read back from actual ext4.

The original72MiB RAM vendor_dlkm copy grows explicitly to80MiB with
--vendor-payload-bytes=83886080. Outer vendor_boot remains100663296 bytes; no
physical partition resize occurs. PAYLOAD-GROWTH-REVIEW.json is the inherited
actual R84 filesystem-only double-growth proof. New assembly repeats the
resize/install twice, preserves all unrelated reachable inodes and xattrs,
checks all five original PID1 source pins and reproduces PID1 and outer image byte-identically, and preserves DTB, bootconfig,
CPIO order/metadata and AVB nonhash data. No larger fallback growth is allowed.

Add --check-inputs to verify all proof inputs without creating an image.
A completed assembly is still marked pending independent final review and
hardware testing; it is not a release-ready claim.

Before R88 CI finishes, these preparation gates are available:
  python3 -B test_assembly_guards.py --baseline-dir <actual-R84-baseline>
    --pid1-source <actual-reproduced-R84-PID1-source>
Nine tests use the real R84 loader to verify surrounding-byte preservation,
unknown/extra owner rejection, old R87 CI rejection before output, and the
explicit reviewed payload-growth constraints. The three additional source tests
reject altered PID1 C and unexpected includes while accepting the exact R84 set.

Prepared native source C/H must match the current reviewed R88 source set,
and its generated header must match the exact frozen module contract. Native
preparation and PID1 compilation bind the same verified toolchain manifest.
The R84 reproduction report must pin all three exact historical outputs; a
self-declared PASS or three booleans alone are insufficient.
