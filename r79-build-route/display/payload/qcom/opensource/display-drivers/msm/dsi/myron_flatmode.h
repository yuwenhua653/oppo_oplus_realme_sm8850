/* SPDX-License-Identifier: GPL-2.0-only */
/* Included once by dsi_display.c, after its internal transfer helpers.
 * MI flatmode_check is a validation result, not a writable panel mode.
 * DT contract: MiCode display-drivers 6def61b29a39710078287416afd3b62f43729c37,
 * msm/mi_disp/mi_disp_flatmode.c. No status or mode value is synthesized.
 */
#ifndef MYRON_FLATMODE_H
#define MYRON_FLATMODE_H

#define MYRON_FLAT_MAX_CMDS 8U
#define MYRON_FLAT_MAX_READ 256U

struct myron_flat_set {
	const u8 *data;
	u32 length, count;
	bool low_power;
};
struct myron_flat_config {
	struct myron_flat_set offset, status, end;
	u32 lengths[MYRON_FLAT_MAX_CMDS];
	u32 expected[MYRON_FLAT_MAX_READ];
	u8 received[MYRON_FLAT_MAX_READ];
	u32 total;
};

/* Fully consume the blob before any I/O. The generic legacy parser accepts a
 * trailing partial header; this sysfs path must not send an incomplete set.
 */
static int myron_flat_validate_packets(struct myron_flat_set *set, bool read)
{
	u32 pos = 0, count = 0, length;
	const u8 *p;

	while (pos < set->length) {
		if (set->length - pos < 7 || ++count > MYRON_FLAT_MAX_CMDS)
			return -EINVAL;
		p = set->data + pos;
		length = ((u32)p[5] << 8) | p[6];
		if (!length || length > MYRON_FLAT_MAX_READ ||
			length > set->length - pos - 7 || p[2] > 3 ||
			(p[1] >> 6) != 0 || (p[3] & MIPI_DSI_MSG_BATCH_COMMAND))
			return -EINVAL;
		/* The MI status contract uses a one-byte DCS register read. */
		if (read && (p[0] != 0x06 || length != 1))
			return -EOPNOTSUPP;
		if (!read && p[0] != 0x05 && p[0] != 0x15 && p[0] != 0x39)
			return -EOPNOTSUPP;
		if (!read && ((p[0] == 0x05 && length != 1) ||
			(p[0] == 0x15 && length != 2)))
			return -EINVAL;
		pos += 7 + length;
	}
	set->count = count;
	return 0;
}

static int myron_flat_get_set(struct device_node *node, const char *prop,
		const char *state_prop, bool required, bool read,
		struct myron_flat_set *set)
{
	const char *state;
	int length, rc;

	set->data = of_get_property(node, prop, &length);
	if (!set->data)
		return required ? -EINVAL : 0;
	if (length <= 0)
		return -EINVAL;
	set->length = length;
	set->low_power = true; /* Same missing-state default as dsi_panel parser. */
	rc = of_property_read_string(node, state_prop, &state);
	if (!rc) {
		if (!strcmp(state, "dsi_hs_mode"))
			set->low_power = false;
		else if (strcmp(state, "dsi_lp_mode"))
			return -EINVAL;
	} else if (of_find_property(node, state_prop, NULL)) {
		return rc;
	}
	return myron_flat_validate_packets(set, read);
}

static int myron_flat_parse(struct device_node *node,
		struct myron_flat_config *cfg)
{
	u32 i;
	int rc;

