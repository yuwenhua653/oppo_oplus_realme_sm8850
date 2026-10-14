R55 guarded late ADSP/CDSP start

Purpose
The separately compiled PAS change restores the stock Canoe ADSP/CDSP auto_boot
settings. Exact firmware-loader source and R54 timing show that initial auto-boot
can run before stock init enables sysfs fallback, ueventd starts, and the firmware
mounts become available. That early failure has no automatic retry. This is a
source/timing prediction for R55, not a claim that R55 was already tested.

The loader addition attempts a later start through standard remoteproc state
sysfs, once per offline ADSP/CDSP, after the original module checks and ready
property. It uses the existing asynchronous vendor.modprobe service. GKI loading,
native bootstrap, init RC, module lists/order, and all 213 Live checks are unchanged.

Files and reproduction
- late-dsp-start.sh: exact inserted shell snippet.
- load-modules.sh: generated full loader to install as /r32/load-modules.sh in
  vendor_dlkm, mode 0100755, owner root:root, SELinux label
  u:object_r:vendor_modinstall-sh_exec:s0 (same as the original loader).
- loader.patch: review diff against the exact R54 baseline.
- generate-loader.py: fail-closed reproduction with pinned baseline, helper and
  result hashes. Run from the workspace root:
  python3 r55-source/late-dsp-start/generate-loader.py \
    --baseline r54-build/generated/load-modules.sh \
    --output r55-source/late-dsp-start/load-modules.sh
- source-evidence.json: source, runtime timing and scope evidence.
- test-readiness.py / readiness-tests.json: focused host simulations.
- Independent review is supplied separately by the reviewer; packaging must bind
  its PASS result to the exact baseline and candidate hashes.

Guards
Each worker requires actual force_sysfs_fallback=1, running ueventd,
ro.cold_boot_done=true, and nonempty readable target MDT plus DTB MDT in existing
stock firmware search directories. The helper does not modify those conditions.
It discovers a unique exact remoteproc name and validates the canonical platform
and OF paths, compatible, current firmware name, and writable state. Numeric
remoteproc indices are discovered rather than assumed. SOCCP and modem are never
targeted. Running targets are skipped; every state other than offline is refused.
Identity is checked again and the timed child re-reads state immediately before
its single start write. There is no stop, detach, SSR, retry, or restart loop.

Timing and diagnostics
The two targets run in parallel. Each has a 15-iteration readiness wait and a
20-second timed write with a 2-second kill grace. The supervising shell checks
for at most 45 one-second iterations, then stops waiting and signals pending
direct workers without a blocking wait. Those are userspace waiting budgets;
command scheduling overhead is additional and an uninterruptible kernel firmware
write can remain pending after signals. This is not a hard kernel cancellation
guarantee. The pre-existing selected-module ready property has already been set,
and helper failure cannot revoke or manufacture that module gate.

R55_DSP messages inherit vendor.modprobe stdio_to_kmsg. Per-target markers include
WAIT_READY, NOT_READY, IDENTITY_REFUSED, ALREADY_RUNNING, STATE_SKIPPED,
START_ONCE, RUNNING, START_UNCONFIRMED and SUPERVISOR_TIMEOUT. RUNNING requires a
post-write state observation, even when the write itself fails. A zero writer
exit alone is insufficient. END reports only that the supervisor stopped waiting;
it does not claim DSP, QMI, audio, sensors, or Android boot success.

Known limits and validation
Kernel state_store calls rproc_boot without an atomic offline comparison. Another
client can start between our state read and write, adding a power reference even
though the kernel mutex prevents another hardware boot. The helper narrows this
race and makes one attempt; it never compensates with a stop.
Host tests use dash, redirected paths and simulated state changes. They check
control flow, not target toybox/mksh, SELinux permissions, firmware acceptance,
ADSP/CDSP startup, or hardware boot. The existing loader's runtime choose_timeout
probe is preserved and the helper repeats the no-op timeout check. Actual R55
capture must inspect the per-target markers and subsequent DSP/QMI/audio progress.
