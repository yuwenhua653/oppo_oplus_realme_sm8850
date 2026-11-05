# Myron native external modules

This branch adds ordinary Kbuild rules for Canoe without changing the tested
driver implementation. It is not yet a complete native external-module tree.

The validated subset is 40 modules: audio (34), msm_ext_display, msm_hfi_core,
msm_hw_fence, sync_fence, frpc-adsprpc and msm-mmrm. Source lists and feature
options follow the pinned Canoe DDK declarations at
b2877f865a4fc591ce15223059062dc0162e058b, with static Kbuild files replacing the
build-time Starlark dependency. The existing non-Canoe Kbuild branches remain.

The ROM's standard external-module rule supplies KERNEL_SRC, relative M= and
absolute O=/OUT_DIR. Build msm_ext_display before audio; audio reads its
Module.symvers from the output directory. All other symbol dependencies of this
validated subset are supplied by the native platform kernel. Native host
FastRPC uses fastrpc_rpmsg.c and produces frpc-adsprpc.ko, not the legacy trusted
VM module. MMRM preserves its six original source inputs.

All 40 .ko files pass normal modpost against the native kernel without an
undefined-symbol warning override. Compilation succeeds with the kernel,
module and DTS sources mounted read-only. See
android/myron-native/module-validation.json for the host test record, and the
adjacent audio/mm source-selection records. Clang 19.1.7 was used; Rust and
pahole were unavailable on the test host. No phone runtime or full ROM test is
claimed.

The driver option `machine_dlkm myron_tfa_links=1` remains required in the device
module options file. This port preserves the driver's default and does not
silently force the option in C source.

The remaining 28 installed external modules still require native validation.
Do not switch a production device tree to this branch yet.
