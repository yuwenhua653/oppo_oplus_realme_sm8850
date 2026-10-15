# Myron FT3683 direct input test driver (R58)

This GPL-2.0-only standalone driver supplies normal Linux multitouch events
for the verified Redmi K90 Pro Max / Myron SPI touchscreen device-tree node.
It is intended to restore basic taps and dragging for adaptation testing.
Compilation and synthetic tests do not establish that hardware works; the
first phone boot, touch motion and resume test remain required.

## What it does

- Matches the existing `focal,touch-spi` node; does not edit the device tree.
- Requires the verified Myron geometry: 1200 × 2608 physical display,
  10 slots, factor 100 and ABS ranges 0–119999 / 0–260799.
- Reads application ID at A3/9F. Only 36/83 and the stock type-92 CID alias
  56/72 are accepted before any SPI register write.
- Writes only volatile register 9E = 00 (TIC, contacts computed by the IC),
  reads it back, and retries with a fixed bound. There is no firmware update,
  bootloader entry, arbitrary register-write interface or Xiaomi THP ABI.
- Reads the stock 3120-byte report from register 01. A 4-byte SPI header and
  3 dummy bytes precede data; a little-endian CRC follows. Status and CRC are
  checked before parsing. SPI retries are bounded; CS stays high at least
  150 microseconds between transactions.
- Decodes only proven protocol-v2 records: event count includes UP, offset
  `4 + 8*i`, 16-bit raw coordinates, `(raw * 100) >> 4`. It does not inspect
  unannounced records, accept duplicate slots, or report a partly valid
  frame. Active coordinates must fit ABS bounds. UP coordinates are unused.
- Publishes `FocalTech Myron Touchscreen` through the Linux input subsystem.
  Absent slots are released at frame sync; faults and suspend release all
  active contacts. The driver logs readiness and the first valid frame,
  but never logs contact coordinates or raw frames.

## Board integration and lifecycle

The module is `focaltech_myron.ko` and the SPI driver name is
`focaltech_myron`. It needs the matching kernel's SPI controller driver
(`spi_msm_geni`), GPIO, regulators, pinctrl and input support. It does not
depend on `xiaomi_touch` or private display symbols.

`devm_gpiod_get(..., "focaltech,reset", ...)` resolves the stock singular
property `focaltech,reset-gpio`. GPIO66 is driven by the raw API: physical
low, 2 ms wait, AVDD enable, IOVDD enable, about 2 ms wait, physical high,
100 ms wait. Normal ID reads then get up to five attempts separated by
200 ms. No boot-ID fallback is used. Supply names are `avdd` and `iovdd`,
not the unmatched descriptive `avdd_focal`/`iovdd_focal` strings. The
fixed AVDD and L4I 1.8 V DT constraints are retained; no voltage is guessed.
On final teardown, reset is asserted low and IOVDD is disabled before AVDD.

The active child pin state `pmx_ts_active` is selected before requesting
reset. The SPI controller owns its separate SPI48–51 state; this child has
no separate CS pinctrl state. GPIO158's DT interrupt is level-low and is
requested as level-low with a threaded, oneshot handler. The vendor
`focaltech,irq-gpio` value is not misinterpreted as normal GPIO flags.

A transport or malformed-frame fault releases contacts and masks IRQ.
After 250 ms, recovery reads the strict ID, restores/verifies TIC and drains
a full report. Persistent transport failure retries at one-second intervals.
A successful drain reenables IRQ, even if the drained packet has no valid
touch records; that packet is not emitted. Repeated malformed packets
therefore cannot cause an unrestricted level-IRQ storm. Recovery does not
reset the controller, cycle rails, or download firmware.

System suspend masks IRQ and releases contacts but deliberately retains
power and TIC mode. Resume reselects active pins and revalidates ID/TIC;
failure is returned and delayed recovery is scheduled with IRQ still masked.
No display blanking hook, gesture wake, FOD, secure/trusted touch, Xiaomi
edge/game tuning, raw-frame service or production power optimization is
implemented. Keeping power during suspend may increase idle consumption.

## Sources and evidence

The SPI and touch protocol implementation was informed by these GPL sources:

- [MeowArch-open/MeowArchMobile_sm8650AB_Touch](https://github.com/MeowArch-open/MeowArchMobile_sm8650AB_Touch/blob/cb907533e92daa59841d9047b11e186930279e2b/source/kernel/drivers/input/touchscreen/focaltech-spi-ts.c),
  commit `cb907533e92daa59841d9047b11e186930279e2b`.
- [MiCode/vendor_xiaomi_proprietary_touch-driver](https://github.com/MiCode/vendor_xiaomi_proprietary_touch-driver/tree/c286ab85f4982c9b5967e18405f4e2da0332ce4d/q200/focaltech_3383),
  commit `c286ab85f4982c9b5967e18405f4e2da0332ce4d`, notably
  `focaltech_spi.c` and protocol-v2 parsing in `focaltech_core.c`.

The Meow source was not used unchanged: this implementation corrects its
permissive ID gate, 84-byte report read, sentinel scan, coordinate scale,
generic GPIO assumptions, IRQ polarity and PM error handling for Myron.

Static comparison against the publicly published Myron
`focaltech_touch_3683.ko` corroborated the normal app ID/CID, full report
length, report fields, power sequencing and TIC switch. Reference repository
`lolipuru/device_xiaomi_myron-kernel`, commit
`71ccf071a60c978883c1ed14d8b07889660be87c`, file
`vendor_dlkm/focaltech_touch_3683.ko`, SHA256
`81dfb5eabe486e9384c15883d49844204072eeb50e5f63ef83ac329b84a608b5`.
The reference ELF and its raw disassembly are not part of this source
package and must not be loaded into the current kernel.

The current-ROM DT report is `r58-touch-dt/touch-dt-report.json`, SHA256
`9ecba7e20bd0e0c60c693909d1e42ffe3ba658813b6714384f6f0315a7bf8b80`.
The stock protocol findings are recorded separately in
`r58-touch-alternatives/stock-protocol-review.json`.

Kernel API declarations and GPIO suffix resolution were checked against
upstream Linux v6.12; exact references are in
`evidence/kernel-api-references.json`. An attempted fetch of the pinned ACK
commit was unavailable through the source mirror, so the authoritative
targeted build and final exported-symbol/CRC audit remain necessary.

## Tests and build

Run `sh tests/run.sh` with GCC. The portable parser tests cover subpixel
precision, exact event counts, UP-only packets, ghost tail records, ten
slots, duplicates, invalid flags, bounds, truncated frames, CRC convention,
atomic rejection and 20,000 deterministic malformed frames. ASan and UBSan
are enabled. LeakSanitizer is disabled because this host's ptrace sandbox
blocks its process inspection; the parser allocates no heap memory.

`Kbuild` supports a prepared external-module kernel tree. The release
artifact must instead be built by the pinned Myron targeted Kleaf route,
against the existing 6.12.81 image's source/config and symbol contract.
No CRC rewriting, forced loading or mismatched old binary is acceptable.
