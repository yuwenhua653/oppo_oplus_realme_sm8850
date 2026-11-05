# SPDX-License-Identifier: GPL-2.0-only
M ?= $(CURDIR)
module_src := $(if $(filter /%,$(M)),$(M),$(abspath $(KERNEL_SRC)/$(M)))
KBUILD_OPTIONS += NFC_ROOT=$(module_src)

.PHONY: all modules modules_install clean
all: modules

modules modules_install clean:
	$(MAKE) -C $(KERNEL_SRC) M=$(M) $@ $(KBUILD_OPTIONS)
