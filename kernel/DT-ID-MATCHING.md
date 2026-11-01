# Reviewed CanoeP thermal component matching

Device: Redmi K90PM / myron. This is a build-time component compatibility rule,
not a change to bootloader selection IDs or proof of the shipping ABL binary.

## Primary implementation evidence

Qualcomm ABL, pinned revision `9f80772a9bb77b06837142b0d2fc9eaa3641b61b`:

- [LocateDeviceTree.h](https://github.com/CodeLinaro-mirror/kernel-platform-2-0-os_abl_tianocore_edk2/blob/9f80772a9bb77b06837142b0d2fc9eaa3641b61b/QcomModulePkg/Include/Library/LocateDeviceTree.h)
  defines `SOC_MASK=0xffff`, `FOUNDRY_ID_MASK=0x00ff0000`,
  `PLATFORM_FOUNDRY_SHIFT=16`, and `OEM_ID_MASK=0xff000000`.
- [LocateDeviceTree.c](https://github.com/CodeLinaro-mirror/kernel-platform-2-0-os_abl_tianocore_edk2/blob/9f80772a9bb77b06837142b0d2fc9eaa3641b61b/QcomModulePkg/Library/BootLib/LocateDeviceTree.c)
  `GetPlatformMatchDtb()` accepts an exact foundry or a zero/default foundry;
  another nonzero foundry is rejected. `ReadDtbFindMatch()` uses that routine,
  including the DTBO selection route in `GetBoardDtb()`.

## Deliberately restricted policy

Only these two source-to-component ID pairs are enabled in `dt-profile.json`:

| Base MSM-ID / revision | Component MSM-ID / revision |
| --- | --- |
| `0x1010295 / 0x10000` | `0x1000295 / 0x10000` |
| `0x1010295 / 0x20000` | `0x1000295 / 0x20000` |

The difference is foundry 1 versus default 0. Low chip ID, high OEM bits and
revision remain identical. The assembler first accepts an exact pair; only
then may it use one of these explicitly reviewed pairs. It does not implement
ABL's general revision fallback, a global ID mask, or arbitrary foundry aliases.
The helper rejects additional/unreviewed mappings even if added to the profile.

With the pinned 32 inputs, 28 component uses need this rule. Camera, display,
and the Myron camera overlay already advertise the exact thermal IDs.
All eight bases retain their original identity and order; board overlay metadata
is restored from the original Myron board overlay. Hardware provider, GPU
revision, audio register and haptics-path checks apply to both thermal variants
just as they apply to the other six.

## Scope of evidence

The public OEM thermal bases also use `0x1010295`; rewriting it as a typo is
unjustified. Those OEM bases contain camera/display components but omit several
other techpacks present in the other six bases. The source assembly deliberately
adds the reviewed components and therefore is not byte-equivalent to OEM DT.
The public ABL implementation supports the encoding and fallback interpretation;
it does not establish which DT is selected by this device's exact ABL binary.
The available R114 capture did not record the live DT IDs.

Keep `MYRON_DT_MODE=oem` as the default until a matching source-DT test package
has passed real-device checks. Static success is necessary, not hardware proof.
