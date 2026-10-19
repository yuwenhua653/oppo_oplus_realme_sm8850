# R78 audio source delta

This package prepares two kernel modules for one compile-only CI run: `tfa98xx_dlkm` and the existing `machine_dlkm`. It does not load modules, modify a phone, install firmware, or change init/SELinux files. Full kernel compilation and hardware operation are still unverified.

The base is the exact R77 prepared tree at `01845c8dcdbc7a5c42f8037f4839e4b12e61137f`. The contract locks all inputs and 81 workspace writes: 77 new TFA files, three appended build declarations, and one replaced machine source. The TFA payload is precisely four C units, 72 headers and one Kconfig. Old standalone Makefile/Kbuild wrappers exist only under `provenance/`; DDK generates its actual Makefile from the registered sources. CI must verify the actual aquery source closure and module outputs before treating the build as valid.

The driver starts from MiCode's pinned onyx TFA source. The delta removes the obsolete `SLAB_MEM_SPREAD` flag for Linux 6.12, uses S32_LE for the documented Myron 48 kHz / three-channel primary TDM route, and supports the two declared receiver pinctrl states. Receiver state changes propagate errors; cached state records only successful selection. Missing states or GPIOs do not cause guessed writes. The control accepts only 0/1. The matching Myron container makes address 0x36 its control-owning device index 0; that is also the DT node containing the receiver states.

The MN2B0 support is a minimal backport from the fixed Goodix source: test type bits using the original chip revision, and copy its exact `0x110b65` initialization case. The table is entered only after revision/type identification; it is not an unconditional register sequence or an alias to A silicon. The local signed return-value correction also preserves timeout/error refusal. Existing calibration, interrupt masking and firmware checks remain in place.

The machine helper is compiled into the already registered `machine_dlkm`. Its `myron_tfa_links` parameter defaults to false and is read-only after module load. When explicitly enabled in a future reviewed runtime step, it resolves three enabled DT/I2C clients at 0x34, 0x35 and 0x36, derives DAI names from their real I2C adapter number, and connects both primary TDM RX and TX only after all three clients are validated. It rejects absent/duplicate/wrong clients, supports deferred probe, and keeps OF/client references balanced. No current init or module-loading change enables it. DT already provides the receiver pinctrl states; the source does not require userspace GPIO/sysfs writes.

`hardware-evidence.json` records exact reference paths/hashes and the small derived facts used here. Proprietary firmware and ODM XML bytes, raw DT images and private captures are excluded. The 2071-byte container was structurally checked beyond its CRC: all three embedded patch descriptors are self-contained dummy MN2B0 headers without external DSP payloads; all profile and bitfield references used here resolve. This is static compatibility evidence, not proof of operation on the user's phone.

To check the source package:

```sh
python3 apply.py --package-dir . --check
```

To apply it after the exact R77 preparation (all preimages are validated before the first write):

```sh
python3 apply.py --package-dir . --workspace /path/to/prepared/workspace
python3 apply.py --package-dir . --workspace /path/to/prepared/workspace --check
```

The import API is `check(package_dir)` and `apply(workspace, package_dir, verify=False)`. Module targets, predicted output paths and exact expected source lists are in `contract.json`.

R78 fix2 uses the public `GPIOF_IN` flag for the legacy integer-GPIO IRQ request
and includes its defining header explicitly. The pinned 6.12 common header does
not define `GPIOF_DIR_IN`. GPIO descriptor flags are not substituted into this
legacy request API. The regression test compiles the actual three request blocks
against declarations and flag definitions from that exact header; it does not
claim a complete kernel build or a hardware test.

The focused local control-flow verification is:

```sh
python3 test_audio.py --output /path/outside/package/TEST-RESULT.json
```

It compiles extracted production C with warnings-as-errors and undefined-behavior checks, covers machine routing/refusal/reference handling, receiver state errors, the B revision path and timeout refusal, and exercises atomic preimage validation and idempotence. It does not compile a kernel module or simulate audio hardware. Remaining gates are the real kernel compiler/modpost/ABI/CFI/provider closure, a phone/reference ODM hash match, actual chip/OTP and power/clock readiness, and subsequent combined hardware testing.
