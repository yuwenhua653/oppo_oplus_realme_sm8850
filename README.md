# Redmi K90 Pro Max / K90PM (myron) kernel

This branch is the build entry for the complete, committed kernel source used
by the R114 adaptation. It is for **Redmi K90PM / myron**, not Xiaomi 17.
The kernel base remains Google ACK + LineageOS Qualcomm.

## Build from Git

Use an x86-64 Ubuntu 24.04 host with at least 16 GB RAM and 100 GB free disk.
Install dependencies:

```sh
sudo apt-get update
sudo apt-get install -y git python3 build-essential bc bison flex libssl-dev libelf-dev libncurses-dev zstd lz4 rsync zip unzip cpio pkg-config patch
git clone --single-branch --branch myron/kernel-6.12 https://github.com/yuwenhua653/oppo_oplus_realme_sm8850.git myron-kernel
cd myron-kernel
python3 -B build.py --jobs 2 --ram-mb 10000
```

`build.py` fetches all exact revisions in `sources.lock.json`, creates the
Kleaf workspace links, then builds the kernel, GKI modules, Qualcomm/device
modules and DT outputs. No historical adaptation ZIP, phone dump or patch
application is required. Internet access to GitHub and android.googlesource.com
is needed for the locked sources, build tools and toolchains.

To fetch without compiling:

```sh
python3 -B sync_sources.py --workspace kernel_workspace --jobs 4
```

The full adapted source is in these branches of this repository:

| Project | Complete source branch |
| --- | --- |
| ACK common | `myron/common-android16-6.12` |
| Qualcomm platform drivers | `myron/sm8850` |
| External Qualcomm modules | `myron/sm8850-modules` |
| Device-tree sources | `myron/sm8850-devicetrees` |

These are complete root snapshots, not patches. All upstream tracked source
and license files are retained. Upstream commit IDs and URLs are recorded in
`sources.lock.json`; `source-provenance.json` records byte equivalence with the
R114 source that passed compilation and user-reported device testing. Upstream
Git ancestry is not included in the snapshot branches. DTS provenance is
recorded separately from the LOS Qualcomm driver sources.

## Version and outputs

The version uses the actual committed common-source Git hash. The script fails
if a source checkout is dirty, an SCM override is present, or output contains
`dirty`, `maybe`, or `mybe`. `-4k` is retained because this configuration uses
4 KiB pages. Build timestamps use the real start time; measured compilation
duration and total sync/build duration are reported separately.

Outputs: `kernel_workspace/integration-artifacts/full/`.
Logs and source revisions: `kernel_workspace/integration-reports/`.
The build verifies the Image banner, module vermagic and all 297 required
runtime module names. These are compilation outputs, not a flash package.
Boot, vendor_boot and Recovery assembly must use matching modules and preserve
the separately validated SELinux/Recovery configuration and OEM DTB/DTBO.

The `K90PM committed source full build` Actions workflow in this branch runs
the same `build.py` command directly. It does not rerun source migration.
Before external modules are built, the real Image version and UTC build time
are checked. The full build reuses that compiled kernel through Bazel's cache.
Timestamp validation compares the exact UTC second and accepts GNU date's
space-padded day field. It does not substitute the commit date or accept a
different build time. Kernel diagnostics and collected outputs are uploaded
even if later validation fails; check `validation-status.json` and the job
result before using any output. An uploaded artifact alone is not proof of
successful validation.

For development, commit changes on the relevant source branch and update that
project's full SHA in the lock file before building in a new workspace. The
build does not discard local edits or invent a clean version for uncommitted code.

## R118 device-tree-only follow-up

The lock now selects DTS `feff8ac781caca95799d642f79a6bfa23a17e639`: v1 camera
collection, optional GPU fuse references, and Myron LPASS/SoundWire provider fixes.
Common kernel and all module source commits are unchanged. The R115 binary outputs
remain evidence for their original lock only; do not relabel them as an R118 build.
A new full build is still required for outputs claiming this updated lock.

Device-owned DT-only compilation and validation live under `kernel/` on
`myron/device-cnb-source`. They can compile the 32 profile inputs using only the
four pinned source projects. OEM DT remains the ROM default while the two CanoeP
thermal-profile ID mappings are under review. No full build is triggered by this
lock-only diagnostic update (`[skip ci]`); normal full-build dispatch remains available.

The follow-up also collects existing MMRM, hardware fence, IPC, mailbox, fingerprint
helper and WCN786x DT components; the device profile respects OEM variant coverage.
