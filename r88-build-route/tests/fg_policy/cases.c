static void policy(struct strategy_fg *fg,bool valid,bool is_eu) {
 fg->is_eu_model=is_eu;
#if CANDIDATE
 fg->eu_policy_valid=valid;
#else
 (void)valid;
#endif
}
static struct strategy_fg fresh_fg(void) {
 struct strategy_fg fg={0};fg.fg_init_flag=true;fg.cfg.report_full_raw_soc=9900;
 fg.cfg.soc_proportion=100;fg.cfg.soc_proportion_c=0;fg.cfg.fg_type=MCA_FG_TYPE_SINGLE;
 fg.cfg.rechg_cfg.temp_low=0;fg.cfg.rechg_cfg.temp_high=50;fg.cfg.rechg_cfg.rest_time=1;
 fg.batt_rsoc=37;fg.batt_raw_soc=10000;strategy_fg_init_voter(&fg);return fg;
}
static void test_probe_storage(void) {
 reset_host();storage_error=-EPROBE_DEFER;storage_scribble=true;storage_value=true;
 struct platform_device p={0};int result=strategy_fg_probe(&p);
 CHECK(result==0);CHECK(registrations==1);CHECK(auth_groups==1);CHECK(monitor_schedules==1);
 CHECK(storage_reads==1);CHECK(ota_schedules==0);
#if CANDIDATE
 CHECK(!current->eu_policy_valid);CHECK(!current->is_eu_model);CHECK(current->eu_policy_errno==-EPROBE_DEFER);
#endif
 free(p.data);
}
static void test_optional_missing(void) {
 reset_host();parse_ota=1;parse_qbg=1;optional_result[MCA_FG_OP_OTA_FLAG]=0;
 struct platform_device p={0};int result=strategy_fg_probe(&p);
 CHECK(result==0);CHECK(!current->cfg.support_nvt1000_ota);CHECK(current->cfg.support_qbg);
 CHECK(ota_schedules==0);CHECK(registrations==1);free(p.data);
}
static void test_dt_errno(void) {
 reset_host();parse_error=-EINVAL;struct platform_device p={0};int result=strategy_fg_probe(&p);
 CHECK(result==-EINVAL);CHECK(registrations==0);CHECK(storage_reads==0);free(p.data);
}
static void test_unknown_map(void) {
 reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,false,false);
 fg.batt_rsoc=37;fg.batt_raw_soc=10000;fg.charging_done=true;fg.en_smooth_full=true;
 CHECK(fg_update_mapped_soc(&fg)==0);CHECK(fg.batt_mapped_soc==37);CHECK(fg.batt_mapped_soc_decimal==0);
}
static void test_unknown_recharge(void) {
 reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,false,false);
 fg.power_present=true;fg.charging_done=true;fg.batt_raw_soc=100;
 CHECK(mca_strategy_check_recharge(&fg)==0);CHECK(recharge_count==0);CHECK(!fg.recharging);
}
static void test_unknown_lossless(void) {
 reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,false,false);fg.fast_charge=true;
 CHECK(mca_strategy_check_lossless_recharge(&fg)==0);fg.charging_done=true;
 fg.lossless_recharge=true;now_ms+=100000;
 CHECK(mca_strategy_check_lossless_recharge(&fg)==0);CHECK(recharge_count==0);
#if CANDIDATE
 CHECK(!fg.lossless_recharge);CHECK(votes_named("losslessRec",false)==4);
#endif
}
static void test_unknown_done(void) {
 reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,false,false);
 fg.en_smooth_full=true;fg.keep_full_flag=true;fg.recharging=true;fg.lossless_recharge=true;
 CHECK(strategy_fg_ops_set_charging_done(&fg,true)==0);CHECK(!fg.keep_full_flag);
 CHECK(!fg.en_smooth_full);CHECK(fg.charging_done);CHECK(!fg.recharging);CHECK(!fg.lossless_recharge);
 CHECK(votes_named("term_recharge",true)==1);CHECK(votes_named("qc_done",false)==1);
}
static void test_invalid_event(void) {
 reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,false,false);
 int result=strategy_fg_process_event(MCA_EVENT_IS_EU_MODEL,2,&fg);
 CHECK(result==-EINVAL);CHECK(!fg.is_eu_model);CHECK(!fg.boot_update_soc);
 CHECK(vote_count==0);
#if CANDIDATE
 CHECK(!fg.eu_policy_valid);
