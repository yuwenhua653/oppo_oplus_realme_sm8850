# R81 Wi-Fi AP EDCA compatibility candidate

This compile-only experiment lets an ordinary 2.4 GHz station use the AP's
advertised EDCA parameters instead of the local EDCA override. The source
contract defines the exact initial-association, beacon-update and channel-switch
write scope. This is a compatibility candidate, not an established root-cause fix.

The route reuses the successful R80 build procedure with the frozen R79 source
preparation and pinned toolchain. It applies only the R81 source patch after
R79 preparation; it does not apply the R80 NSS/HT capability experiment. Exact
source and function guards verify that the original NSS/HT behavior remains.

Only `canoe_perf_qca_cld_peach-v2`, its mandatory build dependencies and the two
core metadata targets are requested. The actual KO and symvers paths are resolved
from Bazel's action graph before compilation, and every patched C file must feed
the selected WLAN action. Source tests run on retained fixtures before sync and
on the actual prepared source after applying the patch.

The output contains one candidate WLAN KO, symvers, core ABI evidence, source and
build reports. The compiled Image is evidence only. Packaging remains a separate
step against the exact retained R79 kernel and provider modules, with exact ABI
and native identity checks before device validation. Compilation alone does not
approve the candidate for runtime use.
