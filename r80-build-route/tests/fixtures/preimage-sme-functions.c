/*
 * Copyright (c) 2012-2021 The Linux Foundation. All rights reserved.
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

#define STA_NSS_CHAINS_SHIFT               0
#define SAP_NSS_CHAINS_SHIFT               3
#define P2P_GO_NSS_CHAINS_SHIFT            6
#define P2P_CLI_CHAINS_SHIFT               9
#define TDLS_NSS_CHAINS_SHIFT              12
#define IBSS_NSS_CHAINS_SHIFT              15
#define P2P_DEV_NSS_CHAINS_SHIFT           18
#define OCB_NSS_CHAINS_SHIFT               21
#define NAN_NSS_CHAIN_SHIFT                24
#define NSS_CHAIN_MASK                     0x7
#define GET_VDEV_NSS_CHAIN(x, y)         (((x) >> (y)) & NSS_CHAIN_MASK)

static uint8_t sme_get_nss_chain_shift(enum QDF_OPMODE device_mode)
{
	switch (device_mode) {
	case QDF_STA_MODE:
		return STA_NSS_CHAINS_SHIFT;
	case QDF_SAP_MODE:
		return SAP_NSS_CHAINS_SHIFT;
	case QDF_P2P_GO_MODE:
		return P2P_GO_NSS_CHAINS_SHIFT;
	case QDF_P2P_CLIENT_MODE:
		return P2P_CLI_CHAINS_SHIFT;
	case QDF_IBSS_MODE:
		return IBSS_NSS_CHAINS_SHIFT;
	case QDF_P2P_DEVICE_MODE:
		return P2P_DEV_NSS_CHAINS_SHIFT;
	case QDF_OCB_MODE:
		return OCB_NSS_CHAINS_SHIFT;
	case QDF_TDLS_MODE:
		return TDLS_NSS_CHAINS_SHIFT;
	case QDF_NAN_DISC_MODE:
	case QDF_NDI_MODE:
		return NAN_NSS_CHAIN_SHIFT;
	default:
		sme_err("Device mode %d invalid", device_mode);
		return STA_NSS_CHAINS_SHIFT;
	}
}

static void
sme_check_nss_chain_ini_param(struct wlan_mlme_nss_chains *vdev_ini_cfg,
			      uint8_t rf_chains_supported,
			      enum nss_chains_band_info band)
{
	vdev_ini_cfg->rx_nss[band] = QDF_MIN(vdev_ini_cfg->rx_nss[band],
					     rf_chains_supported);
	vdev_ini_cfg->tx_nss[band] = QDF_MIN(vdev_ini_cfg->tx_nss[band],
					     rf_chains_supported);
}

static void
sme_fill_nss_chain_params(struct mac_context *mac_ctx,
			  struct wlan_mlme_nss_chains *vdev_ini_cfg,
			  enum QDF_OPMODE device_mode,
			  enum nss_chains_band_info band,
			  uint8_t rf_chains_supported)
{
	uint8_t nss_chain_shift;
	uint8_t max_supported_nss;
	enum coex_btc_chain_mode btc_chain_mode;
	struct wlan_mlme_nss_chains *nss_chains_ini_cfg =
					&mac_ctx->mlme_cfg->nss_chains_ini_cfg;
	QDF_STATUS status;

	nss_chain_shift = sme_get_nss_chain_shift(device_mode);
	max_supported_nss =
			mac_ctx->mlme_cfg->vht_caps.vht_cap_info.enable_mimo ?
			WLAN_MAX_VDEV_NSS : 1;

	/*
	 * If target supports Antenna sharing, set NSS to 1 for 2.4GHz band for
	 * NDI vdev.
	 */
	if (device_mode == QDF_NDI_MODE && mac_ctx->mlme_cfg->gen.as_enabled &&
	    band == NSS_CHAINS_BAND_2GHZ)
		max_supported_nss = NSS_1x1_MODE;

	status = ucfg_coex_psoc_get_btc_chain_mode(mac_ctx->psoc,
						   &btc_chain_mode);
	if (QDF_IS_STATUS_ERROR(status)) {
		sme_err("Failed to get BT coex chain mode");
		btc_chain_mode = WLAN_COEX_BTC_CHAIN_MODE_UNSETTLED;
	}

	if (band == NSS_CHAINS_BAND_2GHZ &&
	    (btc_chain_mode == WLAN_COEX_BTC_CHAIN_MODE_FDD ||
	     btc_chain_mode == WLAN_COEX_BTC_CHAIN_MODE_HYBRID))
		max_supported_nss = NSS_1x1_MODE;

	/* If the fw doesn't support two chains, num rf chains can max be 1 */
	vdev_ini_cfg->num_rx_chains[band] =
		QDF_MIN(GET_VDEV_NSS_CHAIN(
				nss_chains_ini_cfg->num_rx_chains[band],
				nss_chain_shift), rf_chains_supported);

	vdev_ini_cfg->num_tx_chains[band] =
		QDF_MIN(GET_VDEV_NSS_CHAIN(
				nss_chains_ini_cfg->num_tx_chains[band],
				nss_chain_shift), rf_chains_supported);

	/* If 2x2 mode is disabled, then max rx, tx nss can be 1 */
	vdev_ini_cfg->rx_nss[band] =
		QDF_MIN(GET_VDEV_NSS_CHAIN(
				nss_chains_ini_cfg->rx_nss[band],
				nss_chain_shift), max_supported_nss);

	vdev_ini_cfg->tx_nss[band] =
		QDF_MIN(GET_VDEV_NSS_CHAIN(
				nss_chains_ini_cfg->tx_nss[band],
				nss_chain_shift), max_supported_nss);

	vdev_ini_cfg->num_tx_chains_11a =
		QDF_MIN(GET_VDEV_NSS_CHAIN(
				nss_chains_ini_cfg->num_tx_chains_11a,
				nss_chain_shift), rf_chains_supported);

	/* If the fw doesn't support two chains, num rf chains can max be 1 */
	vdev_ini_cfg->num_tx_chains_11b =
		QDF_MIN(GET_VDEV_NSS_CHAIN(
				nss_chains_ini_cfg->num_tx_chains_11b,
				nss_chain_shift), rf_chains_supported);

	vdev_ini_cfg->num_tx_chains_11g =
		QDF_MIN(GET_VDEV_NSS_CHAIN(
				nss_chains_ini_cfg->num_tx_chains_11g,
				nss_chain_shift), rf_chains_supported);

	vdev_ini_cfg->disable_rx_mrc[band] =
				nss_chains_ini_cfg->disable_rx_mrc[band];

	vdev_ini_cfg->disable_tx_mrc[band] =
				nss_chains_ini_cfg->disable_tx_mrc[band];
	/*
	 * Check whether the rx/tx nss is greater than the number of rf chains
	 * supported by FW, if so downgrade the nss to the number of chains
	 * supported, as higher nss cannot be supported with less chains.
	 */
	sme_check_nss_chain_ini_param(vdev_ini_cfg, rf_chains_supported,
				      band);
}

