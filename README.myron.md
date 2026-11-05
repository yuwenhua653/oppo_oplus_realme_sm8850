# Myron native Kbuild migration

This branch is a work in progress. It currently builds the device's DT inputs
through Linux Kbuild. It is **not yet a bootable native kernel integration**;
do not replace the working ROM kernel adapter with this branch yet.

## Source layout

Use `android/myron-native/manifest.xml` as a repo local manifest. The sources
are ordinary repo projects, not a workspace downloaded by a kernel build rule:

* `kernel/xiaomi/sm8850`: ACK 6.12.81, native DT selection and binding headers.
* `kernel/xiaomi/sm8850-modules`: the pinned, previously tested module sources.
* `kernel/xiaomi/sm8850-devicetrees`: DTS sources with native Kbuild selection.

The manifest can coexist with the previous adapter while this port is under
development. It does not select a ROM product or alter any BoardConfig.

## DT compilation

From the ROM source root, with the normal Clang/LLVM and host build tools on
PATH:

```sh
make -C kernel/xiaomi/sm8850 O="$PWD/out-myron-native-dt" ARCH=arm64 LLVM=1 gki_defconfig
kernel/xiaomi/sm8850/scripts/kconfig/merge_config.sh -m \
    -O out-myron-native-dt out-myron-native-dt/.config \
    kernel/xiaomi/sm8850/arch/arm64/configs/vendor/myron-dt.config
make -C kernel/xiaomi/sm8850 O="$PWD/out-myron-native-dt" ARCH=arm64 LLVM=1 olddefconfig
make -C kernel/xiaomi/sm8850 O="$PWD/out-myron-native-dt" ARCH=arm64 LLVM=1 -j2 dtbs
```

The fragment above selects DTs only; it is deliberately not named or presented
as a complete device kernel configuration. Build outputs go under `O=`.
No MYRON_* environment variables, source-tree write allowlist, source sync
script, or Python kernel-build wrapper is used by this DT build.

## Verified scope

All 32 DT inputs in the R123 profile compile through `make dtbs`. With the same
compiler, all 32 are byte-identical to direct compilation using the previous
pinned source/include layout. A second build compiles nothing. Touching the
Myron audio include rebuilds its affected DTBO. Rebuilding all 32 files also
passes with all three source repositories mounted read-only.

See `android/myron-native/dt-validation.json`. Clang 19.1.7 and the in-tree DTC
were used for this host-side test. No Image, loadable module set, flashable
DT image assembly, full ROM, or device boot has been validated on this branch.

The 30 imported binding headers come from platform commit
`cba60332e49c0978aa83c8bb77bf157893c14fb6`; their list is in
`android/myron-native/dt-header-import.json`. ACK build scripts remain intact.
The device DTS contents, including the validated audio/camera fixes, remain
unchanged.

## Remaining integration

The installed module catalog contains 3 ACK modules, 226 Qualcomm/platform
modules, and 68 external modules. The separate Qualcomm platform source must
still be integrated into the native kernel/module trees. In particular, the
MCA, hardware-ID, event and touchscreen additions are not all reachable through
the existing native Makefiles. The platform repository is not a standalone
replacement for ACK and must not simply overwrite the ACK core/build files.

After the driver and configuration work is compiled and checked, the device
tree can select TARGET_KERNEL_SOURCE, TARGET_KERNEL_CONFIG and the standard
external-module variables, and remove TARGET_NO_KERNEL_OVERRIDE and the Python
kernel rule. Native DT image assembly must preserve the R123 FastRPC child
order, board IDs and eight base variants. Keep the working audio module option
`machine_dlkm myron_tfa_links=1` and EROFS vendor_dlkm packaging during migration.
