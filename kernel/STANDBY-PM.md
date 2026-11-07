# Myron SPI system-suspend correction

## Evidence and scope

The November 7 standby report was captured on the older
`6.12.81-android16-6-g6af5fb53d676-4k` kernel. It was not a runtime test of the
native Kbuild branch. The native branch has the same relevant controller and
direct FocalTech PM behavior, so this correction is being developed there.

The report identifies the FocalTech touchscreen under `1a80000.spi`, and records
3,473 `Device 1a80000.spi failed to suspend: error -16` wakeup entries. Suspend
statistics show 2,271 successes and 3,915 failures out of 6,186 attempts. These
are cumulative since boot, not a measured overnight delta. Repeated kernel
messages say `Client managed runtime PM is active`.

Battery statistics cover about 14 h 18 min, with only about 2 min 29 s screen-on
and 1,906 mAh reported screen-off discharge. The reported huge total suspend
duration is inconsistent and must not be used as a valid sleep-time measurement.
These observations identify a real suspend blocker; they do not prove that it
accounts for all standby discharge or that every other wakeup is abnormal.

## Change

The touchscreen stops its IRQ and recovery work during system suspend. The
controller, however, uses 250 ms delayed autosuspend, while its LA-VM system
callback rejects an active runtime state. A still-pending autosuspend can be
blocked by DPM preparation. This timing mechanism is inferred from the source
and observed error, not from an instrumented timing trace.

Only the Myron touchscreen controller opts into system-managed suspend. The
driver drains the SPI queue, checks for outstanding transfers/client votes,
and pairs `pm_runtime_force_suspend()` with `pm_runtime_force_resume()`.
Existing VM ownership is retained. Failure restarts the queue; DMA/resource
suspend errors retain their error and restore IRQ/DMA/resources as applicable.
The DT assembly checks all eight merged variants, rejects an absent/misplaced
opt-in, and rejects shared/LE ownership combinations.

Host tests exercise the actual C PM functions with mocked APIs, including
queue, busy-client, DMA, resource, ICC and resume failures. CI separately builds
the complete kernel, modules and DT with the standard Evolution kernel rules.
Neither check measures hardware power or validates touch after wake.

## Integration and device validation

Update the native device branch together with `kernel/xiaomi/sm8850` and
`kernel/xiaomi/sm8850-devicetrees`; keep the matched module source project.
Use the normal ROM build described in README-CN.md. This is not a patch for the
old R123 prepare/workspace adapter. Do not mix the new driver/DT with old module
partitions or assume that a CI raw Image is a flashable boot image.

After installing a complete matched build through the established recovery
procedure, first verify the running kernel and new controller DT property.
Check repeated screen-off/wake cycles, touch response, audio and camera before
an overnight comparison. No flashing or automatic reboot is part of this change.

For standby testing, record beginning/end battery charge counter, elapsed time,
screen state, suspend successes/failures and wakeup reasons during the same
unplugged interval. Compare the *increase* of the `1a80000.spi` failure counter,
not its total since boot. A zero increase plus successful touch recovery is the
first acceptance criterion. Then compare overnight drain with comparable SIM,
signal and Wi-Fi settings. If drain persists, investigate the remaining wakeup
and power data instead of disabling unrelated drivers without evidence.

Status: source correction and host validation only; device results pending.
