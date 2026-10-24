#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <linux/slab.h>
#include <linux/notifier.h>
#include <linux/string.h>
#include <linux/swab.h>
#include <linux/spinlock.h>
#include <linux/moduleparam.h>
#include <linux/mm.h>

#include <mca/common/mca_log.h>
#include <mca/common/mca_event.h>
#include <mca/common/mca_adsp_glink.h>
#include <mca/protocol/protocol_class.h>
#include <mca/protocol/protocol_pd_class.h>

#ifndef MCA_LOG_TAG
#define MCA_LOG_TAG "qcom_adsp_pd"
#endif

/* Myron stock qcom_adsp_pd_protocol.ko: keep-PDO occupies 0x2100b. */
enum adsp_pd_prop {
	PD_PROP_USB_REAL_TYPE = 0x2000c,
	PD_PROP_VERIFY_PROCESS = 0x21002,
	PD_PROP_VDM_VERSION = 0x21003,
	PD_PROP_VDM_VOLTAGE = 0x21004,
	PD_PROP_VDM_TEMP = 0x21005,
	PD_PROP_VDM_SESSION_SEED = 0x21006,
	PD_PROP_VDM_AUTH = 0x21007,
	PD_PROP_VDM_VERIFIED = 0x21008,
	PD_PROP_VDM_REMOVE_COMP = 0x21009,
	PD_PROP_VDM_REVERSE_AUTH = 0x2100a,
	PD_PROP_SUPPORT_KEEP_PDO = 0x2100b,
	PD_PROP_VDM_NAK = 0x2100c,
	PD_PROP_DATA_ROLE = 0x2100d,
	PD_PROP_CURRENT_STATE = 0x2100e,
	PD_PROP_ADAPTER_ID = 0x2100f,
	PD_PROP_ADAPTER_SVID = 0x21010,
	PD_PROP_PD_VERIFIED = 0x21011,
	PD_PROP_PDOS = 0x21012,
	PD_PROP_VDM_STATE = 0x21013,
	PD_PROP_PPS_MAX_CUR = 0x21014,
	PD_PROP_PPS_APDO_MAX = 0x21015,
	PD_PROP_TYPEC_MODE = 0x21016,
	PD_PROP_TYPEC_CC_ORIENT = 0x21017,
	PD_PROP_SELECT_PPS_PDO = 0x21018,
	PD_PROP_FIXED_PD_VOLT = 0x21019,
	PD_PROP_PPS_STATUS = 0x2101a,
	PD_PROP_PPS_MAX_POWER = 0x2101c,
	PD_PROP_HAS_DP = 0x2101f,
	PD_PROP_CID_STATUS = 0x21020,
	PD_PROP_OTG_PLUGIN = 0x21021,
	PD_PROP_CC_TOGGLE = 0x21022,
	PD_PROP_SNK_SRC_MODE = 0x21023,
	PD_PROP_CC_STATUS = 0x21024,
	PD_PROP_CC_SHORT_VBUS = 0x21025,
	PD_PROP_PPS_PTF = 0x21026,
	PD_PROP_SUSPEND_SUPPORT = 0x21027,
	PD_PROP_ZIMI_CYPRESS = 0x21028,
	PD_PROP_GEAR_SHIFT = 0x21029,
};

#define ADSP_VDM_REQ_KEEP_PDO 0xfe
#define ADSP_VDM_REQ_INIT 200
#define ADSP_VDM_REQ_NAK 0xff
#define ADSP_GLINK_DOWN_CODE 0x2e
#define ADSP_REAL_TYPE_PD 0x0b
#define ADSP_PD_TYPE_PD 0x0b
#define ADSP_PD_TYPE_PD_PPS 0x0c

struct adsp_pd_protocol {
	struct device *dev;
	int pd_active;
	int pd_verifed;
	struct notifier_block event_nb;
	struct notifier_block abnormal_nb;
	int verify_process;
	int support_keep_pdo;
	spinlock_t state_lock;
	unsigned int state_epoch;
};

