# SPDX-License-Identifier: Apache-2.0
# Both images are assembled and checked together by the DTB image rule.
$(BOARD_PREBUILT_DTBOIMAGE): $(INSTALLED_DTBIMAGE_TARGET)
	@mkdir -p $(dir $@)
	cp $(DTB_OUT)/myron-images/dtbo.img $@
