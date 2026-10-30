# R97 fix3: reduce REC module validation overhead

R97 fix2 restores the PON keys, and physical testing confirms that the power key
and battery display work. The remaining delay occurs before the battery/Health
service starts. The hardware loader runs a full live-module allowlist check
before each insertion. Its old implementation starts a separate `toybox grep`
process for every already-loaded module on every check.

Fix3 retains every check at its original call site. It reads the same allowlist
and checks each module's `Live` state and exact name using shell builtins.
Quoted newline boundaries prevent partial-name and pattern matches. Failure to
read the allowlist rejects the check. Module hashes, first-stage requirements,
device identity checks, module insertion order, timeouts, battery ownership
checks and Health gating remain unchanged.

Only `r97-runtime/common.sh` changes in the released fix2 image. The assembler
accepts one exact input image and the unchanged paired R97 vendor_boot. It checks
all 129 module hashes, exact CPIO inventory and metadata, every unchanged raw
CPIO record, the three pinned REC core files, empty early-boot DLKM directories,
deterministic output, Android header and AVB image hash. Android runtime, PID1,
kernel, DTB/DTBO, TWRP and all module bytes remain unchanged.

Run source-only guard tests (no private images needed):

```sh
python3 twrp/myron-r97/pair/test_recovery_speed.py
```

Tests execute both guards under available host shells with 142, 164 and 221 live
modules and count the old/new external grep calls. Unknown and non-Live modules,
partial names, literal pattern characters and a missing allowlist are tested.
These checks establish behavior and process reduction; host timings do not
predict exact phone boot times.

Build locally from the released private fix2 image:

```sh
python3 twrp/myron-r97/pair/fix_recovery_speed.py \
  --source /private/recovery_r97_fix2.img \
  --paired-vendor /private/vendor_boot_r97.img \
  --pair-tools twrp/myron-r97/pair \
  --out /private/fix3/recovery_r97_fix3.img
python3 twrp/myron-r97/pair/test_recovery_speed.py \
  --source /private/recovery_r97_fix2.img \
  --output /private/fix3/recovery_r97_fix3.img \
  --pair-tools twrp/myron-r97/pair
```

The output directory must be fresh. The assembler also creates a `recovery.img`
hard link for partition-name-based AVB verification. Existing historical
`read_candidate.verify_candidate` and overlay pins remain unchanged; they
continue to validate their original 126-module R97 inputs.

Fix3 needs physical timing verification. It does not fake an early percentage,
return cached battery data, start Health before battery validation, parallelize
module insertions, or claim instantaneous display.