/* Cached metadata only: reading provider_status never performs GLINK I/O. */
struct adsp_pd_status {
	unsigned int registered;
	unsigned int reads;
	unsigned int writes;
	unsigned int errors;
	unsigned int last_prop;
	int last_write;
	int last_errno;
	int last_real_type;
	int last_pd_type;
	int pdo_count;
	int pdo_errno;
	unsigned int select_mv;
	unsigned int select_ma;
	int select_errno;
};

static DEFINE_SPINLOCK(adsp_pd_status_lock);
static struct adsp_pd_status adsp_pd_status;

static void adsp_pd_record_io(int prop, bool write, int rc)
{
	unsigned long flags;

	spin_lock_irqsave(&adsp_pd_status_lock, flags);
	if (write)
		adsp_pd_status.writes++;
	else
		adsp_pd_status.reads++;
	if (rc)
		adsp_pd_status.errors++;
	adsp_pd_status.last_prop = prop;
	adsp_pd_status.last_write = write;
	adsp_pd_status.last_errno = rc;
	spin_unlock_irqrestore(&adsp_pd_status_lock, flags);
}

static int adsp_pd_read_prop(int prop, void *buf, size_t size)
{
	int rc = mca_adsp_glink_read_prop(prop, buf, size);

	adsp_pd_record_io(prop, false, rc);
	return rc;
}

static int adsp_pd_write_prop(int prop, void *buf, size_t size)
{
	int rc = mca_adsp_glink_write_prop(prop, buf, size);

	adsp_pd_record_io(prop, true, rc);
	return rc;
}

static int adsp_pd_status_get(char *buf, const struct kernel_param *kp)
{
	struct adsp_pd_status status;
	unsigned long flags;

	spin_lock_irqsave(&adsp_pd_status_lock, flags);
	status = adsp_pd_status;
	spin_unlock_irqrestore(&adsp_pd_status_lock, flags);
	return scnprintf(buf, PAGE_SIZE,
		"registered=%u reads=%u writes=%u errors=%u last_prop=0x%x "
		"last_write=%d last_errno=%d last_real_type=%d last_pd_type=%d "
		"pdo_count=%d pdo_errno=%d select_mv=%u select_ma=%u select_errno=%d\n",
		status.registered, status.reads, status.writes, status.errors,
		status.last_prop, status.last_write, status.last_errno,
		status.last_real_type, status.last_pd_type, status.pdo_count,
		status.pdo_errno, status.select_mv, status.select_ma,
		status.select_errno);
}

static const struct kernel_param_ops adsp_pd_status_ops = {
	.get = adsp_pd_status_get,
};
module_param_cb(provider_status, &adsp_pd_status_ops, NULL, 0444);
MODULE_PARM_DESC(provider_status, "Cached PD provider metadata; no hardware access");

static int adsp_pd_protocol_get_pps_max_power(unsigned int *max_power,
					      void *data)
{
	return adsp_pd_write_prop(PD_PROP_PPS_MAX_POWER, max_power,
					 sizeof(*max_power));
}

static int adsp_pd_protocol_select_pps_pdo(unsigned int volt, unsigned int curr, void *data)
{
	u32 val;
	int rc;
	unsigned long flags;

	mca_log_info("vbus_mv: %u, ibus_ma: %u\n", volt, curr);
	val = (curr / 50) | ((volt / 20) << 16);
	rc = adsp_pd_write_prop(PD_PROP_SELECT_PPS_PDO, &val, sizeof(val));
	spin_lock_irqsave(&adsp_pd_status_lock, flags);
	adsp_pd_status.select_mv = volt;
	adsp_pd_status.select_ma = curr;
	adsp_pd_status.select_errno = rc;
	spin_unlock_irqrestore(&adsp_pd_status_lock, flags);
	return rc;
}

static int adsp_pd_protocol_get_pps_ptf(int *pps_ptf, void *data)
{
	return adsp_pd_read_prop(PD_PROP_PPS_PTF, pps_ptf,
					sizeof(*pps_ptf));
}

