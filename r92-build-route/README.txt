R92: restore the missing ADSP PD/PPS provider

R90's 47-module selection included the PD protocol class and its consumers but
omitted qcom_adsp_pd_protocol, the hardware-facing provider used by the stock
module set. Without its registration, the class's provider wrappers return -1
and cannot perform PD capability queries or PPS requests.

This route preserves the frozen R90 preparation and all earlier production
tests. It adds exactly one explicit target to the same Bazel invocation:
qcom_adsp_pd_protocol.ko. The only patched production C is that added provider;
all original R90 C/configuration inputs remain guarded. The provider payload and
firmware-layout review are pinned alongside its host tests.

reference/ retains sanitized historical stock disassembly/property evidence and
its hashes. Stock images, original stock KO binaries and phone session logs are
not part of this source route. The historical firmware reference has not been
proven byte-equal to the currently installed firmware.

The R90 boundary prepares the exact R88, R89 and R90 source generations and
runs their production tests before the R92 provider patch is applied. Actual
aquery compile chains and source pins are recorded for all 48 module targets.
The configuration checks still require the protected BQ firmware-programming
configuration to be disabled. The resulting effective config must also match
the R90 config byte-for-byte.

Finalization requires 48 real AArch64 ELF modules and checks all 47 inherited
module binaries byte-for-byte against successful R90 run 40046239434. The new
module must actually import the PD registration/unregistration, GLINK read/write
and notifier registration/unregistration APIs; their CRCs must match the four
co-built MCA providers. Missing callbacks cannot pass based solely on a planned
module list.

The reused frozen engine retains legacy r88 filenames and 47-module phase text;
those strings do not describe the R92 scope. The R92 contract, actual aquery,
commands, 48-module inventory and R92 status are authoritative. No historical
route or guard is edited.

Commands:
  python3 -B r92-build-route/build_pd_provider.py --repo-root . --check-inputs
  python3 -B r92-build-route/test_build_guards.py --repo-root .
  python3 -B r92-build-route/test_compiled_scope.py

Artifacts are inactive compile evidence only. They do not contain a flashable
image and do not assert runtime ABI compatibility, successful authentication or
physical fast charging. The retained-kernel ABI, device binding, runtime loading
contract and real charging behavior still require separate review.

Runtime follow-up after successful CI: keep the normal 249-module baseline and
add this provider to the 46-module MCA handover, giving 295 installed modules.
Load it at the new index 24 after mca_protocol_pd_class and before pd_auth, subpmic proxy and
quickchg. Rebuild the native handover helper and image contract rather than
reusing the old 45-module helper. The additional expected real binding is:
  /sys/bus/platform/devices/soc:mca_qcom_pd_protocol
  /sys/bus/platform/drivers/adsp_pd_protocol
  /sys/module/qcom_adsp_pd_protocol
The reviewed merged stock DT already enables this device; no DT mutation is
included. Actual binding must still be checked on the new runtime image.
