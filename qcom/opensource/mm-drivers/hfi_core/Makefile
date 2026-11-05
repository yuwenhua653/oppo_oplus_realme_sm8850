# SPDX-License-Identifier: GPL-2.0-only
# M and O are supplied by the ROM's standard external-module rule.
M ?= $(CURDIR)
module_src := $(if $(filter /%,$(M)),$(M),$(abspath $(KERNEL_SRC)/$(M)))
KBUILD_OPTIONS += MSM_HFI_CORE_ROOT=$(abspath $(module_src)/..)/

.PHONY: all modules modules_install clean
all: modules

modules modules_install clean:
	$(MAKE) -C $(KERNEL_SRC) M=$(M) $@ $(KBUILD_OPTIONS)
