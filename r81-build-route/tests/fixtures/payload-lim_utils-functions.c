void lim_switch_channel_cback(struct mac_context *mac, QDF_STATUS status,
			      uint32_t *data, struct pe_session *pe_session)
{
	struct scheduler_msg mmhMsg = { 0 };
	struct switch_channel_ind *pSirSmeSwitchChInd;
	struct wlan_channel *des_chan;
	struct vdev_mlme_obj *mlme_obj;

	if (QDF_IS_STATUS_ERROR(status)) {
		lim_tear_down_link_with_ap(mac, pe_session->peSessionId,
					   REASON_CHANNEL_SWITCH_FAILED,
					   eLIM_HOST_DISASSOC);
		return;
	}

	mlme_obj = wlan_vdev_mlme_get_cmpt_obj(pe_session->vdev);
	if (!mlme_obj) {
		pe_err("vdev component object is NULL");
		return;
	}

	des_chan = mlme_obj->vdev->vdev_mlme.des_chan;
	if (!des_chan) {
		pe_err("des_chan is NULL");
		return;
	}
	pe_session->curr_op_freq = pe_session->curr_req_chan_freq;
	/* We need to restore pre-channelSwitch state on the STA */
	if (lim_restore_pre_channel_switch_state(mac, pe_session) !=
	    QDF_STATUS_SUCCESS) {
		pe_err("Could not restore pre-channelSwitch (11h) state, resetting the system");
		return;
	}

	/*
	 * Re-evaluate band-specific STA EDCA after a successful CSA even if
	 * the AP keeps its four-bit parameter-set count unchanged.
	 */
	if (pe_session->opmode == QDF_STA_MODE)
		pe_session->gLimEdcaParamSetCount = 0xff;

	mmhMsg.type = eWNI_SME_SWITCH_CHL_IND;
	pSirSmeSwitchChInd = qdf_mem_malloc(sizeof(*pSirSmeSwitchChInd));
	if (!pSirSmeSwitchChInd)
		return;

	pSirSmeSwitchChInd->messageType = eWNI_SME_SWITCH_CHL_IND;
	pSirSmeSwitchChInd->length = sizeof(*pSirSmeSwitchChInd);
	pSirSmeSwitchChInd->freq = des_chan->ch_freq;
	pSirSmeSwitchChInd->sessionId = pe_session->smeSessionId;
	pSirSmeSwitchChInd->chan_params.ch_width = des_chan->ch_width;
	if (des_chan->ch_width > CH_WIDTH_20MHZ) {
		pSirSmeSwitchChInd->chan_params.sec_ch_offset =
			pe_session->gLimChannelSwitch.sec_ch_offset;
		pSirSmeSwitchChInd->chan_params.center_freq_seg0 =
							des_chan->ch_freq_seg1;
		pSirSmeSwitchChInd->chan_params.mhz_freq_seg0 =
							des_chan->ch_cfreq1;
		pSirSmeSwitchChInd->chan_params.center_freq_seg1 =
							des_chan->ch_freq_seg2;
		pSirSmeSwitchChInd->chan_params.mhz_freq_seg1 =
							des_chan->ch_cfreq2;
	}
	pSirSmeSwitchChInd->ch_phymode = des_chan->ch_phymode;

	pSirSmeSwitchChInd->status = status;
	qdf_mem_copy(pSirSmeSwitchChInd->bssid.bytes, pe_session->bssId,
		     QDF_MAC_ADDR_SIZE);
	mmhMsg.bodyptr = pSirSmeSwitchChInd;
	mmhMsg.bodyval = 0;

	MTRACE(mac_trace(mac, TRACE_CODE_TX_SME_MSG,
			 pe_session->peSessionId, mmhMsg.type));

	sys_process_mmh_msg(mac, &mmhMsg);

	lim_switch_channel_vdev_started(pe_session);
}
