# SPDX-License-Identifier: MIT

obj-$(CONFIG_DRM_DISPLAY_DP_AUX_BUS) += drm_dp_aux_bus.o



# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/drivers/gpu/drm/display
obj-$(CONFIG_DRM_DISPLAY_HELPER) += drm_display_helper.o
drm_display_helper-y := drm_display_helper_mod.o
ifneq ($(filter y m,$(CONFIG_DRM_DISPLAY_DP_HELPER)),)
drm_display_helper-y += drm_dp_dual_mode_helper.o drm_dp_helper.o drm_dp_mst_topology.o drm_dsc_helper.o
endif
ifneq ($(filter y m,$(CONFIG_DRM_DISPLAY_DP_TUNNEL)),)
drm_display_helper-y += drm_dp_tunnel.o
endif
ifneq ($(filter y m,$(CONFIG_DRM_DISPLAY_HDCP_HELPER)),)
drm_display_helper-y += drm_hdcp_helper.o
endif
ifneq ($(filter y m,$(CONFIG_DRM_DISPLAY_HDMI_HELPER)),)
drm_display_helper-y += drm_hdmi_helper.o drm_scdc_helper.o
endif
ifneq ($(filter y m,$(CONFIG_DRM_DP_AUX_CHARDEV)),)
drm_display_helper-y += drm_dp_aux_dev.o
endif
ifneq ($(filter y m,$(CONFIG_DRM_DP_CEC)),)
drm_display_helper-y += drm_dp_cec.o
endif