static int adsp_pd_protocol_set_fixed_pd_volt(unsigned int volt, void *data)
{
	struct adsp_pd_protocol *pd = data;
	int val = volt;

	mca_log_info("vbus_mv: %u\n", volt);
	if (READ_ONCE(pd->verify_process)) {
		mca_log_err("pd verify processing, won't set fixed pd volt\n");
		return 0;
	}
	return adsp_pd_write_prop(PD_PROP_FIXED_PD_VOLT, &val,
					 sizeof(val));
}

static int adsp_pd_protocol_set_gear_shift(int gear_shift, void *data)
{
	int val = gear_shift;

	return adsp_pd_write_prop(PD_PROP_GEAR_SHIFT, &val, sizeof(val));
}

static int adsp_pd_protocol_get_pps_max_cur(unsigned int *curr, void *data)
{
	return adsp_pd_read_prop(PD_PROP_PPS_MAX_CUR, curr,
					sizeof(*curr));
}

static int adsp_pd_protocol_get_pps_status(unsigned int *volt, unsigned int *curr, void *data)
{
	u32 val = 0;
	int ret;

	ret = adsp_pd_read_prop(PD_PROP_PPS_STATUS, &val, sizeof(val));
	if (ret == 0) {
		*curr = (val & 0xffff) * 50;
		*volt = (val >> 16) * 20;
	}
	return ret;
}

static int adsp_pd_protocol_get_pps_apdo_max(unsigned int *apdo_max, void *data)
{
	return adsp_pd_read_prop(PD_PROP_PPS_APDO_MAX, apdo_max,
					sizeof(*apdo_max));
}

static int adsp_pd_protocol_get_pdos(struct pd_pdo *pdos, int count, void *data)
{
	int ret, i;
	unsigned long flags;

	if (!pdos || count <= 0 || count > PROTOCOL_PD_MAX_PDO_NUMS)
		return -EINVAL;
	ret = adsp_pd_read_prop(PD_PROP_PDOS, pdos,
				       count * sizeof(struct pd_pdo));
	spin_lock_irqsave(&adsp_pd_status_lock, flags);
	adsp_pd_status.pdo_count = count;
	adsp_pd_status.pdo_errno = ret;
	spin_unlock_irqrestore(&adsp_pd_status_lock, flags);
	if (count > 0 && ret == 0) {
		for (i = 0; i < count; i++)
			mca_log_info(
				"pdo[%d] min_volt: %d, max_volt: %d, max_current: %d\n",
				i, pdos[i].min_volt, pdos[i].max_volt,
				pdos[i].max_current);
	}
	return ret;
}

static int adsp_pd_protocol_set_pd_active(int pd_active, void *data)
{
	struct adsp_pd_protocol *pd = data;

	if (!pd)
		return -1;
	WRITE_ONCE(pd->pd_active, pd_active);
	return 0;
}

static int adsp_pd_protocol_get_pd_active(int *pd_active, void *data)
{
	struct adsp_pd_protocol *pd = data;

	if (!pd)
		return -1;
	*pd_active = READ_ONCE(pd->pd_active);
	return 0;
}

static int adsp_pd_protocol_get_pd_type(int *type, void *data)
{
	struct adsp_pd_protocol *pd = data;
	int real_type = 0;
	int ret;
	unsigned long flags;

	if (!pd)
		return -1;

	ret = adsp_pd_read_prop(PD_PROP_USB_REAL_TYPE, &real_type,
				       sizeof(real_type));
	if (ret == 0) {
		if (real_type == ADSP_REAL_TYPE_PD)
			*type = READ_ONCE(pd->pd_verifed) ? ADSP_PD_TYPE_PD_PPS :
						 ADSP_PD_TYPE_PD;
		else
			*type = 0;
		spin_lock_irqsave(&adsp_pd_status_lock, flags);
		adsp_pd_status.last_real_type = real_type;
		adsp_pd_status.last_pd_type = *type;
		spin_unlock_irqrestore(&adsp_pd_status_lock, flags);
	}
	return ret;
}