static QDF_STATUS
sme_validate_from_ini_config(struct wlan_mlme_nss_chains *user_cfg,
			     struct wlan_mlme_nss_chains *ini_cfg,
			     enum nss_chains_band_info band)
{
	if (user_cfg->num_rx_chains[band] >
	    ini_cfg->num_rx_chains[band])
		return QDF_STATUS_E_FAILURE;

	if (user_cfg->num_tx_chains[band] >
	    ini_cfg->num_tx_chains[band])
		return QDF_STATUS_E_FAILURE;

	if (user_cfg->rx_nss[band] >
	    ini_cfg->rx_nss[band])
		return QDF_STATUS_E_FAILURE;

	if (user_cfg->tx_nss[band] >
	    ini_cfg->tx_nss[band])
		return QDF_STATUS_E_FAILURE;

	if (user_cfg->num_tx_chains_11a >
	    ini_cfg->num_tx_chains_11a)
		return QDF_STATUS_E_FAILURE;

	if (user_cfg->num_tx_chains_11b >
	    ini_cfg->num_tx_chains_11b)
		return QDF_STATUS_E_FAILURE;

	if (user_cfg->num_tx_chains_11g >
	    ini_cfg->num_tx_chains_11g)
		return QDF_STATUS_E_FAILURE;

