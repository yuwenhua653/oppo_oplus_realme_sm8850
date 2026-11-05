# SPDX-License-Identifier: GPL-2.0-only
# M and O are supplied by the ROM's standard external-module rule.
M ?= $(CURDIR)
AUDIO_ROOT := $(if $(filter /%,$(M)),$(M),$(abspath $(KERNEL_SRC)/$(M)))
KBUILD_OPTIONS += AUDIO_ROOT=$(AUDIO_ROOT)
KBUILD_OPTIONS += MODNAME=audio_dlkm
KBUILD_OPTIONS += KBUILD_EXTRA_SYMBOLS=$(abspath $(O)/$(M)/../mm-drivers/msm_ext_display/Module.symvers)

.PHONY: all modules modules_install clean
all: modules

modules modules_install clean:
	$(MAKE) -C $(KERNEL_SRC) M=$(M) $@ $(KBUILD_OPTIONS)