static int adsp_pd_protocol_set_verify_process(int verify_process, void *data)
{
	struct adsp_pd_protocol *pd = data;
	int val = verify_process;

	WRITE_ONCE(pd->verify_process, verify_process);
	mca_log_err("verify_process: %d\n", verify_process);
	return adsp_pd_write_prop(PD_PROP_VERIFY_PROCESS, &val,
					 sizeof(val));
}

static int adsp_pd_protocol_get_verify_process(int *verify_process, void *data)
{
	return adsp_pd_read_prop(PD_PROP_VERIFY_PROCESS, verify_process,
					sizeof(*verify_process));
}

static int adsp_pd_protocol_set_pd_verifed(int pd_verifed, void *data)
{
	struct adsp_pd_protocol *pd = data;
	int val = pd_verifed;
	int keep_pdo = 0;
	int rc;
	unsigned long flags;
	unsigned int epoch;

	spin_lock_irqsave(&pd->state_lock, flags);
	epoch = pd->state_epoch;
	spin_unlock_irqrestore(&pd->state_lock, flags);
	mca_log_err("set pd_verifed: %d\n", pd_verifed);
	rc = adsp_pd_write_prop(PD_PROP_PD_VERIFIED, &val, sizeof(val));
	if (rc)
		return rc;
	spin_lock_irqsave(&pd->state_lock, flags);
	if (epoch != pd->state_epoch) {
		spin_unlock_irqrestore(&pd->state_lock, flags);
		return -ENOTCONN;
	}
	WRITE_ONCE(pd->pd_verifed, pd_verifed);
	WRITE_ONCE(pd->support_keep_pdo, 0);
	spin_unlock_irqrestore(&pd->state_lock, flags);
	/* Stock reads this capability after the verified-state write. */
	rc = adsp_pd_read_prop(PD_PROP_SUPPORT_KEEP_PDO, &keep_pdo,
			       sizeof(keep_pdo));
	spin_lock_irqsave(&pd->state_lock, flags);
	if (epoch != pd->state_epoch) {
		spin_unlock_irqrestore(&pd->state_lock, flags);
		return -ENOTCONN;
	}
	WRITE_ONCE(pd->support_keep_pdo, rc ? 0 : keep_pdo);
	spin_unlock_irqrestore(&pd->state_lock, flags);
	return rc;
}

static int adsp_pd_protocol_get_support_keep_pdo(int *support, void *data)
{
	struct adsp_pd_protocol *pd = data;

	*support = READ_ONCE(pd->support_keep_pdo);
	return 0;
}

static int adsp_pd_protocol_get_pd_verifed(int *pd_verifed, void *data)
{
	struct adsp_pd_protocol *pd = data;

	mca_log_info("get verifed %d\n", READ_ONCE(pd->pd_verifed));
	*pd_verifed = READ_ONCE(pd->pd_verifed);
	return 0;
}

static int adsp_pd_protocol_get_typec_mode(int *typec_mode, void *data)
{
	return adsp_pd_read_prop(PD_PROP_TYPEC_MODE, typec_mode,
					sizeof(*typec_mode));
}

static int adsp_pd_protocol_get_typec_cc_orientation(int *cc_orientation,
						     void *data)
{
	return adsp_pd_read_prop(PD_PROP_TYPEC_CC_ORIENT, cc_orientation,
					sizeof(*cc_orientation));
}

static int adsp_pd_protocol_get_adapter_id(unsigned int *adapter_id, void *data)
{
	return adsp_pd_read_prop(PD_PROP_ADAPTER_ID, adapter_id,
					sizeof(*adapter_id));
}

static int adsp_pd_protocol_get_adapter_svid(unsigned int *adapter_svid,
					     void *data)
{
	return adsp_pd_read_prop(PD_PROP_ADAPTER_SVID, adapter_svid,
					sizeof(*adapter_svid));
}

static int adsp_pd_protocol_get_has_dp(bool *has_dp, void *data)
{
	return adsp_pd_read_prop(PD_PROP_HAS_DP, has_dp,
					sizeof(*has_dp));
}

