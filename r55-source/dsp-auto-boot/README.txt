R55 Canoe ADSP/CDSP automatic boot correction

Evidence
The R52 original vendor_boot_a image contains qcom_q6v5_pas.ko with
canoe_adsp_resource.auto_boot=1 and canoe_cdsp_resource.auto_boot=1.
The R18-derived module used through R54 has both fields zero. OEM and adapted
ADSP/CDSP early_boot remain zero; SOCCP auto_boot and early_boot remain one.
OEM instruction and OF-table evidence is recorded in:
  r54-runtime-analysis/oem-startup-independent.json
  r54-runtime-analysis/oem-reference/descriptor-comparison.json

R54 loads all 213 expected modules but no ADSP/CDSP firmware start is observed.
spf_core_platform only populates its machine/LPASS children after the ADSP
GPR endpoint probes and APM is ready. This explains why loaded audio modules
alone did not create a sound card. Automatic startup restores a verified OEM
driver setting; it does not add an init/sysfs force-start or SSR workaround.

Source scope
Repository: LineageOS/android_kernel_qcom_sm8850
Commit: 557159b6a0d06f1c6f07ec4c1f22bc9309a113e4
File: drivers/remoteproc/qcom_q6v5_pas.c
Required R18 source SHA256:
  06b11e9af536b1ce77c9278602de35d0557e7a908cba12446f71196ec6c4d94a
R55 output source SHA256:
  caf8b7e6ab2786b3cea57b7bd15528f8823409bddcebd8bcb83e63bae14c0723
The diff adds exactly two .auto_boot = true initializers. The R18 SOCCP fix,
all early_boot fields, modem behavior, firmware/PAS data and DT remain intact.
reference/*.c are exact before/after review copies, not replacement modules.

Build integration
1. Run the existing pinned R13 source preparation and R18 apply_soccp.py.
2. Run:
   python3 apply_dsp_auto_boot.py --soc /path/to/vendor/qcom/sm8850
   Optional --check verifies the known pre/post state without writing.
3. Recompile the existing target with the same kernel configuration/toolchain:
   //vendor/qcom/sm8850:canoe_perf/drivers/remoteproc/qcom_q6v5_pas
4. Run:
   python3 check_dsp_auto_boot_elf.py --source /path/to/qcom_q6v5_pas.c \
     --module /path/to/qcom_q6v5_pas.ko --report /path/to/elf-report.json
   Optional --baseline-module must be the exact R18 module locked in JSON.
5. Independently audit module ABI/modversions, dependencies and image placement
   against the current Image before assembling or testing a new image.

Gate coverage
The source applicator verifies the pinned Git HEAD and exact source hashes.
The ELF gate requires exact R55 source bytes, all four Canoe descriptor bytes
equal to R18 except the two reviewed auto_boot bytes, unchanged early_boot,
and the actual desc+54 LDRB to rproc+1249 STRB assignment in adsp_probe.
It also resolves every descriptor pointer relocation to its string value and
checks all four Canoe OF compatible-to-descriptor mappings. Compiler section
offsets are not treated as semantic identities. Null pointer fields must stay
null. This closes the ET_REL gap where raw pointer bytes alone can remain zero
while relocation targets change.

The previous R18 guard that retained ADSP/CDSP=false is deliberately superseded
by this new revision because direct OEM binary evidence proves true is needed.
The old artifact and its checker remain unchanged.

Validation and limits
VALIDATION.json records source and negative-gate checks. No compiled candidate
or device success is claimed until the separate build/runtime checks finish.
No OEM module is copied into the adapted image, and no ELF binary patch is made.
