# R80 Wi-Fi compatibility candidate

This compile-only experiment limits the 2.4 GHz station connection's spatial
stream count while retaining the 5 GHz settings. It is a test candidate for the
observed 2.4 GHz TX retries and gateway reachability failures; it is not a claim
that the root cause has been established.

The route retains the successful R79 source preparation and pinned toolchain.
It requests only `canoe_perf_qca_cld_peach-v2`, the mandatory dependency builds,
and the two core metadata targets. The seven unrelated R79 repair targets are
not selected. The actual KO/symvers paths are resolved from Bazel's action graph
before compilation; all patched C files must feed the selected WLAN action.

The output contains one candidate KO, its symvers, dependency symvers, the
compiled core ABI evidence, source files and reports. The compiled Image is
evidence only: the running R79 kernel remains authoritative. Compilation does
not authorize replacing additional modules or prove runtime ABI compatibility.

The source tests run before sync on retained source fixtures and after applying
the patch against the actual prepared workspace. Failure stops the workflow.

The final fastboot package must be assembled separately against the exact R79
image, retaining the existing kernel and every unselected module. It must carry
the tested R79 image as rollback, and pass the existing full module ABI and
native identity checks before device validation. No persistent Wi-Fi settings,
firmware files, country code, power calibration or NUD policy are changed by
this compile route.
