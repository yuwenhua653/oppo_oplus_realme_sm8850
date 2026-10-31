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

Local preflight: `python3 -B r114-build-route/test_route.py`.
GitHub workflow: `.github/workflows/build-k90pm-full-r114.yml`.
