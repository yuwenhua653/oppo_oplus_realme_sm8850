# Myron R82 CNSS firmware selection candidate

Existing logs show the retained CNSS loading `peach/bdwlan.elf` and
`peach/regdb.bin`. The supplied firmware image contains different bytes for the
Myron board file and Xiaomi regulatory database. The source patch restores the
reviewed Myron/Peach filename policy while retaining the existing DT override
and generic board-ID behavior. This is a candidate fix; Wi-Fi stability still
requires a device test.

The CI route reuses the complete, frozen R79 preparation and builds only
`//vendor/qcom/sm8850-modules/qcom/opensource/wlan/platform:canoe_perf_cnss2`
plus mandatory prerequisites. Only `cnss2.ko` is a replacement candidate.
The existing kernel, HWID provider, R81 WLAN module, loader and other modules
remain the runtime baseline. Dependency KOs and the newly compiled Image are
not replacement candidates.

The CNSS target must receive `MYRON_CNSS_FILE_SELECTION` and the existing HWID
provider through its actual DDK build actions. After compilation, the route
requires both HWID getter imports to be strong undefined symbols and the ELF
module dependency to include `hwid`.

Before upload, run `python3 r82-build-route/freeze_inputs.py` after all route
files are final. Then run the workflow's frozen-input preflight and host source
tests. The full artifact is compile-only; validate its imports, exports, CRCs,
namespaces and CFI boundary against the exact retained runtime before assembly.
No system root is required for installing the eventual separately reviewed
test image.