static int adsp_pd_protocol_get_data_role(unsigned char *pr, void *data)
{
	u32 val = 1;
	int ret;

	ret = adsp_pd_read_prop(PD_PROP_DATA_ROLE, &val, sizeof(val));
	*pr = (unsigned char)val;
	mca_log_info("get data_role: %d\n", val & 0xff);
	return ret;
}

static int adsp_pd_protocol_get_current_state(char *current_state, int len,
					      void *data)
{
	int state = 0;
	int ret;

	if (len < 0x40)
		return -1;

	ret = adsp_pd_read_prop(PD_PROP_CURRENT_STATE, &state,
				       sizeof(state));
	if (ret != 0)
		return ret;

	switch (state) {
	case 0:
		strscpy(current_state, "SRC_Ready", sizeof("SRC_Ready"));
		break;
	case 1:
		strscpy(current_state, "SNK_STARTUP", sizeof("SNK_STARTUP"));
		break;
	case 2:
		strscpy(current_state, "SNK_Ready", sizeof("SNK_Ready"));
		break;
	default:
		strscpy(current_state, "UNKNOWN", sizeof("UNKNOWN"));
		break;
	}
	mca_log_info("get current_state: %u => %s\n", state, current_state);
	return 0;
}

static void adsp_pd_vdm_bswap4(u32 *d)
{
	d[0] = swab32(d[0]);
	d[1] = swab32(d[1]);
	d[2] = swab32(d[2]);
	d[3] = swab32(d[3]);
}

static int adsp_pd_protocol_request_vdm_cmd(enum uvdm_state cmd,
					    unsigned int *vdm_data,
					    unsigned int data_len, void *data)
{
	int prop;

	if (!vdm_data)
		return -1;

	mca_log_info("data_len=%u, cmd=%d\n", data_len, cmd);

	switch (cmd) {
	case USBPD_UVDM_CHARGER_VERSION:
		prop = PD_PROP_VDM_VERSION;
		break;
	case USBPD_UVDM_CHARGER_VOLTAGE:
		prop = PD_PROP_VDM_VOLTAGE;
		break;
	case USBPD_UVDM_CHARGER_TEMP:
		prop = PD_PROP_VDM_TEMP;
		break;
	case USBPD_UVDM_SESSION_SEED:
		if (data_len < 4 * sizeof(*vdm_data))
			return -EINVAL;
		adsp_pd_vdm_bswap4(vdm_data);
		prop = PD_PROP_VDM_SESSION_SEED;
		break;
	case USBPD_UVDM_AUTHENTICATION:
		if (data_len < 4 * sizeof(*vdm_data))
			return -EINVAL;
		adsp_pd_vdm_bswap4(vdm_data);
		prop = PD_PROP_VDM_AUTH;
		break;
	case USBPD_UVDM_VERIFIED:
		prop = PD_PROP_VDM_VERIFIED;
		break;
	case USBPD_UVDM_REMOVE_COMPENSATION:
		prop = PD_PROP_VDM_REMOVE_COMP;
		break;
	case USBPD_UVDM_REVERSE_AUTHEN:
		if (data_len < 4 * sizeof(*vdm_data))
			return -EINVAL;
		adsp_pd_vdm_bswap4(vdm_data);
		prop = PD_PROP_VDM_REVERSE_AUTH;
		break;
	default:
		if (cmd == ADSP_VDM_REQ_INIT)
			prop = PD_PROP_DATA_ROLE;
		else if (cmd == ADSP_VDM_REQ_NAK)
			prop = PD_PROP_VDM_NAK;
		else if (cmd == ADSP_VDM_REQ_KEEP_PDO)
			prop = PD_PROP_SUPPORT_KEEP_PDO;
		else {
			pr_info("cmd:%d is not support\n", cmd);
			return -EINVAL;
		}
		break;
	}

	return adsp_pd_write_prop(prop, vdm_data, data_len);
}

