#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

/* Values copied from the frozen production headers; no fake policy values. */
#define CP_ROLE_MASTER 0
#define MCA_QUICK_CHG_TUNE_VBUS_MAX_COUNT 15
#define MCA_QUICK_CHG_TUNE_VBUS_INTERVAL 300
#define MCA_QUICK_CHG_DEFAULT_VSTEP 20
#define MCA_QUICK_CHG_QC3B_DEFAULT_VSTEP 200
#define QC3_STEP_SIZE 200
#define CP_ENABLE_IBUS_UCP_RISING_MA 250
#define XM_CHARGER_TYPE_HVDCP3_B 7
#define BUS_VOLTAGE_MIN 3000
#define MCA_QUICK_CHG_TUNE_VBUS_WINDOW_MV 1500
#define MCA_QC_QUICK_CHG_OPEN_PATH_COUNT 40
#define CP_PMID_ERROR_OK 0
#define CP_PMID_ERROR_LOW 1
#define CP_PMID_ERROR_HIGH 2
#define TYPEC_PORT_0 0
#define QC2_FORCE_5V 0
enum VBUS_TUNE_STAT { XM_VBUS_TUNE_INIT, XM_VBUS_TUNE_VBUS_LOW,
    XM_VBUS_TUNE_WAIT, XM_VBUS_TUNE_READY_UP, XM_VBUS_TUNE_READY_DOWN,
    XM_VBUS_TUNE_OK, XM_VBUS_TUNE_FAIL };
#define mca_log_info(...) ((void)0)
#define mca_log_err(...) ((void)0)
struct mca_quick_charge_info {
    int tune_vbus_retry;
    struct { int cur_work_cp, cur_adp_volt, cur_adp_cur, adp_type;
        int cur_protocol, ibus, error_num[3]; } proc_data;
};
enum operation { ADC, CURRENT, VOLTAGE, ERRORHL, ENABLE, ADAPTER, SLEEP, QC_RESET, OP_COUNT };
static struct { int op, a, b, c; } trace[256];
static int trace_count, calls[OP_COUNT], failing_op, failing_at, failure;
static int voltage[32], current[32], voltage_n, current_n;
static unsigned long assertions;
static const char *test_name = "full-matrix";
#define CHECK(x) do { assertions++; if (!(x)) { \
    fprintf(stderr,"FAIL %s: %s (line %d)\n",test_name,#x,__LINE__);exit(41); } } while (0)
static int record(int op, int a, int b, int c)
{
    CHECK(op >= 0 && op < OP_COUNT && trace_count < 256);
    trace[trace_count].op = op; trace[trace_count].a = a;
    trace[trace_count].b = b; trace[trace_count++].c = c;
    calls[op]++;
    return op == failing_op && calls[op] == failing_at ? failure : 0;
}
static int platform_class_cp_enable_adc(int role, bool enable)
{ return record(ADC,role,enable,0); }
static int platform_class_cp_set_charging_enable(int role, bool enable)
{ return record(ENABLE,role,enable,0); }
static int platform_class_cp_get_bus_current(int role, int *out)
{
    int ret = record(CURRENT,role,0,0), at = calls[CURRENT]-1;
    *out = ret ? -9999 : current[at < current_n ? at : current_n-1];
    return ret;
}
static int platform_class_cp_get_bus_voltage(int role, int *out)
{
    int ret = record(VOLTAGE,role,0,0), at = calls[VOLTAGE]-1;
    *out = ret ? -9999 : voltage[at < voltage_n ? at : voltage_n-1];
    return ret;
}
static int platform_class_cp_get_errorhl_stat(int role, int *out)
{ int ret=record(ERRORHL,role,0,0); if(!ret)*out=0; return ret; }
static int protocol_class_set_adapter_volt_and_curr(int protocol, int volt, int curr)
{ return record(ADAPTER,protocol,volt,curr); }
static int protocol_class_qc_set_volt_cmd(int port,int cmd)
{ return record(QC_RESET,port,cmd,0); }
static int mca_quick_charge_req_adp_volt_and_cur(struct mca_quick_charge_info *info)
{ return protocol_class_set_adapter_volt_and_curr(info->proc_data.cur_protocol,info->proc_data.cur_adp_volt,info->proc_data.cur_adp_cur); }
static int mca_quick_charge_msleep(int ms, struct mca_quick_charge_info *info)
{ (void)info; return record(SLEEP,ms,0,0); }
static void reset(struct mca_quick_charge_info *info)
{
    memset(info,0,sizeof(*info));memset(calls,0,sizeof(calls));
    memset(trace,0,sizeof(trace));trace_count=0;failing_op=-1;failing_at=1;failure=0;
    info->proc_data.cur_work_cp=0;info->proc_data.cur_adp_volt=9000;
    info->proc_data.cur_adp_cur=1700;info->proc_data.cur_protocol=3;
    info->proc_data.adp_type=12;info->proc_data.ibus=777;
    voltage_n=current_n=1;voltage[0]=8800;current[0]=100;
}
