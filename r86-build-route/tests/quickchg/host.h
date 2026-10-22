#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
struct work_struct { int unused; };
struct delayed_work { struct work_struct work; };
struct mutex { int depth; };
static void mutex_lock(struct mutex *m) { assert(m->depth == 0); m->depth++; }
static void mutex_unlock(struct mutex *m) { assert(m->depth == 1); m->depth--; }
#define container_of(p,t,m) ((t *)((char *)(p) - offsetof(t,m)))
#define mca_log_info(...) ((void)0)
#define mca_log_err(...) ((void)0)
#define msecs_to_jiffies(x) (x)
#define min(a,b) ((a)<(b)?(a):(b))
#define FG_IC_MASTER 0
#define FG_IC_SLAVE 1
#define MCA_FG_TYPE_SINGLE_NUM_MAX 1
#define MPC7021 5
#define FG_MAC_CMD_FASTCHARGE_EN 0x3e
#define FG_MAC_CMD_FASTCHARGE_DIS 0x3f
#define CP_ROLE_MASTER 0
#define CP_ROLE_SLAVE 1
#define MCA_CP_TYPE_PARALLEL 2
#define MCA_QUICK_CHG_STS_CHARGING 1
#define MCA_QUICK_CHG_STS_CHARGE_DONE 2
#define MCA_QUICK_CHG_CP_DEFAULT_FSW 100
#define MCA_QUICK_QC_CHG_ADP_DEFAULT_VOLT 5000
#define MCA_QUICK_CHG_VFC_INTERVAL 10
#define MCA_QUICK_CHG_FAST_INTERVAL 20
#define MCA_QUICK_CHG_PPS_PTF_INTERVAL 30
#define MCA_QUICK_CHG_BASE_CLOSE_CURR_NUM 1
#define MCA_QUICK_CHG_BASE_CLOSE_CURR_DEN 1
#define MCA_QUICK_CHG_MAX_CURR_MA 10000
#define MCA_QUICK_TEMP_HYS_DIS 0
#define MCA_QUICK_TEMP_HYS_HIGH 1
#define MCA_QUICK_TEMP_HYS_LOW 2
#define XM_CHARGER_TYPE_PPS 3
#define XM_CHARGER_TYPE_PD_VERIFY 4
#define XM_CHARGER_TYPE_HVDCP3_B 5
#define XM_CHARGER_TYPE_HVDCP3P5 6
#define ADAPTER_PROTOCOL_PPS 1
#define ADAPTER_PROTOCOL_QC 2
#define OCP_THRESHOLD_MAINT 1000
#define OCP_THRESHOLD_FLIP 2000
#define USBPD_QUICK_DPM_PORT_PPS_PTF_NOT_OVERTEMP 1
#define CountryCN 1
enum { MCA_EVENT_MASTER_BATT_CLOSE=1,MCA_EVENT_FCC_TOO_LOW,MCA_EVENT_USB_CONNECT,MCA_EVENT_USB_DISCONNECT,MCA_EVENT_BATT_AUTH_PASS,MCA_EVENT_CHARGE_TYPE_CHANGE,MCA_EVENT_CHARGE_CAP_CHANGE,MCA_EVENT_SINK_PWR_SUSPEND_CHANGE,MCA_EVENT_CONN_ANTIBURN_CHANGE,MCA_EVENT_BATT_BTB_CHANGE,MCA_EVENT_BATTERY_DTPT,MCA_EVENT_CHARGE_ABNORMAL,MCA_EVENT_LPD_STATUS_CHANGE,MCA_EVENT_WIRELESS_REVCHG,MCA_EVENT_CHARGE_ACTION,MCA_EVENT_CC_SHORT_VBUS,MCA_EVENT_VBAT_OVP_CHANGE,MCA_EVENT_IBAT_OCP_CHANGE,MCA_EVENT_CP_CBOOT_FAIL,MCA_EVENT_PPS_PTF,MCA_EVENT_IS_EU_MODEL,MCA_EVENT_PLATE_SHOCK,MCA_EVENT_CSD_SEND_PULSE };
struct mca_quick_charge_volt_para { int volt_para_size; };
struct mca_quick_charge_temp_para { int temp_low,temp_high,max_current,high_temp_hysteresis,low_temp_hysteresis,ffc_max_fv,normal_max_fv; };
struct temp_info { struct mca_quick_charge_temp_para temp_para; struct mca_quick_charge_volt_para volt_ffc_info,volt_info; };
struct mca_quick_charge_batt_para_info { int temp_para_size; struct temp_info temp_info[3]; };
struct mca_hwid { const char *product_name; int platform_version,country_version; };
struct mca_quick_charge_process_data { int adp_type,adp_mode,charge_flag,cur_adp_volt,cur_work_cp,ffc_flag,max_power,total_err,ibus,stop_charging,temp_hys_en,temp_para_index[2],temp_max_cur[2],temp_max_fv[2],zone_changed,cur_protocol,sw_ocp_curr,type_chg; struct mca_quick_charge_volt_para *cur_volt_para[2]; };
struct mca_quick_charge_info { struct mca_quick_charge_process_data proc_data; struct { bool support_cp_vfc; } vfc_para; struct delayed_work monitor_work,vfc_work,pps_ptf_work; struct mutex data_lock; struct mca_quick_charge_batt_para_info batt_para[2]; int boost_done,cp_type,cur_support_mode,is_platform_qc,pd_switch_to_pmic,curr_monitor_time_s,fastchg_temp_flag,force_normal_volt_para,init_volt_para,support_curr_monitor,base_close_curr,batt_auth,dtpt_status,fake_pps_ptf,is_eu_model,master_batt_close,online,parall_force_normal_volt_para[2],parall_init_volt_para,pps_ptf,support_base_flip,trigger_antr_burn; void *input_suspend_voter,*buck_charge_curr_voter,*chg_disable_voter,*chg_en_voter; };
struct bq_fg_chip { struct mutex data_lock; bool fast_mode,fast_mode_valid; int fg_vendor,role; };
struct strategy_fg { bool fg_init_flag; struct { int fg_type; } cfg; void *vterm_voter; };
static struct strategy_fg fg;
static struct bq_fg_chip chips[2];
static struct mca_quick_charge_info *current;
static int provider_error[2],provider_writes[2],provider_calls[2],class_calls,desired_mode;
static int open_error,judge_error,regulation_error,temperature,stop_count,regulation_count,schedule_count,monitor_schedule,vfc_schedule,vote_count,disable_count,req_count,reset_count,exit_count,sequence,reset_at,exit_at,mode_at;
static int fg_mac_write_block_locked(struct bq_fg_chip *bq,u16 cmd,u8 *data,u8 len) { int role=bq->role; assert(bq->data_lock.depth==1); assert(cmd==(data[0]?0x3e:0x3f));assert(len==2);assert(data[1]==0);provider_writes[role]++;return provider_error[role]; }
static int platform_fg_ops_set_fastcharge(unsigned role,bool en);
static int strategy_class_fg_set_fastcharge(bool en);
#define mca_is_override_vote_enabled(...) 0
#define mca_vote_override(...) ((void)0)
static int mca_vote(void *v,const char *name,bool en,int value) { (void)v;(void)name;(void)en;(void)value;vote_count++;return 0; }
static int platform_class_cp_set_charging_enable(int role,bool en) { (void)role;assert(!en);disable_count++;return 0; }
#define platform_class_cp_set_fsw(...) ((void)0)
#define platform_class_cp_enable_busucp(...) ((void)0)
#define mca_cp_check_initial_mode(...) ((void)0)
#define mca_quick_charge_select_stage(...) ((void)0)
#define mca_quick_charge_change_path(...) ((void)0)
#define mca_check_cp_work_mode(...) ((void)0)
#define mca_quick_charge_ibus_queue_push(...) ((void)0)
#define mca_quick_charge_check_charge_done(...) ((void)0)
#define mca_quick_charge_parallel_judge_temp(...) 0
#define mca_quick_charge_pre_charge_check(...) ((void)0)
#define update_batt_para(...) ((void)0)
#define mca_quick_charge_force_stop_charging(i) mca_quick_charge_stop_charging(i)
static int mca_quick_charge_judge_soc(struct mca_quick_charge_info *i) { (void)i;return judge_error; }
#define mca_quick_charge_judge_vbat(i) mca_quick_charge_judge_soc(i)
#define mca_quick_charge_judge_temp(i) mca_quick_charge_judge_soc(i)
#define mca_quick_charge_select_cp(i) mca_quick_charge_judge_soc(i)
#define mca_quick_charge_select_volt_para(i) mca_quick_charge_judge_soc(i)
#define mca_quick_charge_is_charge_abnormal(i) mca_quick_charge_judge_soc(i)
#define mca_qc_quick_charge_is_charge_abnormal(i) mca_quick_charge_judge_soc(i)
static int mca_quick_charge_judge_thermal_vote(struct mca_quick_charge_info *i,bool initial) { (void)i;(void)initial;return judge_error; }
static int mca_quick_charge_open_path(struct mca_quick_charge_info *i) { (void)i;return open_error; }
#define mca_qc_quick_charge_open_path(i) mca_quick_charge_open_path(i)
static void mca_quick_charge_stop_charging(struct mca_quick_charge_info *i) { stop_count++;i->pd_switch_to_pmic=true;i->proc_data.charge_flag=0; }
static int mca_quick_charge_req_adp_volt_and_cur(struct mca_quick_charge_info *i) { (void)i;req_count++;return 0; }
static bool strategy_class_fg_is_chip_ok(void) { return true; }
#define mca_qc_check_if_goto_taper(...) false
#define mca_check_if_goto_hw_taper(...) false
static int mca_quick_charge_regulation(struct mca_quick_charge_info *i) { (void)i;regulation_count++;return regulation_error; }
#define mca_qc_quick_charge_regulation(i) mca_quick_charge_regulation(i)
static bool schedule_delayed_work(struct delayed_work *w,int delay) { (void)delay;schedule_count++;if(w==&current->monitor_work)monitor_schedule++;if(w==&current->vfc_work)vfc_schedule++;return true; }
static const struct mca_hwid *mca_get_hwid_info(void) { return NULL; }
static int strategy_class_fg_ops_get_temperature(int *t) { *t=temperature;return 0; }
static void mca_quick_charge_reset_charge_para(struct mca_quick_charge_info *i) { (void)i;reset_count++;reset_at=++sequence; }
static void mca_quick_charge_exit_charging(struct mca_quick_charge_info *i) { exit_count++;exit_at=++sequence;mca_quick_charge_stop_charging(i);memset(&i->proc_data,0,sizeof(i->proc_data)); }
