# R77 compile-only thermal request observer

This route compiles the independent `myron_buck_thermal` receiver. It records
thermal-limit requests in memory and reports them. It does not regulate charging,
raise charging power, authenticate a thermal source, or perform MCA, GLINK,
voter, power_supply, cooling-device or charger operations. No module is installed
or loaded, and no image, DT, daemon configuration or runtime module list changes.

The module is disabled by default. `enable_observer` is its only boolean parameter,
mode 0444, default false; disabled initialization returns `-EPERM` before driver
registration. Even an explicitly enabled observer always reports
`source_verified=0`, `eligible_for_control=0`, `hardware_applied=0` and
`active_mode_selected=0`. This compilation does not approve enabling it on a device.

## Frozen source preparation

Repository parent commit: `513e1f19a44dd67f127999dfa27f77ac88e70f49`.
The R76 foundation contract is reused exactly:
`e2eef12cfc674435a85e5f3c92355353be2daf49cf27c65a9ec0f8f40e27deac`.
Its R75/R61 preparation, source/toolchain revisions and original runtime Image
identity remain authoritative. The R76 source and all earlier routes are unchanged.

The new production source is
`payload/drivers/thermal/myron_buck_thermal.c`, SHA256
`b4a54111dac86447b527859f96a57aa4cc5b83ada2f49472c9d37b4803eb9be5`.
FIX1 renames only the module initialization function to
`myron_buck_thermal_init`, avoiding the real kernel Maple Tree `mt_init` API.
Its three test calls use the new name; the host shim now declares the real
`mt_init(struct maple_tree *)` signature so the original source fails with the
same conflicting-types error and the corrected source passes all eight groups.
Receiver behavior, the original independent specification and API evidence
remain unchanged. `receiver-contract.json` binds the corrected repository source
and this revision's passing host result. `thermal-contract.json` defines the
CI source mapping and published inventory.

## Actual build wiring and output scope

Four explicit DDK targets are built and collected: unchanged `qti_pmic_glink`,
`myron_mca_readonly`, `myron_bq_readonly`, and new `myron_buck_thermal`.
The three original MCA foundation targets (`mca_adsp_glink`,
`mca_qcom_subpmic_proxy`, `mca_strategy_buckchg`) are not rebuilt or represented
as R77 outputs. Their previously verified R76 source preparation is retained.
The three existing read-only KOs must retain their exact R75/R76 bytes and hashes.

| Prepared workspace path under `vendor/qcom/sm8850` | R77 operation |
| --- | --- |
| `drivers/thermal/myron_buck_thermal.c` | New independent single translation unit |
| `drivers/xiaomi/myron/Kconfig` | Append `MYRON_BUCK_THERMAL`, tristate, default n, depends on OF and SYSFS |
| `drivers/xiaomi/myron/modules.bzl` | Append one DDK registration for the exact source and KO, with no module dependencies |
| `configs/canoe_perf.bzl` | Select only `CONFIG_MYRON_BUCK_THERMAL=m` for target compilation |

DDK generates the Makefile/Kbuild from the registration, then the KernelModule
action compiles it and the final action copies its KO. No unused handwritten
Makefile or runtime `modules.load` entry is added. Aquery must show the observer's
real DDK Makefile generator, exact source-to-compiler-to-KO chain, and no compiler
actions for the three omitted MCA foundation targets.

The R77 planner derives all append bytes from frozen R61/R75 inputs, never from
untrusted workspace contents. It combines the parent ten operations and this
layer into eleven distinct final destinations. Every source revision and preimage
is checked before any overlay mutation. Exact R61/R75/R77 configuration states
are accepted to support a fresh workspace and idempotent verification; arbitrary
local edits are rejected. Final verification merges all inherited, R75, R76 and
R77 hashes without running the old workspace checker against new appended files.

Collection requires exactly four actual ELF module identities, own symvers,
release strings, existing QTI/read-only metadata, and observer metadata with no
module dependencies, exported private interfaces, soft dependencies or control
imports. The completion marker follows successful collection and hash checks.
Dependency symvers and core ABI metadata may also be collected; they do not
constitute an installable runtime dependency closure. A newly built Image is
evidence only and must not replace the original runtime Image.

## Receiver behavior and limits

An enabled receiver can bind the `mca_charger_thermal` compatible only after its
`wired_thermal` property matches all 150 big-endian cells of the frozen 600-byte
15-by-10 table. This validates the table at probe, not a whole board/DTBO or a
live thermal-policy owner. Its private `myron_buck_thermal` sysfs group exposes:

| File | Mode | Accepted values |
| --- | --- | --- |
| `wired_ctrl_limit` | 0600 | 0–15; zero selects no table row |
| `wired_chg_curr` | 0600 | 0–2147483647 uA, independent raw request |
| `wired_chg_curr2` | 0600 | 0–2147483647 uA, separate raw request |
| `wired_thermal_remove` | 0600 | 0–1; removal never grants unlimited current |
| `snapshot` | 0444 | One coherent memory view with explicit unverified status |

Inputs accept bounded ASCII decimal syntax and reject invalid/overflow values
without changing state. Every accepted write has a monotonic sequence and
BOOTTIME receipt timestamp. These are request observations, not sensor samples,
heartbeats, verified freshness or an atomic daemon transaction. Table columns
remain mA observations; current requests remain exact uA. No active charging mode
or current-channel identity is inferred. No compatibility with an existing
thermal daemon path, permissions or selection behavior is claimed.

Probe publishes sysfs only after validation and context initialization. Removal
uses `sysfs_remove_group` outside the state mutex, then clears drvdata before
devres frees context. There are no workers. The actual frozen Linux 6.12 API and
original Image export review is separate from host stubs; actual KO ABI/CFI and
device lifetime remain later gates.

## Narrow local and CI checks

Use a complete checkout at the pinned parent plus this route:

```sh
python3 r77-build-route/thermal_inputs.py --root "$PWD"
python3 r77-build-route/test_integration.py
python3 r77-build-route/run_host_tests.py --root "$PWD" --reports /tmp/r77-fresh-reports
```

Only the new observer host suite and new integration risks are retested. The
whole production translation unit retains the kernel `current` macro and strict
prototype guards, ASan and UBSan. Its eight groups include numeric/error bounds,
all 150 DT cell mutations and 8000 concurrent writes with snapshot reads. Host
stubs test source logic and callback order, not actual kernfs/device unload safety.
Unchanged R75/R76 host suites retain their prior frozen successful evidence.

The workflow triggers only for this route or its own workflow file. Uploads are
limited to the new source route/workflow, named reports, source lock and verified
compile outputs. No captures, old private source tree, BQ/auth/key implementation,
flash package, image assembly or device action is included.
