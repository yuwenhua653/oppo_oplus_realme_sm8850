#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>

#define GFP_KERNEL 0
#define STATEGY_CHARGE_VBUS_5V 5000
#define STRATEGY_FUNC_TYPE_BUCK_CHARGE 3
#define MCA_EVENT_TYPE_THERMAL_TEMP 4
#define MCA_EVENT_TYPE_PANEL 5
#define MAIN_BUCK_CHARGER 0
#define MCA_EVENT_TYPE_CHARGER_CONNECT 6
#define MCA_EVENT_USB_CONNECT 7
#define mca_log_info(...) ((void)0)
#define mca_log_err(...) ((void)0)

struct device { int unused; };
struct platform_device { struct device dev; };
struct notifier_block { int notifier_call; };
struct strategy_buckchg_dev {
	struct device *dev;
	void *input_voltage_voter, *charge_limit_voter;
	int chg_batt_auth_failed;
	struct { int voltage; } proc_data;
	int hvdcp_allow_flag, vbat_ov_count, strategy_init_done;
	int monitor_work, sw_cv_work, base_flip_sw_cv_work, wls_revchg_monitor_work;
	int csd_pulse_process_work, source_status_monitor_work, check_pd_secret_work;
	int rerun_handle_pd_auth_work, soc_limit_stepper_work;
	struct notifier_block thermal_board_nb, panel_nb;
};
static struct strategy_buckchg_dev *g_buckchg_info;
static struct { void *data; } g_strategy_buckchg_if_ops, g_buck_smartchg_if_ops;
static int alloc_fail, voter_result, getter_result, getter_writes, getter_value;
static int getter_calls, connect_events, registrations, vote_calls, work_inits;
static void *allocation;

static void *devm_kzalloc(struct device *dev, size_t size, int flags)
{
	(void)dev; (void)flags;
	allocation = alloc_fail ? NULL : calloc(1, size);
	return allocation;
}
static void strategy_buckchg_parse_dt(struct strategy_buckchg_dev *info) { (void)info; }
static int strategy_buckchg_init_voter(struct strategy_buckchg_dev *info) { (void)info; return voter_result; }
static int mca_vote(void *voter, const char *name, bool enabled, int val)
{
	(void)voter; (void)name; (void)enabled; (void)val;
	vote_calls++;
	return 0;
}
#define INIT_DELAYED_WORK(ptr, fn) ((void)(ptr), work_inits++)
#define mca_strategy_ops_register(...) (registrations++, 0)
#define mca_charge_if_ops_register(...) (registrations++, 0)
#define mca_smartchg_if_ops_register(...) (registrations++, 0)
#define mca_event_block_notify_register(...) (registrations++, 0)
#define strategy_buckchg_thermal_notifier_cb 1
#define strategy_buckchg_panel_notifier_cb 2
static int platform_class_buckchg_ops_get_online(int role, int *online)
{
	(void)role;
	getter_calls++;
	if (getter_writes)
		*online = getter_value;
	return getter_result;
}
static void mca_event_block_notify(int type, int event, void *data)
{
	(void)data;
	if (type != MCA_EVENT_TYPE_CHARGER_CONNECT || event != MCA_EVENT_USB_CONNECT)
		abort();
	connect_events++;
}

/* The test runner inserts the entire unmodified production probe function. */
/* PRODUCTION_FUNCTIONS */

static void require(int condition, const char *name)
{
	if (!condition) {
		fprintf(stderr, "FAIL probe: %s (read_rc=%d writes=%d value=%d events=%d)\n",
			name, getter_result, getter_writes, getter_value, connect_events);
		exit(1);
	}
}

static void run_case(const char *name, int read_rc, int writes, int value, int expected_events)
{
	struct platform_device device = {0};
	getter_result = read_rc; getter_writes = writes; getter_value = value;
	getter_calls = connect_events = registrations = vote_calls = work_inits = 0;
	int ret = strategy_buckchg_class_probe(&device);
	require(ret == 0, "read failure must not introduce a new late probe failure");
	require(getter_calls == 1 && connect_events == expected_events, name);
	require(registrations == 5 && vote_calls == 2 && work_inits == 9, "existing initialization and registrations retained");
	require(g_buckchg_info && g_buckchg_info->strategy_init_done == 1, "successful initialization still completes");
	free(allocation); allocation = NULL; g_buckchg_info = NULL;
}

int main(void)
{
	const int errors[] = {-EIO, -ENODEV, -ETIMEDOUT, -EOPNOTSUPP};
	run_case("successful offline read", 0, 1, 0, 0);
	run_case("successful online read", 0, 1, 1, 1);
	for (size_t i = 0; i < sizeof(errors) / sizeof(errors[0]); i++) {
		run_case("failed read writes online=true: no fake connect", errors[i], 1, 1, 0);
		run_case("failed read leaves output untouched: no fake connect", errors[i], 0, 0, 0);
	}
	struct platform_device device = {0};
	connect_events = 0; alloc_fail = 1;
	require(strategy_buckchg_class_probe(&device) == -ENOMEM && !connect_events, "allocation failure emits no connect");
	alloc_fail = 0; voter_result = -EIO;
	require(strategy_buckchg_class_probe(&device) == -1 && !connect_events, "voter setup failure emits no connect");
	free(allocation);
	printf("PASS probe: 12 cases; real probe read/early failures emit no fake connect; late lifecycle unchanged\n");
	return 0;
}
