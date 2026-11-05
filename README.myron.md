# Myron native Kbuild migration

This native integration has passed host kernel/module compilation and device
DT/module-packaging checks. It is not a complete ROM or a device-tested
replacement for the working kernel adapter.

## Source layout

The three ordinary repo projects in `android/myron-native/manifest.xml` are:

* `kernel/xiaomi/sm8850`: ACK 6.12.81, Qualcomm platform drivers and native DT rules.
* `kernel/xiaomi/sm8850-modules`: external drivers with native Canoe Kbuild rules.
* `kernel/xiaomi/sm8850-devicetrees`: the validated device-tree sources.

Source synchronization belongs to repo. Kernel compilation does not download
sources or invoke Python, Starlark or Bazel. The normal ROM kernel.mk will use
TARGET_KERNEL_SOURCE, TARGET_KERNEL_CONFIG and TARGET_KERNEL_EXT_MODULES.
The native device integration uses these standard rules. This three-project
manifest itself does not modify the ROM's BoardConfig.

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
* All 68 required external modules compile and link through the normal ROM-style
  make invocation, with all three source repositories read-only. Modpost checks
  remain enabled.
* Stock modules_install produces 406 modules. All 297 original catalog entries
  are present, with a complete dependency closure and passing depmod symbol and
  version checks. The actual Evolution kernel.mk module packaging macro passes
  in a host fixture for system_dlkm, vendor_dlkm, vendor_boot and recovery.
* Native headers_install exports 1005 headers, including asm/signal.h and
  asm-generic/signal.h. This does not test Soong's sandbox or bionic cleaning.
* All 32 DT inputs remain byte-identical to the pinned source reference using
  the same DTC. No-op, include-dependency and full read-only DT rebuild tests pass.

See `android/myron-native/kernel-validation.json`, `dt-validation.json` and
`platform-import.json` for the tested scope and source provenance. These are
host build checks, not an ABI compatibility certification or runtime tests.
The test host lacks Rust and pahole; olddefconfig consequently does not enable
the corresponding optional Rust/BTF configuration. A build using the ROM's
production toolchain remains necessary.

`vendor/myron-dt.config` is retained for isolated DT compilation only.

## Device integration and remaining verification

The native device branch uses standard BoardConfig kernel variables and
kernel.mk for compilation and module installation. It removes the private
Kleaf build rule, workspace setup helpers and writable-source exception.

DT compilation uses make dtbs. The standard BOARD_CUSTOM_DTBIMG_MK and
BOARD_CUSTOM_DTBOIMG_MK hooks retain the R123 DT image assembler, including
FastRPC child order and the eight variants' selection IDs. That image helper
consumes already compiled DTBs; it does not compile kernels or manage source
workspaces. Native device make-rule tests produce byte-identical DTB/DTBO
images to the R123 assembly reference with the same input compiler/tools.

The default fragment-by-fragment ROM configuration sequence matches the
configuration used for the compiled native kernel. Tests also cover read-only
source directories, separate outputs and no-op DT image builds.

Keep `options machine_dlkm myron_tfa_links=1` in vendor_dlkm module options and
retain EROFS lz4hc,9. A host payload estimate with all extra GKI modules is
33,513,472 bytes, below the reported 53,805,056-byte partition. This estimate
does not include final ROM SELinux/AVB metadata or production BTF/Rust changes.
Extra GKI modules are installed but are not added to the original load lists.

Production-toolchain, complete Android ROM/Kati/Soong, final signed-image and
phone runtime checks remain necessary. No new boot, camera, audio or runtime
success is inferred from the host tests. Device-side host validation records
are in kernel/NATIVE-VALIDATION.json in the native device branch.