static int adsp_pd_protocol_get_vdm_cmd(int *cmd,
					struct usbpd_vdm_data *vdm_data,
					void *data)
{
	int ret;

	if (!vdm_data)
		return -1;

	ret = adsp_pd_read_prop(PD_PROP_VDM_STATE, cmd, sizeof(*cmd));
	if (ret != 0)
		return ret;

	mca_log_info("current uvdm_state: %d\n", *cmd);

	switch (*cmd) {
	case USBPD_UVDM_CHARGER_VERSION:
		return adsp_pd_read_prop(PD_PROP_VDM_VERSION,
						&vdm_data->ta_version,
						sizeof(vdm_data->ta_version));
	case USBPD_UVDM_CHARGER_VOLTAGE:
		return adsp_pd_read_prop(PD_PROP_VDM_VOLTAGE,
						&vdm_data->ta_voltage,
						sizeof(vdm_data->ta_voltage));
	case USBPD_UVDM_CHARGER_TEMP:
		return adsp_pd_read_prop(PD_PROP_VDM_TEMP,
						&vdm_data->ta_temp,
						sizeof(vdm_data->ta_temp));
	case USBPD_UVDM_AUTHENTICATION: {
		u32 buf[4] = { 0 };

		ret = adsp_pd_read_prop(PD_PROP_VDM_AUTH, buf,
					       sizeof(buf));
		if (ret)
			return ret;
		vdm_data->s_secert[4] = buf[0];
		vdm_data->s_secert[5] = buf[1];
		vdm_data->s_secert[6] = buf[2];
		vdm_data->s_secert[7] = buf[3];
		mca_log_info("authentication response received\n");
		return ret;
	}
	default:
		return ret;
	}
}

static int adsp_pd_protocol_get_cid_status(bool *status, void *data)
{
	return adsp_pd_read_prop(PD_PROP_CID_STATUS, status,
					sizeof(*status));
}

static int adsp_pd_protocol_get_otg_plugin_status(bool *status, void *data)
{
	return adsp_pd_read_prop(PD_PROP_OTG_PLUGIN, status,
					sizeof(*status));
}

static int adsp_protocol_set_cc_toggle(bool en, void *data)
{
	u8 val = en;

	mca_log_info("set cc toggle: 0x%2x\n", en & 1);
	return adsp_pd_write_prop(PD_PROP_CC_TOGGLE, &val, sizeof(val));
}

static int adsp_protocol_get_cc_toggle(bool *en, void *data)
{
	return adsp_pd_read_prop(PD_PROP_CC_TOGGLE, en, sizeof(*en));
}

static int adsp_pd_protocol_get_snk_src_mode(int *snk_src_mode, void *data)
{
	return adsp_pd_read_prop(PD_PROP_SNK_SRC_MODE, snk_src_mode,
					sizeof(*snk_src_mode));
}

static int adsp_protocol_get_cc_status(bool *status, void *data)
{
	return adsp_pd_read_prop(PD_PROP_CC_STATUS, status,
					sizeof(*status));
}

static int adsp_protocol_get_cc_short_vbus(int *cc_short_vbus, void *data)
{
	return adsp_pd_read_prop(PD_PROP_CC_SHORT_VBUS, cc_short_vbus,
					sizeof(*cc_short_vbus));
}

static int adsp_pd_protocol_get_suspend_support_status(bool *pdsuspendsupported,
						       void *data)
{
	return adsp_pd_read_prop(PD_PROP_SUSPEND_SUPPORT,
					pdsuspendsupported,
					sizeof(*pdsuspendsupported));
}

static int adsp_pd_protocol_get_zimi_cypress_flag(int *zimi_cypress_flag,
						  void *data)
{
	return adsp_pd_read_prop(PD_PROP_ZIMI_CYPRESS, zimi_cypress_flag,
					sizeof(*zimi_cypress_flag));
}

