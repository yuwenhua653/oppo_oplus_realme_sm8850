# SPDX-License-Identifier: GPL-2.0-only
M ?= $(CURDIR)
.PHONY: all modules modules_install clean
all: modules
modules modules_install clean:
	$(MAKE) -C $(KERNEL_SRC) M=$(M) $@ $(KBUILD_OPTIONS)