	rc = myron_flat_get_set(node,
		"mi,mdss-dsi-panel-flatmode-status-offset-command",
		"mi,mdss-dsi-panel-flatmode-status-offset-command-state",
		false, false, &cfg->offset);
	if (rc)
		return rc;
	rc = myron_flat_get_set(node,
		"mi,mdss-dsi-panel-flatmode-status-command",
		"mi,mdss-dsi-panel-flatmode-status-command-state",
		true, true, &cfg->status);
	if (rc || !cfg->status.count)
		return rc ? rc : -EINVAL;
	rc = myron_flat_get_set(node,
		"mi,mdss-dsi-panel-flatmode-status-offset-end-command",
		"mi,mdss-dsi-panel-flatmode-status-offset-end-command-state",
		false, false, &cfg->end);
	if (rc)
		return rc;
	if (of_property_count_u32_elems(node,
		"mi,mdss-dsi-panel-flatmode-status-read-length") != (int)cfg->status.count)
		return -EINVAL;
	rc = of_property_read_u32_array(node,
		"mi,mdss-dsi-panel-flatmode-status-read-length",
		cfg->lengths, cfg->status.count);
	if (rc)
		return rc;
	for (i = 0; i < cfg->status.count; i++) {
		if (!cfg->lengths[i] ||
			cfg->lengths[i] > MYRON_FLAT_MAX_READ - cfg->total)
			return -EINVAL;
		cfg->total += cfg->lengths[i];
	}
	if (of_property_count_u32_elems(node,
		"mi,mdss-dsi-panel-flatmode-on-status-value") != (int)cfg->total)
		return -EINVAL;
	rc = of_property_read_u32_array(node,
		"mi,mdss-dsi-panel-flatmode-on-status-value",
		cfg->expected, cfg->total);
	if (rc)
		return rc;
	for (i = 0; i < cfg->total; i++)
		if (cfg->expected[i] > 255)
			return -EINVAL;
	return 0;
}

static void myron_flat_cmd(struct dsi_cmd_desc *cmd, const u8 *p, bool low_power)
{
	memset(cmd, 0, sizeof(*cmd));
	cmd->msg.type = p[0];
	cmd->msg.channel = p[2];
	cmd->msg.flags = p[3] | (low_power ? MIPI_DSI_MSG_USE_LPM : 0);
	cmd->msg.tx_len = ((u32)p[5] << 8) | p[6];
	cmd->msg.tx_buf = p + 7;
	cmd->post_wait_ms = p[4];
	cmd->last_command = true;
}

static int myron_flat_send(struct dsi_display *display,
		const struct myron_flat_set *set)
{
	struct dsi_cmd_desc cmd;
	u32 i, pos = 0;
	int rc;

	for (i = 0; i < set->count; i++) {
		myron_flat_cmd(&cmd, set->data + pos, set->low_power);
		rc = dsi_host_transfer_sub(&display->host, &cmd, false);
		if (rc < 0)
			return rc;
		if (cmd.post_wait_ms)
			usleep_range(cmd.post_wait_ms * 1000,
				cmd.post_wait_ms * 1000 + 10);
		pos += 7 + cmd.msg.tx_len;
	}
	return 0;
}

int myron_dsi_flatmode_check_locked(struct dsi_display *display, bool *status);
/* Caller holds display_lock via trylock, so detach cannot free display. All
 * offset/read/end commands share panel_lock; no unrelated panel commands may
 * interleave with the register-window selection. Existing RX prepare, flags,
 * error-interrupt and clock operations are used without altering their APIs.
 */