#endif
}
static void test_late_false_event(void) {
 reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,true,true);fg.boot_update_soc=false;
 CHECK(strategy_fg_process_event(MCA_EVENT_IS_EU_MODEL,0,&fg)==0);
 CHECK(!fg.is_eu_model);CHECK(fg.boot_update_soc);
}
static void test_unknown_hold(void) {
 reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,false,false);
 fg.keep_full_flag=true;fg.batt_raw_soc=10000;fg.batt_current_mean=0;
 int result=fg_ui_soc_process_special_conditions(&fg,100,99);
 CHECK(result==99);
}
static void test_unknown_decimal(void) {
 reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,false,false);
 fg.batt_mapped_soc=50;fg.batt_ui_soc_decimal=75;
 fg_ui_soc_update_decimal(&fg,49,49);CHECK(fg.batt_ui_soc_decimal==0);
}

#if CANDIDATE
static void test_storage_fault_matrix(void) {
 int errors[]={-EPROBE_DEFER,-EIO,-EACCES,-EOPNOTSUPP,-EINVAL};
 for(unsigned e=0;e<ARRAY_SIZE(errors);e++)for(int scribble=0;scribble<2;scribble++)for(int old=0;old<2;old++) {
  reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,old,old);fg.boot_update_soc=old;
  storage_error=errors[e];storage_scribble=scribble;storage_value=!old;
  CHECK(strategy_fg_read_eu_policy(&fg)==errors[e]);CHECK(fg.eu_policy_valid==(bool)old);
  CHECK(fg.is_eu_model==(bool)old);CHECK(fg.boot_update_soc==(bool)old);CHECK(fg.eu_policy_errno==errors[e]);CHECK(storage_reads==1);
 }
 for(int value=0;value<2;value++) {
  reset_host();struct strategy_fg fg=fresh_fg();storage_value=value;
  CHECK(strategy_fg_read_eu_policy(&fg)==0);CHECK(fg.eu_policy_valid);CHECK(fg.is_eu_model==(bool)value);
  CHECK(fg.eu_policy_errno==0);CHECK(fg.boot_update_soc==(bool)value);
  struct platform_device p={0};CHECK(strategy_fg_probe(&p)==0);CHECK(current->eu_policy_valid);
  CHECK(current->is_eu_model==(bool)value);CHECK(registrations==1);free(p.data);
 }
}
static void test_probe_fault_matrix(void) {
 int errors[]={-EPROBE_DEFER,-EIO,-EACCES,-EOPNOTSUPP,-EINVAL};
 for(unsigned e=0;e<ARRAY_SIZE(errors);e++) {
  reset_host();storage_error=errors[e];struct platform_device p={0};
  CHECK(strategy_fg_probe(&p)==0);CHECK(registrations==1);CHECK(monitor_schedules==1);
  CHECK(!current->eu_policy_valid);CHECK(current->eu_policy_errno==errors[e]);free(p.data);
  reset_host();parse_error=errors[e];memset(&p,0,sizeof(p));
  CHECK(strategy_fg_probe(&p)==errors[e]);CHECK(registrations==0);CHECK(storage_reads==0);free(p.data);
 }
 reset_host();allocation_error=1;struct platform_device p={0};CHECK(strategy_fg_probe(&p)==-ENOMEM);
 CHECK(registrations==0);CHECK(storage_reads==0);
}
static void test_optional_matrix(void) {
 enum mca_fg_optional_op ops[]={MCA_FG_OP_OTA_FLAG,MCA_FG_OP_AVERAGE_CURRENT,MCA_FG_OP_OTA_UPDATE,MCA_FG_OP_QBG_CHG_DATA};
 for(unsigned op=0;op<ARRAY_SIZE(ops);op++)for(int absence=0;absence<2;absence++) {
  reset_host();parse_ota=1;parse_qbg=1;optional_result[ops[op]]=absence?-EOPNOTSUPP:0;
  struct platform_device p={0};CHECK(strategy_fg_probe(&p)==0);CHECK(registrations==1);
  CHECK(current->cfg.support_nvt1000_ota==(op==3));CHECK(current->cfg.support_qbg==(op!=3));
  CHECK(ota_schedules==(op==3));CHECK(optional_calls[ops[op]]==1);
  strategy_fg_update_qbg_chg_data(current);CHECK(qbg_calls==(op!=3));free(p.data);
 }
 for(unsigned op=0;op<ARRAY_SIZE(ops);op++)for(int which=0;which<2;which++) {
  reset_host();parse_ota=1;parse_qbg=1;int error=which?-EIO:-EPROBE_DEFER;optional_result[ops[op]]=error;
  struct platform_device p={0};CHECK(strategy_fg_probe(&p)==error);CHECK(registrations==0);
  CHECK(storage_reads==0);CHECK(ota_schedules==0);free(p.data);
 }
 reset_host();parse_ota=parse_qbg=1;struct platform_device p={0};CHECK(strategy_fg_probe(&p)==0);
 CHECK(current->cfg.support_nvt1000_ota);CHECK(current->cfg.support_qbg);CHECK(ota_schedules==1);
 for(unsigned op=0;op<ARRAY_SIZE(ops);op++)CHECK(optional_calls[ops[op]]==1);
 strategy_fg_update_qbg_chg_data(current);CHECK(qbg_calls==1);free(p.data);
 reset_host();memset(&p,0,sizeof(p));CHECK(strategy_fg_probe(&p)==0);
 for(unsigned op=0;op<ARRAY_SIZE(ops);op++)CHECK(optional_calls[ops[op]]==0);
 strategy_fg_update_qbg_chg_data(current);CHECK(qbg_calls==0);CHECK(ota_schedules==0);free(p.data);
 reset_host();parse_ota=parse_qbg=1;optional_result[MCA_FG_OP_OTA_FLAG]=optional_result[MCA_FG_OP_QBG_CHG_DATA]=0;
 memset(&p,0,sizeof(p));CHECK(strategy_fg_probe(&p)==0);CHECK(!current->cfg.support_qbg);
 CHECK(!current->cfg.support_nvt1000_ota);CHECK(ota_schedules==0);strategy_fg_update_qbg_chg_data(current);CHECK(qbg_calls==0);free(p.data);
}
static void test_soc_matrix(void) {
 for(int is_eu=0;is_eu<2;is_eu++)for(int rsoc=0;rsoc<=100;rsoc++) {
  reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,false,is_eu);
  fg.batt_rsoc=rsoc;fg.batt_raw_soc=(rsoc%2)?123:10000;
  fg.charging_done=fg.lossless_recharge=fg.en_smooth_full=true;
  CHECK(fg_update_mapped_soc(&fg)==0);CHECK(fg.batt_mapped_soc==rsoc);CHECK(fg.batt_mapped_soc_decimal==0);
  int decimal=-123,rate=-456;fg.batt_ui_soc_decimal=99;
  CHECK(strategy_fg_ops_get_soc_decimal(&fg,&decimal,&rate)==0);CHECK(decimal==0);CHECK(rate==0);
 }
 reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,true,false);
 CHECK(fg_update_mapped_soc(&fg)==0);CHECK(fg.batt_mapped_soc==100);
 fg.batt_raw_soc=5070;CHECK(fg_update_mapped_soc(&fg)==0);CHECK(fg.batt_mapped_soc==50);CHECK(fg.batt_mapped_soc_decimal==70);
 policy(&fg,true,true);fg.chg_status=POWER_SUPPLY_STATUS_CHARGING;fg.batt_raw_soc=10000;
 CHECK(fg_update_mapped_soc(&fg)==0);CHECK(fg.batt_mapped_soc==99);
 fg.charging_done=true;fg.batt_rsoc=100;CHECK(fg_update_mapped_soc(&fg)==0);CHECK(fg.batt_mapped_soc==100);
 policy(&fg,true,false);fg.keep_full_flag=true;fg.batt_current_mean=0;
 CHECK(fg_ui_soc_process_special_conditions(&fg,100,99)==100);
 policy(&fg,true,true);CHECK(fg_ui_soc_process_special_conditions(&fg,100,99)==99);
}
static void test_event_matrix(void) {
 reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,false,false);
 for(int value=0;value<2;value++) {
  fg.keep_full_flag=fg.en_smooth_full=fg.lossless_recharge=true;fg.eu_policy_errno=-EIO;
  fg.boot_update_soc=false;int prior_recharges=recharge_count;int before_votes=vote_count;
  CHECK(strategy_fg_process_event(MCA_EVENT_IS_EU_MODEL,value,&fg)==0);CHECK(fg.eu_policy_valid);
  CHECK(fg.is_eu_model==(bool)value);CHECK(fg.eu_policy_errno==0);CHECK(fg.boot_update_soc);
  CHECK(!fg.keep_full_flag);CHECK(!fg.en_smooth_full);CHECK(!fg.lossless_recharge);CHECK(recharge_count==prior_recharges);
  CHECK(vote_count==before_votes+2);
  fg.boot_update_soc=false;before_votes=vote_count;
  CHECK(strategy_fg_process_event(MCA_EVENT_IS_EU_MODEL,value,&fg)==0);CHECK(!fg.boot_update_soc);CHECK(vote_count==before_votes);
 }
 int invalid[]={-1,2,12345};
 for(unsigned v=0;v<ARRAY_SIZE(invalid);v++) {
  struct strategy_fg old=fg;CHECK(strategy_fg_process_event(MCA_EVENT_IS_EU_MODEL,invalid[v],&fg)==-EINVAL);
  CHECK(!memcmp(&old,&fg,sizeof(fg)));
 }
 for(int wireless=0;wireless<2;wireless++)for(int is_eu=0;is_eu<2;is_eu++) {
  reset_host();fg=fresh_fg();current=&fg;policy(&fg,false,is_eu);fg.batt_ui_soc=50;
  fg.charging_done=fg.keep_full_flag=fg.en_smooth_full=fg.recharging=true;
  CHECK(strategy_fg_process_event(wireless?MCA_EVENT_WIRELESS_CONNECT:MCA_EVENT_USB_CONNECT,0,&fg)==0);
  CHECK(fg.power_present);CHECK(fg.charging_done);CHECK(votes_named("term_recharge",false)==0);
  CHECK(monitor_schedules==1);CHECK(cancel_count==1);
  CHECK(strategy_fg_process_event(wireless?MCA_EVENT_WIRELESS_DISCONNECT:MCA_EVENT_USB_DISCONNECT,0,&fg)==0);
  CHECK(!fg.power_present);CHECK(!fg.charging_done);CHECK(!fg.keep_full_flag);CHECK(!fg.en_smooth_full);CHECK(!fg.recharging);
  CHECK(votes_named("term_recharge",false)==1);CHECK(votes_named("calibration",false)==1);CHECK(votes_named("qc_done",false)==1);
 }
 CHECK(strategy_fg_process_event(MCA_EVENT_IS_EU_MODEL,0,NULL)==-1);
}
static void test_known_controls(void) {
 for(int is_eu=0;is_eu<2;is_eu++) {
  reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,true,is_eu);
  CHECK(strategy_fg_ops_set_charging_done(&fg,true)==0);CHECK(fg.charging_done);
  CHECK(fg.keep_full_flag==!is_eu);CHECK(fg.en_smooth_full==(bool)is_eu);CHECK(votes_named("term_recharge",true)==1);
  fg.power_present=true;fg.batt_raw_soc=9900;fg.batt_ui_soc=94;
  CHECK(mca_strategy_check_recharge(&fg)==0);CHECK(recharge_count==1);
  CHECK(strategy_fg_ops_set_charging_done(&fg,false)==0);CHECK(!fg.charging_done);CHECK(!fg.en_smooth_full);
 }
 reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,true,true);fg.charging_done=true;fg.fast_charge=true;fg.batt_cyclecount=300;
 CHECK(mca_strategy_check_lossless_recharge(&fg)==0);CHECK(recharge_count==0);CHECK(!fg.lossless_recharge);
}
static void test_unknown_ui_speed(void) {
 reset_host();struct strategy_fg fg=fresh_fg();policy(&fg,false,false);
 fg.batt_rsoc=50;fg.power_present=true;fg.chg_status=POWER_SUPPLY_STATUS_CHARGING;
 fg.batt_current_mean=-100;fg.plugin_time=-100;fg.en_smooth_full=true;
 CHECK(fg_ui_soc_smooth(&fg,true)==50);now_ms+=10000;fg.batt_rsoc=55;
 CHECK(fg_ui_soc_smooth(&fg,true)==51);CHECK(fg.batt_ui_soc_decimal==0);CHECK(shutdown_checks>0);
 fg.vbatt_empty=true;CHECK(fg_ui_soc_smooth(&fg,true)==0);
}
#endif
struct named_test { const char *name; void (*run)(void); };
static const struct named_test tests[]={
 {"probe_storage",test_probe_storage},{"optional_missing",test_optional_missing},{"dt_errno",test_dt_errno},
 {"unknown_map",test_unknown_map},{"unknown_recharge",test_unknown_recharge},{"unknown_lossless",test_unknown_lossless},
 {"unknown_done",test_unknown_done},{"invalid_event",test_invalid_event},{"late_false_event",test_late_false_event},
 {"unknown_hold",test_unknown_hold},{"unknown_decimal",test_unknown_decimal},
#if CANDIDATE
 {"storage_fault_matrix",test_storage_fault_matrix},{"probe_fault_matrix",test_probe_fault_matrix},
 {"optional_matrix",test_optional_matrix},{"soc_matrix",test_soc_matrix},{"event_matrix",test_event_matrix},
 {"known_controls",test_known_controls},{"unknown_ui_speed",test_unknown_ui_speed},
#endif
};
int main(int argc,char **argv) {
 (void)strategy_fg_update_qbg_chg_data;(void)strategy_fg_ops_get_soc_decimal;
 int ran=0;for(unsigned i=0;i<ARRAY_SIZE(tests);i++)if(argc==1||!strcmp(argv[1],tests[i].name)) {
  scenario=tests[i].name;tests[i].run();ran++;
 }
 CHECK(ran>0);printf("PASS %d FG production-C scenarios, %d assertions\n",ran,assertions);return 0;
}
