/*
 * Copyright (c) 2011-2021 The Linux Foundation. All rights reserved.
 * Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
 *
 * Permission to use, copy, modify, and/or distribute this software for
 * any purpose with or without fee is hereby granted, provided that the
 * above copyright notice and this permission notice appear in all
 * copies.
 *
 * THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL
 * WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE
 * AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL
 * DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR
 * PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
 * TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
 * PERFORMANCE OF THIS SOFTWARE.
 */

static void lim_populate_mcs_set_ht_per_vdev(struct mac_context *mac_ctx,
						      struct sHtCaps *ht_cap,
						      uint8_t vdev_id,
						      uint8_t band)
{
	struct wlan_mlme_nss_chains *nss_chains_ini_cfg;
	struct wlan_objmgr_vdev *vdev =
			wlan_objmgr_get_vdev_by_id_from_psoc(mac_ctx->psoc,
							     vdev_id,
							     WLAN_MLME_SB_ID);
	if (!vdev) {
		pe_err("Got NULL vdev obj, returning");
		return;
	}
	if (!ht_cap->supportedMCSSet[1])
		goto end;
	nss_chains_ini_cfg = mlme_get_ini_vdev_config(vdev);
	if (!nss_chains_ini_cfg) {
		pe_err("nss chain dynamic config NULL");
		goto end;
	}

	/* convert from unpacked to packed structure */
	if (nss_chains_ini_cfg->rx_nss[band] == 1)
		ht_cap->supportedMCSSet[1] = 0;

end:
	wlan_objmgr_vdev_release_ref(vdev, WLAN_MLME_SB_ID);
}

static QDF_STATUS lim_send_ht_caps_ie(struct mac_context *mac_ctx,
				      enum QDF_OPMODE device_mode,
				      uint8_t vdev_id)
{
	uint8_t ht_caps[DOT11F_IE_HTCAPS_MIN_LEN + 2] = {0};
	tHtCaps *p_ht_cap = (tHtCaps *)(&ht_caps[2]);
	QDF_STATUS status_5g, status_2g;
	bool nan_beamforming_supported;

	ht_caps[0] = DOT11F_EID_HTCAPS;
	ht_caps[1] = DOT11F_IE_HTCAPS_MIN_LEN;
	lim_set_ht_caps(mac_ctx, ht_caps,
			DOT11F_IE_HTCAPS_MIN_LEN + 2);
	/* Get LDPC and over write for 2G */
	p_ht_cap->advCodingCap = lim_get_rx_ldpc(mac_ctx,
						 CHAN_ENUM_2437);
	/* Get self cap for HT40 support in 2G */
	if (lim_get_sta_cb_mode_for_24ghz(mac_ctx, vdev_id)) {
		p_ht_cap->supportedChannelWidthSet = 1;
		p_ht_cap->shortGI40MHz = 1;
	} else {
		p_ht_cap->supportedChannelWidthSet = 0;
		p_ht_cap->shortGI40MHz = 0;
	}

	lim_populate_mcs_set_ht_per_vdev(mac_ctx, p_ht_cap, vdev_id,
					 NSS_CHAINS_BAND_2GHZ);

	nan_beamforming_supported =
		ucfg_nan_is_beamforming_supported(mac_ctx->psoc);
	if (device_mode == QDF_NDI_MODE && !nan_beamforming_supported) {
		p_ht_cap->txBF = 0;
		p_ht_cap->implicitTxBF = 0;
		p_ht_cap->explicitCSITxBF = 0;
	}

	status_2g = lim_send_ie(mac_ctx, vdev_id, DOT11F_EID_HTCAPS,
				CDS_BAND_2GHZ, &ht_caps[2],
				DOT11F_IE_HTCAPS_MIN_LEN);
	/*
	 * Get LDPC and over write for 5G - using channel 64 because it
	 * is available in all reg domains.
	 */
	p_ht_cap->advCodingCap = lim_get_rx_ldpc(mac_ctx, CHAN_ENUM_5320);
	/* Get self cap for HT40 support in 5G */
	if (mac_ctx->roam.configParam.channelBondingMode5GHz) {
		p_ht_cap->supportedChannelWidthSet = 1;
		p_ht_cap->shortGI40MHz = 1;
	} else {
		p_ht_cap->supportedChannelWidthSet = 0;
		p_ht_cap->shortGI40MHz = 0;
	}
	lim_populate_mcs_set_ht_per_vdev(mac_ctx, p_ht_cap, vdev_id,
					 NSS_CHAINS_BAND_5GHZ);
	status_5g = lim_send_ie(mac_ctx, vdev_id, DOT11F_EID_HTCAPS,
				CDS_BAND_5GHZ, &ht_caps[2],
				DOT11F_IE_HTCAPS_MIN_LEN);

	if (QDF_IS_STATUS_SUCCESS(status_2g) &&
	    QDF_IS_STATUS_SUCCESS(status_5g))
		return QDF_STATUS_SUCCESS;

	return QDF_STATUS_E_FAILURE;
}
