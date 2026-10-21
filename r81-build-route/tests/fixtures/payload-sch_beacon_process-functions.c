QDF_STATUS
sch_beacon_edca_process(struct mac_context *mac, tSirMacEdcaParamSetIE *edca,
			struct pe_session *session)
{
	bool follow_ap_edca;
#ifdef FEATURE_WLAN_DIAG_SUPPORT
	host_log_qos_edca_pkt_type *log_ptr = NULL;
#endif /* FEATURE_WLAN_DIAG_SUPPORT */

	if (!(mac->mlme_cfg)) {
		pe_err("invalid mlme cfg");
		return QDF_STATUS_E_FAILURE;
	}

	follow_ap_edca = mlme_get_follow_ap_edca_flag(session->vdev);

	/* Myron: keep the AP's contention parameters on 2.4 GHz STA links. */
	if (session->opmode == QDF_STA_MODE &&
	    wlan_reg_is_24ghz_ch_freq(session->curr_op_freq)) {
		follow_ap_edca = true;
		pe_info_rl("R81 AP EDCA vdev %d freq %d BE cwmin %d cwmax %d aifs %d",
			   session->vdev_id, session->curr_op_freq,
			   edca->acbe.cw.min, edca->acbe.cw.max,
			   edca->acbe.aci.aifsn);
	}

	session->gLimEdcaParamSetCount = edca->qosInfo.count;
	session->gLimEdcaParams[QCA_WLAN_AC_BE] = edca->acbe;
	session->gLimEdcaParams[QCA_WLAN_AC_BK] = edca->acbk;
	session->gLimEdcaParams[QCA_WLAN_AC_VI] = edca->acvi;
	session->gLimEdcaParams[QCA_WLAN_AC_VO] = edca->acvo;

