# Redmi K90PM / myron R114 full kernel build

The device is Redmi K90PM. Its existing Android device directory remains
`device/xiaomi/myron`. This round changes the kernel build route only; it does
not edit ROM core code, Android device policy, driver behavior, or partition images.

The source baseline is integration commit
`7b74ce235cabd1f966a679c9fc03ceda1e6160f5`, with common kernel commit
`41a2024a9e2eb66ab0643a865d74943b4ee3cff8` (6.12.81, Android 16 KMI generation 6).
The inherited public R88/R92 build contract records
`6.12.81-android16-6-maybe-dirty-4k` as its baseline release.

This route reuses the hash-locked R94/R92 preparation chain, then adds the
existing R18/R55 remoteproc and R81/R82 WLAN/CNSS fixes. It does not apply the
superseded R80 forced-NSS experiment. It requests the complete platform target,
GKI modules, DT outputs, and the explicitly prepared charging/LED targets.
It never labels a single-module build as a full build.

Kleaf `--config=stamp` is used for configuration, compilation and output queries.
Immediately before those actions, `SOURCE_DATE_EPOCH` is set to the current
runner wall clock. The Image's embedded Linux banner must contain that actual
build timestamp. It is not the upstream commit date or a fabricated date.
The release must contain the actual common Git SHA; dirty source remains dirty.
No custom marketing suffix, fixed `maybe` placeholder, fake clock, or arbitrary
GitHub integration SHA is substituted for the kernel's actual source revision.

The pinned upstream implementation used to test stamping is from:
https://android.googlesource.com/kernel/build/+/e114b907efb6c8ef513617cc13fdc0f87c46abde/kleaf/workspace_status_stamp.py
The copy under `reference` is test material. It does not replace Kleaf in CI.

Output checks require matching Image and kernel.release, actual timestamp,
same-build vermagic for every collected KO, required device DT outputs and at
least 295 module files. Source revisions, source diff hashes, workflow commit,
start/end times, elapsed duration and output checksums are retained in reports.

Artifacts are complete source-build outputs, not a flashable package or an
autoload list. The platform graph includes alternative/reference modules.
New version strings require matching rebuilt modules; do not replace only the
Image while keeping old-release modules. Partition assembly, exact runtime
module selection, CRC checks against that selection and device testing follow
after the build succeeds. This workflow does not flash or create a release.
The latest device SELinux and Recovery integration is retained locally for
that assembly stage; its derived files are not publicly uploaded by this job.

The original R13 DTS commit `8b86fedda64183338411f9751f5e62ce25997620`
is no longer retrievable. The explicit migration pins candidate
`928b59fcca6306aaba39343a474dc5930d8f424d` (tree
`3da2d6f5050abf14d97ab7503d7c94cf8188288c`). This includes the immediate
build-error fix after the initial Myron platform-map commit, but excludes later
OS4 changes. ACK, LineageOS SoC/modules and every other source pin remain unchanged.

`dt_source_bridge.py` verifies the immutable R18 archive and its nested R13 and
platform archives before deriving five extracted metadata/revision-guard edits.
It normalizes three build files to exact historical preimages and checks 123
archived hashes/blobs before legacy patches. The original legacy helpers remain
hash checked; their DTS revision and the two derived collection-manifest hashes
are adapted in memory. Driver contracts, source HEAD/origin verification and
bundle checks remain active. The new lock hash is
`0c420df07cbc9d1e44de020cc1e3b8ac74510003a6fca12ce4c9798991db1a7a`.

This is not proof of complete historical DTS equivalence: the archive does not
contain old hashes for every Myron board/charging/touch/camera/display source.
The compiled diagnostic composition must pass the R13 libfdt overlay merge,
audio-provider and touch-framework checks. Equal duplicate DT outputs may be
deduplicated for that check; conflicting bytes fail. OEM DTB/DTBO must remain in
later partition assembly until replacement images are separately qualified.

Local preflights: `python3 -B r114-build-route/test_route.py` and
`python3 -B r114-build-route/test_dt_source_bridge.py`.
GitHub workflow: `.github/workflows/build-k90pm-full-r114.yml`.
