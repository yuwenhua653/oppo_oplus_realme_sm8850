# Myron native external modules

This branch provides ordinary Canoe Kbuild rules for all 68 external modules
in the device-validated R123 installed catalog. It is a host-validated build
migration; native ROM image assembly and phone testing are still pending.

## Standard build integration

Place this project at `kernel/xiaomi/sm8850-modules`, alongside
`kernel/xiaomi/sm8850` and `kernel/xiaomi/sm8850-devicetrees`. The ROM uses
`TARGET_KERNEL_EXT_MODULE_ROOT` and `TARGET_KERNEL_EXT_MODULES`; the ordered
paths are recorded in `android/myron-native/external-modules.list`.

The standard external-module rule supplies KERNEL_SRC, relative M= and separate
O=/OUT_DIR. Ordinary Makefiles support the default target, modules,
modules_install and clean. Module.symvers dependencies point into the output
tree. No prepare step, source download, Bazel, Starlark or Python builder runs
during compilation, and source directories need no writable exception.

Canoe Kbuild source lists and module-local configuration follow the pinned DDK
selection at b2877f865a4fc591ce15223059062dc0162e058b. Kconfig defaults are
preserved, including RMNET LA support and GPU options. WLAN retains the
peach-v2 selection, kernel-header feature probes and external IPA interface.
Its feature header is generated under the object directory with dependency
tracking. Camera build metadata comes from the kernel generated headers.
The SMC trace include path supports the native layout while retaining its
legacy fallback. Existing non-Canoe Kbuild bodies remain; other SoCs were not
tested with the new Makefile wrappers.

## Verified scope

All 68 external .ko files compile and link with modpost errors enabled against
native kernel baa10617cb95a58c2e353db319c3e37293f94ad8. All three source trees
were mounted read-only. This includes audio (34), camera, display, GPU, EVA,
FastRPC, MMRM, synchronization, secure services, data networking, WLAN,
Bluetooth and NFC.

Stock modules_install with INSTALL_MOD_STRIP=1 also succeeds. The combined
kernel/external installation contains 406 modules, includes all 297 original
catalog entries, and passes depmod's symbol/version checks. The original
catalog remains closed over its module dependencies. See the JSON validation
records and source-selection records in android/myron-native.

A host-only EROFS lz4hc,9 size check, including the extra GKI modules, produces
a 33,513,472-byte vendor payload against the reported 53,805,056-byte partition.
This is an estimate, not a flashable Android image; final ROM metadata, SELinux
labels, AVB and partition packaging still require validation.

Tests used Clang 19.1.7; Rust and pahole were unavailable. Production-toolchain,
full-ROM and phone runtime tests are not claimed. Keep the working device
adapter until native DT assembly and ROM packaging are qualified.

The device module options must retain `options machine_dlkm myron_tfa_links=1`
and vendor_dlkm must retain its validated EROFS configuration. This migration
does not force the audio option in driver C source.