	return QDF_STATUS_SUCCESS;
}

void sme_update_vdev_type_nss(mac_handle_t mac_handle, uint8_t max_supp_nss,
			      enum nss_chains_band_info band)
{
	struct mac_context *mac_ctx = MAC_CONTEXT(mac_handle);
	struct vdev_type_nss *vdev_nss;

	struct wlan_mlme_nss_chains *nss_chains_ini_cfg =
					&mac_ctx->mlme_cfg->nss_chains_ini_cfg;

	if (band == NSS_CHAINS_BAND_5GHZ)
		vdev_nss = &mac_ctx->vdev_type_nss_5g;
	else
		vdev_nss = &mac_ctx->vdev_type_nss_2g;

	vdev_nss->sta = QDF_MIN(max_supp_nss, GET_VDEV_NSS_CHAIN(
						nss_chains_ini_cfg->
							rx_nss[band],
						STA_NSS_CHAINS_SHIFT));
	vdev_nss->sap = QDF_MIN(max_supp_nss, GET_VDEV_NSS_CHAIN(
						nss_chains_ini_cfg->
							rx_nss[band],
						SAP_NSS_CHAINS_SHIFT));
	vdev_nss->p2p_go = QDF_MIN(max_supp_nss, GET_VDEV_NSS_CHAIN(
						nss_chains_ini_cfg->
							rx_nss[band],
						P2P_GO_NSS_CHAINS_SHIFT));
	vdev_nss->p2p_cli = QDF_MIN(max_supp_nss, GET_VDEV_NSS_CHAIN(
						nss_chains_ini_cfg->
							rx_nss[band],
						P2P_CLI_CHAINS_SHIFT));
	vdev_nss->p2p_dev = QDF_MIN(max_supp_nss, GET_VDEV_NSS_CHAIN(
						nss_chains_ini_cfg->
							rx_nss[band],
						P2P_DEV_NSS_CHAINS_SHIFT));
	vdev_nss->ibss = QDF_MIN(max_supp_nss, GET_VDEV_NSS_CHAIN(
						nss_chains_ini_cfg->
							rx_nss[band],
						IBSS_NSS_CHAINS_SHIFT));
	vdev_nss->tdls = QDF_MIN(max_supp_nss, GET_VDEV_NSS_CHAIN(
						nss_chains_ini_cfg->
							rx_nss[band],
						TDLS_NSS_CHAINS_SHIFT));
	vdev_nss->ocb = QDF_MIN(max_supp_nss, GET_VDEV_NSS_CHAIN(
						nss_chains_ini_cfg->
							rx_nss[band],
						OCB_NSS_CHAINS_SHIFT));
	vdev_nss->nan = QDF_MIN(max_supp_nss, GET_VDEV_NSS_CHAIN(
						nss_chains_ini_cfg->
							rx_nss[band],
						NAN_NSS_CHAIN_SHIFT));
	vdev_nss->ndi = QDF_MIN(max_supp_nss, GET_VDEV_NSS_CHAIN(
						nss_chains_ini_cfg->
							rx_nss[band],
						NAN_NSS_CHAIN_SHIFT));

	sme_debug("band %d NSS:sta %d sap %d cli %d go %d dev %d ibss %d tdls %d ocb %d nan %d",
		  band, vdev_nss->sta, vdev_nss->sap, vdev_nss->p2p_cli,
		  vdev_nss->p2p_go, vdev_nss->p2p_dev, vdev_nss->ibss,
		  vdev_nss->tdls, vdev_nss->ocb, vdev_nss->nan);
}
