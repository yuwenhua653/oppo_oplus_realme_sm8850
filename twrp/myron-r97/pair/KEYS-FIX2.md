# R97 fix2: recovery PON keys

The fix1 recovery boots and its battery monitor receives real Health values.
Its input inventory lacks KEY_POWER and KEY_VOLUMEDOWN: the only key device
is gpio-keys with KEY_VOLUMEUP. After the normal screen timeout, there is
therefore no power-key event to trigger the existing GUI screen-on path.

This follow-up adds the three modules already loaded by the stable R96
Android runtime, in the same dependency order:

1. reboot-mode.ko (reboot_mode)
2. qcom-pon.ko (qcom_pon; depends on reboot_mode)
3. pm8941-pwrkey.ko (pm8941_pwrkey)

The existing REC UI phase loads them before starting the GUI. No GUI binary,
init RC, loader script, PID1, kernel, DTB/DTBO, Android payload, or MCA module
is changed. The paired R97 vendor_boot remains byte-identical. All three
existing REC files checked by PID1 retain their original bytes and pins.

The local assembler requires exact fix1 Recovery, stable R96 vendor_boot,
and paired R97 vendor_boot hashes. It extracts the modules from the pinned
private R96 payload using read-only debugfs, validates ELF identities and
dependency order, and updates only these four controls:

- r97-runtime/module-plan.json
- r97-runtime/allowed-live.txt
- r97-runtime/modules.sha256
- r97-runtime/ui.list

It adds only the three KO records. All retained unrelated CPIO records are
compared byte-for-byte, including the fix1 empty DLKM root layout. Output
is assembled twice, checked independently, and its internal AVB hash verified.
The original 126-module verifier remains strict; it is used on the fix1 input,
not weakened to accept arbitrary follow-up inventories.

## Reproduce locally

Run from a checkout containing this pair directory. Private images are local
inputs and must not be committed to this source repository.

```bash
python3 twrp/myron-r97/pair/fix_recovery_keys.py \
  --source /private/recovery_r97_fix1.img \
  --vendor /private/vendor_boot_r96.img \
  --paired-vendor /private/vendor_boot_r97.img \
  --pair-tools twrp/myron-r97/pair \
  --out /private/fix2/recovery_r97_fix2.img
```

Use a fresh output directory; the AVB verifier uses the recovery.img alias
created beside the output. The existing full CI candidate is not flashable
without the earlier local runtime injection and pairing steps. This fix is
a local follow-up to the exact released fix1 and does not trigger full CI.

## Validation and limits

The final module inventory is 129 selected modules, with 22 newly loaded UI
modules, the same 142 first-stage modules, and the same 57 hardware modules.
Tests cover the actual input and output, exact allowed changes, dependency
ordering, missing dependencies, malformed ELF, module tampering, changes to
PID1-pinned files, unexpected files, and module ownership/mode.

Expected Recovery SHA256:
3781fbdef579681c15127a4a7e40e1ee0fd446387929c0dfaace24c0481446f1

The existing GUI handles KEY_POWER and periodically discovers newly added
input devices. Normal Android already uses these same modules. These facts
support the fix but do not replace device testing: verify power-key screen
off/on, slide-to-unlock, battery visibility, and Android behavior on hardware.

The existing battery initialization takes approximately 105 seconds in the
observed REC boot; fix2 does not claim to reduce that delay. A device test
must distinguish the initial loading interval from the settled state.
