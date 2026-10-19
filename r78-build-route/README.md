# Myron R78 audio and brightness build

This additive route starts from repository commit
`01845c8dcdbc7a5c42f8037f4839e4b12e61137f`. It preserves the R60/R61 and R75–R77
source contracts and the original R75 runtime image. It does not replace any old
driver, load any module, alter a device module list, or create a flashable image.

One CI run compiles the audio candidates listed in the source contract and the
brightness `msm_drm` candidate, sharing the pinned kernel and their declared dependencies.
The earlier 49-module build and the completed R77 observer lifecycle are not
repeated. Every candidate KO is explicitly selected and collected as a real ELF
objects. Dependency symvers are preserved for later compatibility review.

Before source sync, the workflow verifies the immutable R77 parent and every
new source/build input. Before compilation, actual aquery results resolve each
selected target's unique KO and Module.symvers and prove that its expected
source files feed the compiler-to-KO action chain. No output filename is guessed
and accepted only after a long build. A completion marker is written only after
all actual ELF identities and the exact frozen KO inventory pass.

New audio and display source details, inherited display startup fixes and
remaining hardware compatibility limits are recorded in their component
contracts. The R77 thermal observer is retained unchanged; daemon endpoint work
does not imply that charging control has been enabled. Compiling the TFA driver
and machine routing does not establish amplifier chip revision support; a
source contract that still reports an unsupported revision blocks runtime use.

Local source checks (in a complete existing repository with this update):

```
python3 r78-build-route/r78_inputs.py --root .
python3 r78-build-route/test_integration.py
```

The workflow is `.github/workflows/build-myron-multimedia-r78.yml`. Its output is
compile-only. On-device audio/brightness behavior still requires validation of
the resulting artifacts and one combined installation package. No `su` or
`adb root` test is included.

R78 fix1 corrects the external TFA Kconfig source to use `KCONFIG_EXT_PREFIX`.
The regression test executes the pinned upstream flatten script from the Bazel
workspace layout and reproduces the original missing-file error. CI builds the
Kconfig genrule on its own before starting the kernel/module build, and overrides
the inherited keep-going option so later failures stop further build work.
