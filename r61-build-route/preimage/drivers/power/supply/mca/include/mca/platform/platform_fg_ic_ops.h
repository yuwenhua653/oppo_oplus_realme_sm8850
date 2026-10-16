/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _MCA_PLATFORM_PLATFORM_FG_IC_OPS_H_
#define _MCA_PLATFORM_PLATFORM_FG_IC_OPS_H_
#include <linux/types.h>

enum mca_fg_ic_role {
	FG_IC_MASTER = 0,
	FG_IC_SLAVE,
	FG_IC_MAX,
};
#define FG_SITE_MAX FG_IC_MAX

/* Stock Myron ABI: 67 pointer slots (536 bytes on arm64).
 * Slot 136 is unexposed and NULL in the stock BQ27Z561 provider. Its function
 * signature is not inferred; leave the reserved slot NULL in source providers.
 * Battery info/abnormal info are opaque provider buffers, not an int value.
 */
struct fuelguage_ic_ops {
	int (*fg_ic_probe_ok)(void *data, bool *value);
	int (*fg_ic_get_batt_info)(void *data, void *value);
	int (*fg_ic_get_soc)(void *data);
	int (*fg_ic_get_rsoc)(void *data, int *value);
	int (*fg_ic_get_curr)(void *data, int *value);
	int (*fg_ic_get_volt)(void *data, int *value);
	int (*fg_ic_set_temp)(void *data, int value);
	int (*fg_ic_get_temp)(void *data, int *value);
	int (*fg_ic_get_original_temp)(void *data, int *value);
	int (*fg_ic_set_iterm)(void *data, int value);
	int (*fg_ic_get_charge_status)(void *data);
	int (*fg_ic_get_rm)(void *data, int *value);
	int (*fg_ic_get_fastcharge)(void *data, int *value);
	int (*fg_ic_set_fastcharge)(void *data, bool value);
	int (*fg_ic_get_chg_vol)(void *data, int *value);
	int (*fg_ic_get_chip_ok)(void *data, int *value);
	int (*fg_ic_get_cyclecount)(void *data, int *value);
	void *reserved_136;
	int (*fg_ic_get_tte)(void *data, int *value);
	int (*fg_ic_get_ttf)(void *data, int *value);
	int (*fg_ic_get_fcc)(void *data, int *value);
	int (*fg_ic_get_full_design)(void *data, int *value);
	int (*fg_ic_get_soh)(void *data, int *value);
	int (*fg_ic_get_temp_max)(void *data, int *value);
	int (*fg_ic_get_time_ot)(void *data, int *value);
	int (*fg_ic_get_batt_cell_info)(void *data, const char **value);
	int (*fg_ic_set_verify_digest)(void *data, char *value);
	int (*fg_ic_get_verify_digest)(void *data, char *value);
	int (*fg_ic_set_authentic)(void *data, int value);
	int (*fg_ic_get_authentic)(void *data, int *value);
	int (*fg_ic_get_error_state)(void *data, bool *value);
	int (*fg_ic_get_cutoff_voltage)(void *data, int *value);
	int (*fg_ic_set_cutoff_voltage)(void *data, int value);
	int (*fg_ic_get_dod_count)(void *data);
	int (*fg_ic_get_count_level1)(void *data, int *value);
	int (*fg_ic_get_count_level2)(void *data, int *value);
	int (*fg_ic_get_count_level3)(void *data, int *value);
	int (*fg_ic_get_vsiloss)(void *data, int *value);
	int (*fg_ic_get_iaver)(void *data, int *value);
	int (*fg_ic_get_count_lowtemp)(void *data, int *value);
	int (*fg_ic_set_clear_count_data)(void *data);
	int (*fg_ic_get_adapt_power)(void *data, int *value);
	int (*fg_ic_get_aged_flag)(void *data, int *value);
	int (*fg_ic_get_isc_alert_level)(void *data, int *value);
	int (*fg_ic_get_soa_alert_level)(void *data, int *value);
	int (*fg_ic_get_raw_soc)(void *data, int *value);
	void (*fg_ic_update_fw)(void *data);
	int (*fg_ic_get_device_name)(void *data, const char **value);
	int (*fg_ic_get_temp_min)(void *data, int *value);
	void (*fg_ic_set_force_report_full)(void *data);
	int (*fg_ic_get_fc)(void *data, bool *value);
	int (*fg_ic_set_co)(void *data, bool value);
	int (*fg_ic_get_calibration_ffc_iterm)(void *data, int *value);
	int (*fg_ic_get_real_supplement_energy)(void *data, int *value);
	int (*fg_ic_get_calibration_charge_energy)(void *data, int *value);
	void (*fg_ic_fl4p0_enable_check)(void *data);
	void (*fg_ic_get_ui_soh)(void *data, int *value);
	void (*fg_ic_get_pack_vendor)(void *data, int *value);
	unsigned long (*fg_ic_get_calc_rvalue)(void *data);
	int (*fg_ic_get_batt_sn)(void *data, char *value);
	void (*fg_ic_get_batt_abnormal_info)(void *data, void *value);
	int (*fg_ic_get_csd_flag)(void *data, int *value);
	int (*fg_ic_get_batt_qmax)(void *data, int *value);
	int (*fg_ic_get_fg_vendor)(void *data, int *value);
	int (*fg_ic_set_reboot_vol_thr)(void *data, u8 value);
	int (*fg_ic_get_fast_mode_times)(void *data, int *value);
	int (*fg_ic_set_fast_mode_times)(void *data, int value);
};

/* Sleepable context only. Do not register/unregister inside an FG callback.
 * Keep the ops table immutable and ops/data live until unregister returns.
 */