int myron_dsi_flatmode_check_locked(struct dsi_display *display, bool *status)
{
	struct myron_flat_config *cfg;
	struct dsi_cmd_desc cmd;
	struct dsi_ctrl *ctrl;
	struct sde_kms *kms;
	struct device_node *node = display->panel->panel_of_node;
	u32 i, j, pos = 0, start = 0;
	bool host_ready = false, matched = true;
	int rc, end_rc;

	*status = false;
	if (!of_find_property(node, "mi,flatmode-status-check-enabled", NULL))
		return 0;
	if (!display->drm_dev || !ddev_to_msm_kms(display->drm_dev) ||
		sde_kms_is_suspend_blocked(display->drm_dev))
		return -EBUSY;
	kms = to_sde_kms(ddev_to_msm_kms(display->drm_dev));
	cfg = kzalloc(sizeof(*cfg), GFP_KERNEL);
	if (!cfg)
		return -ENOMEM;
	rc = myron_flat_parse(node, cfg);
	if (rc)
		goto free_config;
	/* Backlight/VM paths take VM ownership before display/panel locks.
	 * Do not block while holding display_lock in the opposite order.
	 */
	if (kms->vm && !mutex_trylock(&kms->vm->vm_res_lock)) {
		rc = -EBUSY;
		goto free_config;
	}
	if (!sde_vm_owns_hw(kms)) {
		rc = -EOPNOTSUPP;
		goto unlock_vm;
	}
	dsi_panel_acquire_panel_lock(display->panel);
	if (!display->ctrl_count || display->ctrl_count > MAX_DSI_CTRLS_PER_DISPLAY ||
		display->cmd_master_idx >= display->ctrl_count) {
		rc = -EINVAL;
		goto unlock_panel;
	}
	/* The controller's RX path uses a memory-backed max-return-size packet.
	 * Never issue this optional userspace check while secure mode owns it.
	 */
	for (i = 0; i < display->ctrl_count; i++) {
		if (!display->ctrl[i].ctrl || display->ctrl[i].ctrl->secure_mode) {
			rc = -EBUSY;
			goto unlock_panel;
		}
	}
	if (!display->panel->panel_initialized ||
		atomic_read(&display->panel->esd_recovery_pending) ||
		is_sim_panel(display) || phy_pll_bypass(display)) {
		rc = -ENODEV;
		goto unlock_panel;
	}
	rc = dsi_display_ctrl_get_host_init_state(display, &host_ready);
	if (rc || !host_ready) {
		rc = rc ? rc : -EPERM;
		goto unlock_panel;
	}
	ctrl = display->ctrl[display->cmd_master_idx].ctrl;
	if (!ctrl) {
		rc = -ENODEV;
		goto unlock_panel;
	}
	rc = dsi_display_wake_up(display);
	if (rc)
		goto unlock_panel;
	/* The offset set is optional. RX still requires a command DMA buffer. */
	if (!display->tx_cmd_buf) {
		rc = dsi_host_alloc_cmd_tx_buffer(display);
		if (rc)
			goto unlock_panel;
	}
	rc = dsi_display_clk_ctrl(display->dsi_clk_handle,
		DSI_CORE_CLK | DSI_LINK_CLK, DSI_CLK_ON);
	if (rc)
		goto unlock_panel;
	rc = myron_flat_send(display, &cfg->offset);
	if (rc)
		goto end_commands;
	dsi_display_toggle_error_interrupt_status(display, false);
	for (i = 0; i < cfg->status.count; i++) {
		myron_flat_cmd(&cmd, cfg->status.data + pos, cfg->status.low_power);
		cmd.msg.flags |= MIPI_DSI_MSG_UNICAST_COMMAND;
		cmd.msg.rx_buf = cfg->received + start;
		cmd.msg.rx_len = cfg->lengths[i];
		cmd.ctrl_flags = DSI_CTRL_CMD_READ;
		dsi_display_set_cmd_tx_ctrl_flags(display, &cmd);
		rc = dsi_ctrl_transfer_prepare(ctrl, cmd.ctrl_flags);
		if (rc)
			break;
		rc = dsi_ctrl_cmd_transfer(ctrl, &cmd, false);
		dsi_ctrl_transfer_unprepare(ctrl, cmd.ctrl_flags);
		if (rc != (int)cfg->lengths[i]) {
			rc = rc < 0 ? rc : -EIO;
			break;
		}
		for (j = 0; j < cfg->lengths[i]; j++)
			if (cfg->received[start + j] != cfg->expected[start + j])
				matched = false;
		start += cfg->lengths[i];
		pos += 7 + cmd.msg.tx_len;
		rc = 0;
	}
	dsi_display_toggle_error_interrupt_status(display, true);
end_commands:
	/* Restore any DT-defined register window even after an I/O failure. */
	end_rc = myron_flat_send(display, &cfg->end);
	if (!rc)
		rc = end_rc;
	end_rc = dsi_display_clk_ctrl(display->dsi_clk_handle,
		DSI_CORE_CLK | DSI_LINK_CLK, DSI_CLK_OFF);
	if (!rc)
		rc = end_rc;
	if (!rc)
		*status = matched;
unlock_panel:
	dsi_panel_release_panel_lock(display->panel);
unlock_vm:
	if (kms->vm)
		mutex_unlock(&kms->vm->vm_res_lock);
free_config:
	kfree(cfg);
	return rc;
}
#endif
