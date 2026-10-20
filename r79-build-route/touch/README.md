# R79 Xiaomi touch extension review

The current runtime extension is **not connected**. The R58 `focaltech_myron`
driver still provides working direct TIC input. This directory contains reviewed
Xiaomi framework prerequisites, not a completed THP driver or a flashable fix.

## Findings

The R78 log records 9 THP0 `/dev/xiaomi-touch` open failures and 23 AIDL
touch-node open failures. It also records a validated protocol-v2 FTS input frame
and successful suspend/resume. The open-error log omits errno, so it alone does
not distinguish an absent node from a permission denial.

The actual retained FTS ELF has no dependency on `xiaomi_touch` and no imports
for backend registration. The selected runtime loader does not load
`xiaomi_touch.ko`. The restored R13 source does register a real misc device
named `xiaomi-touch`, and the prior handset DT capture has compatible
`xiaomi-touch`. Loading the framework alone cannot supply a controller backend:
`SELECT_TOUCH_ID` requires a successfully registered panel.

The preserved v3 ABI uses magic `T`; commands 0 through 6 are common data,
hardware parameters, mmap-area selection, touch-ID selection, frame index,
raw index and report-point update. The actual header is retained unchanged in
`fixtures/xiaomi_touch_type_common.h`. Its hardware parameters advertise frame
and raw page counts, buffer counts and the THP configuration filename.

The restored R58 stock-protocol review confirms that the original Myron
FT3683 publishes raw-enable and HTC mode callbacks through
`register_touch_panel()`. Raw mode writes register `9e=41`; the current tested
driver uses `9e=00` and decodes TIC contacts. Registering a panel with empty
buffers would advertise an unverified partial protocol. The checkpoint does
not contain the Myron HAL executable, configuration or an error-handling trace
proving that it tolerates that partial protocol. No such panel is published by
this patch, and no raw-mode register writes are added.

## Implemented prerequisites

`xiaomi-touch-foundation.patch` changes five real framework sources:

- Propagate probe initialization failures and unwind completed stages; an
  unsuccessful misc registration can no longer leave a falsely successful bind.
- Publish the backing pointer before `misc_register()` exposes `open()`;
  publish the misc device only after sysfs, notifier, netlink and evdev/timeline
  state are ready. Reject an unavailable backing object.
- Handle `ERR_PTR` from class/device creation and clean up failed sysfs or input
  handler registration. Initialize notifier work before registering it and
  unregister the notifier before cancelling its work.
- Validate userspace common-data lengths before dispatch and queue copying;
  return `EOPNOTSUPP` for a missing hardware mode callback and propagate its
  actual errors. Clear unused queue bytes.
- Bound each mmap request by its actual allocation, reject overflowing offsets
  and invalid areas, preserve requested mapping protection, and propagate
  remap/copy errors.

This is intentionally not a claim of a complete framework lifetime audit.
Mapped-buffer lifetime across unregister/timeline release and backend/client
concurrency still require review before enabling the extension.

## Reproduction and integration

Run from this directory:

```sh
python3 prepare_patch.py
python3 test_touch.py
python3 test_apply.py
```

The generator uses the bundled exact preimages. The seven ASan/UBSan host
groups compile actual modified function bodies with fault-injection stubs and
the real unchanged common ABI header. Every new implementation passes; each
old implementation fails its regression. These are host checks, not a full
kernel build, ABI validation or a hardware result.

Apply only to a disposable full workspace after the exact R13 source overlay
and retained R78 preparation:

```sh
python3 apply_touch_foundation.py --workspace /absolute/build/workspace
python3 apply_touch_foundation.py --workspace /absolute/build/workspace --check
```

The application checks all five preimage/postimage hashes before writing,
rejects symlinks, and is idempotent. It does not modify config, metadata, loader,
module selection or FTS. The source lock remains `runtime_enable: false`.

The existing registry-derived DDK label is:

```text
//vendor/qcom/sm8850:canoe_perf/drivers/input/touchscreen/xiaomi/xiaomi_touch
```

Use the retained runner's exact Bazel options and output base. The registry
already contains `CONFIG_TOUCHSCREEN_XIAOMI_TOUCHFEATURE`, the eight C sources,
two headers, `TOUCH_THP_SUPPORT`/`TOUCH_FOD_SUPPORT` compile flags and dependencies
on `panel_event_notifier` and `miev`. Do not replace that registry with an older
copy. A future build must bind these source postimages to its actual aquery
compile action, collect the new `xiaomi_touch.ko` and module symvers, and perform
installed-kernel import/CRC/namespace/GPL/CFI review. This directory supplies no
new KO and authorizes no runtime selection.

## Remaining implementation inputs

Full THP work needs either the matching Myron FT3683 backend source or a
verified reconstruction of its frame/raw/command contracts, plus the current
HAL's negotiation/error behavior. The known original source path is
`touchfeature_v2/touch_driver/p11u/focaltech_3683/`; the configuration reference
is `/odm/firmware/myron_fts_thp_config.ini`. The restored R58 stock review gives
limited static callback/protocol evidence but not a complete raw pipeline.

No new handset capture or root access is requested by this source work.