int platform_fg_ic_ops_register(unsigned int ic_role, void *data,
				struct fuelguage_ic_ops *ops);
int platform_fg_ic_ops_unregister(unsigned int ic_role, void *data,
				  struct fuelguage_ic_ops *ops);
int platform_fg_ops_probe_ok(unsigned int ic_role, bool *value);
int platform_fg_ops_get_batt_info(unsigned int ic_role, void *value);
void platform_fg_ops_get_batt_abnormal_info(unsigned int ic_role, void *value);
int platform_fg_ops_get_soc(unsigned int ic_role);
int platform_fg_ops_get_rsoc(unsigned int ic_role, int *value);
int platform_fg_ops_get_curr(unsigned int ic_role, int *value);
int platform_fg_ops_set_verify_digest(unsigned int ic_role, char *value);
int platform_fg_ops_get_verify_digest(unsigned int ic_role, char *value);
int platform_fg_ops_set_authentic(unsigned int ic_role, int value);
int platform_fg_ops_get_authentic(unsigned int ic_role, int *value);
int platform_fg_ops_get_error_state(unsigned int ic_role, bool *value);
int platform_fg_ops_get_volt(unsigned int ic_role, int *value);
int platform_fg_ops_set_temp(unsigned int ic_role, int value);
int platform_fg_ops_get_temp(unsigned int ic_role, int *value);
int platform_fg_ops_get_original_temp(unsigned int ic_role, int *value);
int platform_fg_ops_set_iterm(unsigned int ic_role, int value);
int platform_fg_ops_get_charge_status(unsigned int ic_role);
int platform_fg_ops_get_rm(unsigned int ic_role, int *value);
int platform_fg_ops_get_isc_alert_level(unsigned int ic_role, int *value);
int platform_fg_ops_get_soa_alert_level(unsigned int ic_role, int *value);
int platform_fg_ops_get_fastcharge(unsigned int ic_role, int *value);
int platform_fg_ops_set_fastcharge(unsigned int ic_role, bool value);
int platform_fg_ops_get_chg_vol(unsigned int ic_role, int *value);
int platform_fg_ops_get_chip_ok(unsigned int ic_role, int *value);
int platform_fg_ops_get_cyclecount(unsigned int ic_role, int *value);
int platform_fg_ops_get_tte(unsigned int ic_role, int *value);
int platform_fg_ops_get_ttf(unsigned int ic_role, int *value);
int platform_fg_ops_get_fcc(unsigned int ic_role, int *value);
int platform_fg_ops_get_full_design(unsigned int ic_role, int *value);
int platform_fg_ops_get_soh(unsigned int ic_role, int *value);
int platform_fg_ops_get_temp_max(unsigned int ic_role, int *value);
int platform_fg_ops_get_time_ot(unsigned int ic_role, int *value);
int platform_fg_ops_get_batt_cell_info(unsigned int ic_role, const char **value);
int platform_fg_ops_get_cutoff_voltage(unsigned int ic_role, int *value);
int platform_fg_ops_set_cutoff_voltage(unsigned int ic_role, int value);
int platform_fg_ops_get_dod_count(unsigned int ic_role);
int platform_fg_ops_get_count_level1(unsigned int ic_role, int *value);
int platform_fg_ops_get_count_level2(unsigned int ic_role, int *value);
int platform_fg_ops_get_count_level3(unsigned int ic_role, int *value);
int platform_fg_ops_get_vsiloss(unsigned int ic_role, int *value);
int platform_fg_ops_get_iaver(unsigned int ic_role, int *value);
int platform_fg_ops_get_count_lowtemp(unsigned int ic_role, int *value);
int platform_fg_ops_set_clear_count_data(unsigned int ic_role);
int platform_fg_ops_get_adapt_power(unsigned int ic_role, int *value);
int platform_fg_ops_get_aged_flag(unsigned int ic_role, int *value);
int platform_fg_ops_get_raw_soc(unsigned int ic_role, int *value);
int platform_fg_ops_get_real_supplement_energy(unsigned int ic_role, int *value);
int platform_fg_ops_get_calibration_ffc_iterm(unsigned int ic_role, int *value);
int platform_fg_ops_get_calibration_charge_energy(unsigned int ic_role, int *value);
void platform_fg_ops_fl4p0_enable_check(unsigned int ic_role);
void platform_fg_ops_update_fw(unsigned int ic_role);
int platform_fg_ops_get_device_name(unsigned int ic_role, const char **value);
int platform_fg_ops_get_temp_min(unsigned int ic_role, int *value);
void platform_fg_ops_set_force_report_full(unsigned int ic_role);
int platform_fg_ops_get_fc(unsigned int ic_role, bool *value);
int platform_fg_ops_set_co(unsigned int ic_role, bool value);
void platform_fg_ops_get_ui_soh(unsigned int ic_role, int *value);
void platform_fg_ops_get_pack_vendor(unsigned int ic_role, int *value);
unsigned long platform_fg_ops_get_calc_rvalue(unsigned int ic_role);
int platform_fg_ops_get_batt_sn(unsigned int ic_role, char *value);
int platform_fg_ops_get_csd_flag(unsigned int ic_role, int *value);
int platform_fg_ops_get_batt_qmax(unsigned int ic_role, int *value);
int platform_fg_ops_get_fg_vendor(unsigned int ic_role, int *value);
int platform_fg_ops_set_reboot_vol_thr(unsigned int ic_role, u8 value);
int platform_fg_ops_get_fast_mode_times(unsigned int ic_role, int *value);
int platform_fg_ops_set_fast_mode_times(unsigned int ic_role, int value);

#endif /* _MCA_PLATFORM_PLATFORM_FG_IC_OPS_H_ */
