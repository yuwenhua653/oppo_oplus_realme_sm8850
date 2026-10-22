static unsigned assertions;
#define CHECK(x) do { assertions++;if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);abort();} } while(0)
static void reset(struct mca_quick_charge_info *info,int dual) {
 memset(info,0,sizeof(*info));memset(chips,0,sizeof(chips));memset(&fg,0,sizeof(fg));fg.fg_init_flag=true;fg.cfg.fg_type=dual?1:0;
 for(int k=0;k<2;k++){chips[k].role=k;chips[k].fast_mode_valid=true;provider_error[k]=provider_writes[k]=provider_calls[k]=0;}
 current=info;info->vfc_para.support_cp_vfc=true;info->proc_data.ffc_flag=1;
 class_calls=desired_mode=open_error=judge_error=regulation_error=temperature=stop_count=regulation_count=schedule_count=monitor_schedule=vfc_schedule=vote_count=disable_count=req_count=reset_count=exit_count=sequence=reset_at=exit_at=mode_at=0;
}
static void start_failure(void) {
 for(int dual=0;dual<2;dual++)for(int role=0;role<=dual;role++)for(int platform=0;platform<2;platform++)for(int desired=0;desired<2;desired++) {
  struct mca_quick_charge_info i;reset(&i,dual);i.is_platform_qc=platform;i.proc_data.ffc_flag=desired;for(int k=0;k<=dual;k++)chips[k].fast_mode=!desired;provider_error[role]=-EREMOTEIO;
  mca_quick_charge_start_charging(&i);
  CHECK(class_calls==1);CHECK(provider_writes[role]==1);CHECK(stop_count==1);CHECK(i.pd_switch_to_pmic);CHECK(i.proc_data.total_err==1);CHECK(i.proc_data.charge_flag==0);CHECK(vote_count==2);CHECK(disable_count==1);CHECK(req_count==1);CHECK(schedule_count==0);
  provider_error[role]=0;mca_quick_charge_start_charging(&i);
  CHECK(class_calls==2);CHECK(provider_writes[role]==2);CHECK(i.proc_data.charge_flag==MCA_QUICK_CHG_STS_CHARGING);CHECK(!i.pd_switch_to_pmic);CHECK(monitor_schedule==1);CHECK(vfc_schedule==1);
  if(dual)CHECK(provider_writes[1-role]==1);
 }
 struct mca_quick_charge_info i;reset(&i,0);open_error=-EIO;mca_quick_charge_start_charging(&i);CHECK(class_calls==0);CHECK(stop_count==1&&vote_count==2&&disable_count==1&&req_count==1);CHECK(schedule_count==0);
 reset(&i,0);judge_error=-ERANGE;mca_quick_charge_start_charging(&i);CHECK(class_calls==0&&stop_count==0&&schedule_count==0);
}
static void monitor_failure(void) {
 for(int dual=0;dual<2;dual++)for(int role=0;role<=dual;role++)for(int desired=0;desired<2;desired++) {
  struct mca_quick_charge_info i;reset(&i,dual);i.proc_data.ffc_flag=desired;for(int k=0;k<=dual;k++)chips[k].fast_mode=!desired;provider_error[role]=-ETIMEDOUT;
  mca_quick_charge_monitor_work(&i.monitor_work.work);
  CHECK(class_calls==1);CHECK(provider_writes[role]==1);CHECK(stop_count==1);CHECK(regulation_count==0);CHECK(schedule_count==0);CHECK(i.proc_data.total_err==1);CHECK(i.proc_data.charge_flag==0);CHECK(chips[role].fast_mode==!desired);
  provider_error[role]=0;mca_quick_charge_monitor_work(&i.monitor_work.work);
  CHECK(class_calls==2);CHECK(provider_writes[role]==2);CHECK(chips[role].fast_mode==desired);CHECK(regulation_count==1);CHECK(monitor_schedule==1);
  if(dual)CHECK(provider_writes[1-role]==1);
  for(int n=0;n<20;n++)mca_quick_charge_monitor_work(&i.monitor_work.work);
  CHECK(class_calls==22);CHECK(provider_writes[role]==2);if(dual)CHECK(provider_writes[1-role]==1);CHECK(regulation_count==21);
 }
}
static void separate_instances(void) {
 struct mca_quick_charge_info a,b;reset(&a,0);mca_quick_charge_monitor_work(&a.monitor_work.work);CHECK(provider_writes[0]==1);
 /* Another lifecycle/provider now starts opposite to the last request. */
 chips[0].fast_mode=false;memset(&b,0,sizeof(b));current=&b;b.proc_data.ffc_flag=1;mca_quick_charge_monitor_work(&b.monitor_work.work);CHECK(provider_writes[0]==2);
}
static void thermal_failure(void) {
 for(int initial=0;initial<2;initial++)for(int old_index=0;old_index<3;old_index++) {
  struct mca_quick_charge_info i;reset(&i,0);chips[0].fast_mode=true;provider_error[0]=-EIO;temperature=500;i.batt_para[0].temp_para_size=3;
  for(int n=0;n<3;n++){i.batt_para[0].temp_info[n].temp_para.temp_low=n*40;i.batt_para[0].temp_info[n].temp_para.temp_high=(n+1)*40;}
  i.proc_data.temp_para_index[0]=old_index;
  CHECK(mca_quick_charge_can_tbat_do_charge(0,&i,initial)==-EIO);CHECK(i.proc_data.ffc_flag==0);CHECK(desired_mode==0);CHECK(provider_writes[0]==1);CHECK(chips[0].fast_mode);
  if(!initial&&old_index==0)CHECK(i.proc_data.temp_hys_en==MCA_QUICK_TEMP_HYS_HIGH);
  if(!initial&&old_index==2)CHECK(i.proc_data.temp_hys_en==MCA_QUICK_TEMP_HYS_LOW);
  provider_error[0]=0;CHECK(mca_quick_charge_can_tbat_do_charge(0,&i,initial)==-1);CHECK(!chips[0].fast_mode);
 }
}
static void disconnect_failure(void) {
 for(int dual=0;dual<2;dual++)for(int role=0;role<=dual;role++) {
  struct mca_quick_charge_info i;reset(&i,dual);for(int k=0;k<=dual;k++)chips[k].fast_mode=true;provider_error[role]=-EIO;
  CHECK(mca_quick_charge_process_event(MCA_EVENT_USB_DISCONNECT,0,&i)==-EIO);CHECK(reset_count==1&&exit_count==1&&stop_count==1);CHECK(reset_at<exit_at&&exit_at<mode_at);CHECK(provider_writes[role]==1);CHECK(schedule_count==0);CHECK(i.pd_switch_to_pmic);
  provider_error[role]=0;CHECK(mca_quick_charge_process_event(MCA_EVENT_USB_DISCONNECT,0,&i)==0);CHECK(provider_writes[role]==2);if(dual)CHECK(provider_writes[1-role]==1);
 }
 CHECK(mca_quick_charge_process_event(MCA_EVENT_USB_DISCONNECT,0,NULL)==-1);
}
static void enum_boundary(void) {
 struct mca_quick_charge_info i;reset(&i,0);CHECK(fg.cfg.fg_type==MCA_FG_TYPE_SINGLE);CHECK(MCA_FG_TYPE_SINGLE_NUM_MAX==0);CHECK(strategy_class_fg_set_fastcharge(true)==0);CHECK(provider_calls[0]==1);CHECK(provider_calls[1]==0);CHECK(provider_writes[0]==1);CHECK(provider_writes[1]==0);
 reset(&i,1);CHECK(fg.cfg.fg_type==MCA_FG_TYPE_PARALLEL);CHECK(fg.cfg.fg_type==1);CHECK(strategy_class_fg_set_fastcharge(true)==0);CHECK(provider_calls[0]==1);CHECK(provider_calls[1]==1);CHECK(provider_writes[0]==1);CHECK(provider_writes[1]==1);
}
int main(int argc,char **argv) {
 enum_boundary();
 if(argc==2&&!strcmp(argv[1],"start"))start_failure();
 else if(argc==2&&!strcmp(argv[1],"monitor"))monitor_failure();
 else if(argc==2&&!strcmp(argv[1],"instances"))separate_instances();
 else if(argc==2&&!strcmp(argv[1],"thermal"))thermal_failure();
 else if(argc==2&&!strcmp(argv[1],"disconnect"))disconnect_failure();
 else {start_failure();monitor_failure();separate_instances();thermal_failure();disconnect_failure();}
 printf("PASS quickchg assertions=%u\n",assertions);return 0;
}