static struct protocol_class_pd_ops g_adsp_pd_ops = {
	.protocol_pd_pps_get_max_power = adsp_pd_protocol_get_pps_max_power,
	.protocol_pd_pps_pdo_select = adsp_pd_protocol_select_pps_pdo,
	.protocol_pd_get_pps_ptf = adsp_pd_protocol_get_pps_ptf,
	.protocol_pd_fixed_pdo_set_vol = adsp_pd_protocol_set_fixed_pd_volt,
	.protocol_pd_set_gear_shift = adsp_pd_protocol_set_gear_shift,
	.protocol_pd_get_pps_max_cur = adsp_pd_protocol_get_pps_max_cur,
	.protocol_pd_get_pps_status = adsp_pd_protocol_get_pps_status,
	.protocol_pd_set_pd_active = adsp_pd_protocol_set_pd_active,
	.protocol_pd_get_pd_active = adsp_pd_protocol_get_pd_active,
	.protocol_pd_get_pps_apdo_max = adsp_pd_protocol_get_pps_apdo_max,
	.protocol_pd_get_pd_type = adsp_pd_protocol_get_pd_type,
	.protocol_pd_get_typec_mode = adsp_pd_protocol_get_typec_mode,
	.protocol_pd_get_typec_cc_orientation =
		adsp_pd_protocol_get_typec_cc_orientation,
	.protocol_pd_get_adapter_id = adsp_pd_protocol_get_adapter_id,
	.protocol_pd_get_adapter_svid = adsp_pd_protocol_get_adapter_svid,
	.protocol_pd_request_vdm_cmd = adsp_pd_protocol_request_vdm_cmd,
	.protocol_pd_get_vdm_cmd = adsp_pd_protocol_get_vdm_cmd,
	.protocol_pd_get_data_role = adsp_pd_protocol_get_data_role,
	.protocol_pd_get_current_state = adsp_pd_protocol_get_current_state,
	.protocol_pd_get_pdos = adsp_pd_protocol_get_pdos,
	.protocol_pd_set_verify_process = adsp_pd_protocol_set_verify_process,
	.protocol_pd_get_verify_process = adsp_pd_protocol_get_verify_process,
	.protocol_pd_set_pd_verifed = adsp_pd_protocol_set_pd_verifed,
	.protocol_pd_get_pd_verifed = adsp_pd_protocol_get_pd_verifed,
	.protocol_pd_get_has_dp = adsp_pd_protocol_get_has_dp,
	.protocol_pd_get_cid_status = adsp_pd_protocol_get_cid_status,
	.protocol_pd_get_otg_plugin_status =
		adsp_pd_protocol_get_otg_plugin_status,
	.protocol_pd_set_cc_toggle = adsp_protocol_set_cc_toggle,
	.protocol_pd_get_cc_toggle = adsp_protocol_get_cc_toggle,
	.protocol_pd_get_snk_src_mode = adsp_pd_protocol_get_snk_src_mode,
	.protocol_pd_get_cc_status = adsp_protocol_get_cc_status,
	.protocol_pd_get_cc_short_vbus = adsp_protocol_get_cc_short_vbus,
	.protocol_pd_get_suspend_support_status =
		adsp_pd_protocol_get_suspend_support_status,
	.protocol_pd_get_zimi_cypress_flag =
		adsp_pd_protocol_get_zimi_cypress_flag,
	.protocol_pd_get_support_keep_pdo = adsp_pd_protocol_get_support_keep_pdo,
};

static int adsp_pd_protocol_event_cb(struct notifier_block *nb,
				     unsigned long action, void *data)
{
	struct adsp_pd_protocol *pd =
		container_of(nb, struct adsp_pd_protocol, event_nb);
	unsigned long flags;

	if (action != MCA_EVENT_USB_DISCONNECT)
		return 0;

	spin_lock_irqsave(&pd->state_lock, flags);
	pd->state_epoch++;
	WRITE_ONCE(pd->pd_verifed, 0);
	WRITE_ONCE(pd->verify_process, 0);
	WRITE_ONCE(pd->support_keep_pdo, 0);
	spin_unlock_irqrestore(&pd->state_lock, flags);
	return 0;
}

