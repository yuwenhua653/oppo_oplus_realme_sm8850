# SPDX-License-Identifier: GPL-2.0
obj-$(CONFIG_LIB80211) += lib80211.o
obj-$(CONFIG_LIB80211_CRYPT_WEP) += lib80211_crypt_wep.o
obj-$(CONFIG_LIB80211_CRYPT_CCMP) += lib80211_crypt_ccmp.o
obj-$(CONFIG_LIB80211_CRYPT_TKIP) += lib80211_crypt_tkip.o
obj-y += tests/

obj-$(CONFIG_WEXT_CORE) += wext-core.o
obj-$(CONFIG_WEXT_PROC) += wext-proc.o
obj-$(CONFIG_WEXT_SPY) += wext-spy.o
obj-$(CONFIG_WEXT_PRIV) += wext-priv.o


CFLAGS_trace.o := -I$(src)

ifneq ($(CONFIG_CFG80211_EXTRA_REGDB_KEYDIR),)
endif

$(obj)/shipped-certs.c: $(sort $(wildcard $(src)/certs/*.hex))
	@$(kecho) "  GEN     $@"
	$(Q)(echo '#include "reg.h"'; \
	  echo 'const u8 shipped_regdb_certs[] = {'; \
	  echo | cat - $^ ; \
	  echo '};'; \
	  echo 'unsigned int shipped_regdb_certs_len = sizeof(shipped_regdb_certs);'; \
	 ) > $@

$(obj)/extra-certs.c: $(CONFIG_CFG80211_EXTRA_REGDB_KEYDIR) \
		      $(sort $(wildcard $(CONFIG_CFG80211_EXTRA_REGDB_KEYDIR)/*.x509))
	@$(kecho) "  GEN     $@"
	$(Q)(set -e; \
	  allf=""; \
	  for f in $^ ; do \
	      test -f $$f || continue;\
	      # similar to hexdump -v -e '1/1 "0x%.2x," "\n"' \
	      thisf=$$(od -An -v -tx1 < $$f | \
	                   sed -e 's/ /\n/g' | \
	                   sed -e 's/^[0-9a-f]\+$$/\0/;t;d' | \
	                   sed -e 's/^/0x/;s/$$/,/'); \
	      # file should not be empty - maybe command substitution failed? \
	      test ! -z "$$thisf";\
	      allf=$$allf$$thisf;\
	  done; \
	  ( \
	      echo '#include "reg.h"'; \
	      echo 'const u8 extra_regdb_certs[] = {'; \
	      echo "$$allf"; \
	      echo '};'; \
	      echo 'unsigned int extra_regdb_certs_len = sizeof(extra_regdb_certs);'; \
	  ) > $@)

clean-files += shipped-certs.c extra-certs.c

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/net/wireless
obj-$(CONFIG_CFG80211) += cfg80211.o
cfg80211-y := ap.o chan.o core.o ethtool.o ibss.o mesh.o mlme.o nl80211.o ocb.o pmsr.o radiotap.o reg.o scan.o sme.o sysfs.o trace.o util.o shipped-certs.o
ifneq ($(filter y m,$(CONFIG_OF)),)
cfg80211-y += of.o
endif
ifneq ($(filter y m,$(CONFIG_CFG80211_DEBUGFS)),)
cfg80211-y += debugfs.o
endif
ifneq ($(filter y m,$(CONFIG_CFG80211_WEXT)),)
cfg80211-y += wext-compat.o wext-sme.o
endif
