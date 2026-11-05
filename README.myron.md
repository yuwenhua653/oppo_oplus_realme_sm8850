# Myron native Kbuild migration

This is a development integration, not yet a complete ROM or a device-tested
replacement for the working kernel adapter.

## Source layout

The three ordinary repo projects in `android/myron-native/manifest.xml` are:

* `kernel/xiaomi/sm8850`: ACK 6.12.81, Qualcomm platform drivers and native DT rules.
* `kernel/xiaomi/sm8850-modules`: external drivers with native Canoe Kbuild rules.
* `kernel/xiaomi/sm8850-devicetrees`: the validated device-tree sources.

Source synchronization belongs to repo. Kernel compilation does not download
sources or invoke Python, Starlark or Bazel. The normal ROM kernel.mk will use
TARGET_KERNEL_SOURCE, TARGET_KERNEL_CONFIG and TARGET_KERNEL_EXT_MODULES once
the remaining external drivers and image assembly are validated. This manifest
does not activate or modify the ROM's BoardConfig.

## Kernel configuration

The intended normal configuration sequence is:

```
gki_defconfig vendor/canoe_GKI.config vendor/myron_GKI.config
```

`canoe_GKI.config` carries the platform options. `myron_GKI.config` limits the
platform-module selection to the previously validated installed catalog while
retaining ACK zram and zsmalloc. The 226 platform modules use ordinary in-tree
Kconfig and per-directory Makefiles. Public FF-A definitions remain ACK's, so
its KVM implementation and transport share the same API. SCM includes TZMEM
once, instead of also building a conflicting standalone TZMEM module.

External modules use the relative M= and separate O= layout expected by
LineageOS/Evolution kernel.mk. Absolute M= retains upstream behavior. There is
no MYRON_DT_MODE, custom jobs/RAM parameter, writable-source allowlist, private
kernel build wrapper, or replacement build-message echo.

## Verified scope

With Debian Clang 19.1.7 and normal host build tools:

* `make Image modules` succeeds, including modpost with errors enabled.
* Image is generated and all 338 selected in-tree modules link. All 226 required
  platform modules are present in modules.order and as .ko files.
* A platform module rebuild and the Image/modules targets succeed with all
  three source repositories bind-mounted read-only.
* 40 of the 68 required external modules compile and link through the normal
  ROM-style make invocation, with all three source repositories read-only.
  These are audio (34), external display, HFI core, hardware fence, sync fence,
  FastRPC and MMRM. See the external repository's validation record.
* All 32 DT inputs remain byte-identical to the pinned source reference using
  the same DTC. No-op, include-dependency and full read-only DT rebuild tests pass.

See `android/myron-native/kernel-validation.json`, `dt-validation.json` and
`platform-import.json` for the tested scope and source provenance. These are
host build checks, not an ABI compatibility certification or runtime tests.
The test host lacks Rust and pahole; olddefconfig consequently does not enable
the corresponding optional Rust/BTF configuration. A build using the ROM's
production toolchain remains necessary.

`vendor/myron-dt.config` is retained for isolated DT compilation only.

## Remaining integration

The other 28 external modules still need native source/configuration/symbol
validation, including graphics, display, camera, connectivity and data drivers.
Do not activate the native device BoardConfig before those checks pass.

The normal GKI configuration also builds modules beyond the old installed
catalog; ROM partition selection and size must be checked, rather than assuming
that all 338 should be copied to vendor_dlkm.

Native DT image assembly must preserve the R123 FastRPC child order, board IDs
and eight base variants. Keep `options machine_dlkm myron_tfa_links=1` in the
vendor module options file, and retain EROFS vendor_dlkm packaging. None of this
phase's host checks demonstrates phone boot, camera, audio or full ROM success.