static int adsp_pd_protocol_abnormal_cb(struct notifier_block *nb,
					unsigned long action, void *data)
{
	struct adsp_pd_protocol *pd =
		container_of(nb, struct adsp_pd_protocol, abnormal_nb);
	unsigned long flags;

	if (action == ADSP_GLINK_DOWN_CODE) {
		spin_lock_irqsave(&pd->state_lock, flags);
		pd->state_epoch++;
		WRITE_ONCE(pd->pd_verifed, 0);
		WRITE_ONCE(pd->support_keep_pdo, 0);
		spin_unlock_irqrestore(&pd->state_lock, flags);
	}
	return 0;
}

static int adsp_pd_protocol_probe(struct platform_device *pdev)
{
	struct adsp_pd_protocol *pd;
	unsigned long flags;
	int rc;

	pd = devm_kzalloc(&pdev->dev, sizeof(*pd), GFP_KERNEL);
	if (!pd)
		return -ENOMEM;

	pd->dev = &pdev->dev;
	spin_lock_init(&pd->state_lock);
	platform_set_drvdata(pdev, pd);
	pd->event_nb.notifier_call = adsp_pd_protocol_event_cb;
	rc = mca_event_block_notify_register(MCA_EVENT_TYPE_CHARGER_CONNECT,
					    &pd->event_nb);
	if (rc)
		return rc;
	pd->abnormal_nb.notifier_call = adsp_pd_protocol_abnormal_cb;
	rc = mca_event_block_notify_register(MCA_EVENT_CHARGE_STATUS,
					    &pd->abnormal_nb);
	if (rc)
		goto unregister_event;

	/* Publish callbacks only after both event listeners are ready. */
	rc = protocol_class_pd_register_ops(0, &g_adsp_pd_ops, pd);
	if (rc)
		goto unregister_abnormal;

	spin_lock_irqsave(&adsp_pd_status_lock, flags);
	adsp_pd_status.registered = 1;
	spin_unlock_irqrestore(&adsp_pd_status_lock, flags);
	mca_log_err("probe ok\n");
	return 0;

unregister_abnormal:
	mca_event_block_notify_unregister(MCA_EVENT_CHARGE_STATUS,
					  &pd->abnormal_nb);
unregister_event:
	mca_event_block_notify_unregister(MCA_EVENT_TYPE_CHARGER_CONNECT,
					  &pd->event_nb);
	return rc;
}

static void adsp_pd_protocol_remove(struct platform_device *pdev)
{
	struct adsp_pd_protocol *pd = platform_get_drvdata(pdev);
	unsigned long flags;

	/* The class waits for in-flight SRCU callbacks before freeing pd. */
	protocol_class_pd_unregister_ops(0, &g_adsp_pd_ops, pd);
	mca_event_block_notify_unregister(MCA_EVENT_CHARGE_STATUS,
					  &pd->abnormal_nb);
	mca_event_block_notify_unregister(MCA_EVENT_TYPE_CHARGER_CONNECT,
					  &pd->event_nb);
	spin_lock_irqsave(&adsp_pd_status_lock, flags);
	adsp_pd_status.registered = 0;
	spin_unlock_irqrestore(&adsp_pd_status_lock, flags);
}

static void adsp_pd_protocol_shutdown(struct platform_device *pdev)
{
}

static const struct of_device_id adsp_pd_protocol_match_table[] = {
	{ .compatible = "mca,adsp_pd_protocol" },
	{},
};
MODULE_DEVICE_TABLE(of, adsp_pd_protocol_match_table);

static struct platform_driver adsp_pd_protocol_driver = {
	.driver = {
		.name = "adsp_pd_protocol",
		.of_match_table = adsp_pd_protocol_match_table,
	},
	.probe = adsp_pd_protocol_probe,
	.remove = adsp_pd_protocol_remove,
	.shutdown = adsp_pd_protocol_shutdown,
};
module_platform_driver(adsp_pd_protocol_driver);

MODULE_DESCRIPTION("qcom pd protocol");
MODULE_AUTHOR("lvchen@xiaomi.com");
MODULE_LICENSE("GPL v2");
