# R75 capture source candidate

This directory is source for offline review and later packaging. It contains no images, native executables, Windows launchers, flash entry point, release manifest, or release script lock. `TEST_SHA`, `NATIVE_SHA`, and `SCRIPT_LOCK_SHA256` are deliberately empty. Both collector modes fail before resolving adb/fastboot or making a device call until the actual reviewed package is assembled. Do not push or run the shell files on a device independently.

Candidate build: `R75-READONLY-PD-DIAG-20261018-01`. Collector identity: `R75-READONLY-MCA-CAPTURE-20261018-01`. The future permitted source and rollback baseline is the verified R74 image, SHA256 `edff07856a15c1ea53bcdff4456b6c0d29e41dd49310783c39f240c7f3926a84`, 100663296 bytes. This source contains no rollback transaction. Existing frozen R74 files and its R70 restoration entry point are unchanged.

## Offline verification

From any checkout directory on a POSIX test host with Python 3, `sh`, GNU-compatible `timeout`, `head`, `readlink` and core utilities:

```sh
python /absolute/path/to/r75-capture-source/run_tests.py
```

Tests use synthetic sysfs trees, FIFOs, and a synthetic recorder clock inside temporary directories. They never call adb/fastboot, access a connected phone, request root, or use the network. All sample boot IDs and cache rows are synthetic; no original user archive, serial number, logcat, or device log is included.

## Capture contract

- The periodic script first reads the verified MCA six-GET cache and reviewed battery/USB properties. `CORE_BEGIN` / `CORE_END` are independent of the outer snapshot envelope. Each read preserves its raw value, return code, explicit truncation flag and BOOTTIME interval. The parser requires all 19 expected scalar records plus MCA, identity, boundaries, monotonic clocks and consecutive recorder rounds.
- Core record completion, valid telemetry, outer frame completion, optional evidence and stable file transfer are distinct. An outer timeout after `CORE_END` retains the available core but still yields partial overall evidence. Read errors remain errors; values are never replaced with zero. The previous R74 partial capture is not rewritten or reclassified.
- Each scalar/cache/link read has a one-second timeout with a one-second kill allowance. The recorder bounds each entire snapshot at eight seconds with a one-second kill allowance. It targets a two-second start interval, never overlaps frames, and stops at 75 rounds or 150 BOOTTIME seconds; its external supervisor remains bounded at 179 seconds. Real cadence depends on completed reads, scheduling and suspend.
- Type-C/UCSI/UDC enumeration and owner/DT metadata are read only once before and once after the normal recording, each under the existing 20-second foreground cap. Optional errors, missing end markers and truncation remain evidence gaps. Resuming a run only reads existing recorder files; it never launches a second recorder or reloads a module.
- The separate historical diagnostics cache is read after `CORE_END`. It contains exactly five ordered properties: `0x2002`, `0x2029`, `0x21013`, `0x21014`, `0x21019`. `disabled` and `waiting` are valid collection states. In-flight rows may have `error=-115`, `end_ms=0`, and zero or one wire reservation. A stopped, still-active row and a failure before any wire reservation remain representable. Accepted historical `0xffffffff` stays raw unsigned data, not a decoded PPS capability.
- Hardware GET requests and charging behavior belong to the separately reviewed kernel/native implementation. These scripts only read cached diagnostics and reviewed power-supply getters. They do not issue GET requests, write charging controls, load/restart modules or reboot the phone.

The report lists observed USB online/status and battery status changes with per-property BOOTTIME brackets. These are observations of sequential published values, not physical plug timestamps. No verified physical cable-event format is currently available. Original pre/post dmesg and logcat are retained when accessible; transport SSR/PDR events and operator wall-charger instructions do not become hardware cable events. Physical event time and response latency remain unavailable rather than inferred.

## Final assembly still required

Freeze the actual R75 image, native contracts and script lock; reconcile exact native helper status fields with that contract, including the explicitly enabled `enable_extra_diagnostics=1` parameter; then build and review Windows entry points. The currently empty pins are an intentional hard gate. The source-only candidate must not be represented as a usable flash/capture release.