	if (mac->mlme_cfg->edca_params.enable_edca_params && !follow_ap_edca) {
		session->gLimEdcaParams[QCA_WLAN_AC_VO].aci.aifsn =
			mac->mlme_cfg->edca_params.edca_ac_vo.vo_aifs;
		session->gLimEdcaParams[QCA_WLAN_AC_VI].aci.aifsn =
			mac->mlme_cfg->edca_params.edca_ac_vi.vi_aifs;
		session->gLimEdcaParams[QCA_WLAN_AC_BK].aci.aifsn =
			mac->mlme_cfg->edca_params.edca_ac_bk.bk_aifs;
		session->gLimEdcaParams[QCA_WLAN_AC_BE].aci.aifsn =
			mac->mlme_cfg->edca_params.edca_ac_be.be_aifs;

		session->gLimEdcaParams[QCA_WLAN_AC_VO].cw.min =
			mac->mlme_cfg->edca_params.edca_ac_vo.vo_cwmin;
		session->gLimEdcaParams[QCA_WLAN_AC_VI].cw.min =
			mac->mlme_cfg->edca_params.edca_ac_vi.vi_cwmin;
		session->gLimEdcaParams[QCA_WLAN_AC_BK].cw.min =
			mac->mlme_cfg->edca_params.edca_ac_bk.bk_cwmin;
		session->gLimEdcaParams[QCA_WLAN_AC_BE].cw.min =
			mac->mlme_cfg->edca_params.edca_ac_be.be_cwmin;

		session->gLimEdcaParams[QCA_WLAN_AC_VO].cw.max =
			mac->mlme_cfg->edca_params.edca_ac_vo.vo_cwmax;
		session->gLimEdcaParams[QCA_WLAN_AC_VI].cw.max =
			mac->mlme_cfg->edca_params.edca_ac_vi.vi_cwmax;
		session->gLimEdcaParams[QCA_WLAN_AC_BK].cw.max =
			mac->mlme_cfg->edca_params.edca_ac_bk.bk_cwmax;
		session->gLimEdcaParams[QCA_WLAN_AC_BE].cw.max =
			mac->mlme_cfg->edca_params.edca_ac_be.be_cwmax;
	}
#ifdef FEATURE_WLAN_DIAG_SUPPORT
	WLAN_HOST_DIAG_LOG_ALLOC(log_ptr, host_log_qos_edca_pkt_type,
				 LOG_WLAN_QOS_EDCA_C);
	if (log_ptr) {
		log_ptr->aci_be = session->gLimEdcaParams[QCA_WLAN_AC_BE].aci.aci;
		log_ptr->cw_be =
			session->gLimEdcaParams[QCA_WLAN_AC_BE].cw.max << 4
				| session->gLimEdcaParams[QCA_WLAN_AC_BE].cw.min;
		log_ptr->txoplimit_be =
			session->gLimEdcaParams[QCA_WLAN_AC_BE].txoplimit;
		log_ptr->aci_bk =
			session->gLimEdcaParams[QCA_WLAN_AC_BK].aci.aci;
		log_ptr->cw_bk =
			session->gLimEdcaParams[QCA_WLAN_AC_BK].cw.max << 4
				| session->gLimEdcaParams[QCA_WLAN_AC_BK].cw.min;
		log_ptr->txoplimit_bk =
			session->gLimEdcaParams[QCA_WLAN_AC_BK].txoplimit;
		log_ptr->aci_vi =
			session->gLimEdcaParams[QCA_WLAN_AC_VI].aci.aci;
		log_ptr->cw_vi =
			session->gLimEdcaParams[QCA_WLAN_AC_VI].cw.max << 4
				| session->gLimEdcaParams[QCA_WLAN_AC_VI].cw.min;
		log_ptr->txoplimit_vi =
			session->gLimEdcaParams[QCA_WLAN_AC_VI].txoplimit;
		log_ptr->aci_vo =
			session->gLimEdcaParams[QCA_WLAN_AC_VO].aci.aci;
		log_ptr->cw_vo =
			session->gLimEdcaParams[QCA_WLAN_AC_VO].cw.max << 4
				| session->gLimEdcaParams[QCA_WLAN_AC_VO].cw.min;
		log_ptr->txoplimit_vo =
			session->gLimEdcaParams[QCA_WLAN_AC_VO].txoplimit;
	}
	WLAN_HOST_DIAG_LOG_REPORT(log_ptr);
#endif /* FEATURE_WLAN_DIAG_SUPPORT */
	pe_debug("Vdev_id: %d Edca param enabled %d. Updating Local Params to: AC_BE: AIFSN: %d, ACM %d, CWmin %d, CWmax %d, TxOp %d  AC_BK: AIFSN: %d, ACM %d, CWmin %d, CWmax %d, TxOp %d  AC_VI: AIFSN: %d, ACM %d, CWmin %d, CWmax %d, TxOp %d  AC_VO: AIFSN: %d, ACM %d, CWmin %d, CWmax %d, TxOp %d",
		 session->vdev_id,
		 mac->mlme_cfg->edca_params.enable_edca_params,
		 session->gLimEdcaParams[0].aci.aifsn,
		 session->gLimEdcaParams[0].aci.acm,
		 session->gLimEdcaParams[0].cw.min,
		 session->gLimEdcaParams[0].cw.max,
		 session->gLimEdcaParams[0].txoplimit,
		 session->gLimEdcaParams[1].aci.aifsn,
		 session->gLimEdcaParams[1].aci.acm,
		 session->gLimEdcaParams[1].cw.min,
		 session->gLimEdcaParams[1].cw.max,
		 session->gLimEdcaParams[1].txoplimit,
		 session->gLimEdcaParams[2].aci.aifsn,
		 session->gLimEdcaParams[2].aci.acm,
		 session->gLimEdcaParams[2].cw.min,
		 session->gLimEdcaParams[2].cw.max,
		 session->gLimEdcaParams[2].txoplimit,
		 session->gLimEdcaParams[3].aci.aifsn,
		 session->gLimEdcaParams[3].aci.acm,
		 session->gLimEdcaParams[3].cw.min,
		 session->gLimEdcaParams[3].cw.max,
		 session->gLimEdcaParams[3].txoplimit);

	return QDF_STATUS_SUCCESS;
}
