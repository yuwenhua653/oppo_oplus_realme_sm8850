static void release(struct mca_quick_charge_batt_para_info *b) {
 if(!b->temp_info)return;
 for(int i=0;i<b->temp_para_size;i++){struct mca_quick_charge_temp_para_info *t=&b->temp_info[i];kfree(t->volt_info.stage_para);kfree(t->volt_info.volt_para);kfree(t->volt_ffc_info.stage_para);kfree(t->volt_ffc_info.volt_para);}kfree(b->temp_info);memset(b,0,sizeof(*b));
}
static int final_voltage(struct device_node *node,const char *name) {struct property *p=property(node,name);return !strcmp(name,"null")?0:atoi(p->strings[p->count-3]);}
static void check_voltage(struct device_node *node,const char *name,const char *stage,struct mca_quick_charge_volt_para_info *v) {
 struct property *p=property(node,name);
 if(!strcmp(name,"null")){check(!v->volt_para&&!v->volt_para_size&&!v->stage_para,"null voltage table");return;}
 check(p && v->volt_para_size==p->count/3,"voltage count");
 for(int i=0;i<v->volt_para_size;i++){check(v->volt_para[i].voltage==atoi(p->strings[i*3]),"voltage unchanged");check(v->volt_para[i].current_max==atoi(p->strings[i*3+1]),"maximum current unchanged");check(v->volt_para[i].current_min==atoi(p->strings[i*3+2]),"minimum current unchanged");}
 if(!strcmp(stage,"null")){check(v->stage_para==NULL,"null stage");check(mca_quick_charge_jump_stage(1,v)==1,"null stage has existing behavior");return;}
 p=property(node,stage);check(v->stage_para!=NULL,"stage retained");
 for(int i=0;i<v->volt_para_size*2;i++)check(v->stage_para[i]==(int)p->numbers[i],"stage values unchanged");
}
static void verify(struct device_node *node,const char **raw,int rows,struct mca_quick_charge_batt_para_info *b) {
 check(b->temp_info && b->temp_para_size==rows,"temp table published");
 for(int i=0;i<rows;i++){const char **a=raw+i*9;struct mca_quick_charge_temp_para_info *t=&b->temp_info[i];
 check(t->temp_para.temp_low==atoi(a[0])&&t->temp_para.temp_high==atoi(a[1]),"temperature bounds unchanged");
 check(t->temp_para.low_temp_hysteresis==atoi(a[2])&&t->temp_para.high_temp_hysteresis==atoi(a[3]),"hysteresis unchanged");
 check(t->temp_para.max_current==atoi(a[4]),"temperature current limit unchanged");
 check(t->temp_para.normal_max_fv==final_voltage(node,a[5]),"normal FV derived from final original voltage");
 check(t->temp_para.ffc_max_fv==final_voltage(node,a[6]),"FFC FV derived from final original voltage");
 check_voltage(node,a[5],a[7],&t->volt_info);check_voltage(node,a[6],a[8],&t->volt_ffc_info);
 }
}
static void modernize(struct device_node *node,const char **raw,int rows,const char **out,char values[20][24]) {
 for(int i=0;i<rows;i++){const char **a=raw+i*9;const char **b=out+i*11;for(int j=0;j<5;j++)b[j]=a[j];snprintf(values[i*2],24,"%d",final_voltage(node,a[5]));snprintf(values[i*2+1],24,"%d",final_voltage(node,a[6]));b[5]=values[i*2];b[6]=values[i*2+1];for(int j=5;j<9;j++)b[j+2]=a[j];}
}
static void failure(struct device_node *node,const char *name,int role,int mode) {
 struct mca_quick_charge_info info={0};struct mca_quick_charge_batt_para_info *b=mode?&info.base_flip_para[role]:&info.batt_para[role];
 struct mca_quick_charge_temp_para_info sentinel={0};b->temp_info=&sentinel;b->temp_para_size=3;
 check(mca_quick_charge_parse_temp_para(node,role,name,&info,mode)<0,"reject injected failure");
 check(b->temp_info==&sentinel && b->temp_para_size==3,"failed parse preserves previously published output");check(live==0,"failure releases nested allocations");
}
static void run_fixture(struct device_node *node,const char *name) {
 struct property *p=property(node,name);const char **raw=p->strings;int rows=p->count/9, original_count=p->count;
 const char *modern[110];char values[20][24];modernize(node,raw,rows,modern,values);
#if !CANDIDATE
 reset();struct mca_quick_charge_info before={0};check(mca_quick_charge_parse_temp_para(node,0,name,&before,0)<0,"R89 rejects actual 63-string stock table");check(diag_errno==-EINVAL&&!strcmp(diag_stage,"temp_count"),"R89 reproduces observed temp_count=-EINVAL");check(!live,"count failure has no allocation");
#endif
 for(int width=9;width<=11;width+=2){
#if !CANDIDATE
 if(width==9)continue;
#endif
 p->strings=width==9?raw:modern;p->count=rows*width;
 for(int role=0;role<2;role++)for(int mode=0;mode<2;mode++){
 reset();struct mca_quick_charge_info info={0};check(mca_quick_charge_parse_temp_para(node,role,name,&info,mode)==0,"valid table parse");struct mca_quick_charge_batt_para_info *b=mode?&info.base_flip_para[role]:&info.batt_para[role];verify(node,raw,rows,b);int ac=alloc_calls,sc=string_calls,ic=integer_calls,uc=u32_calls;release(b);check(live==0,"success released");
#if CANDIDATE
 for(int k=1;k<=ac;k++){reset();alloc_fail=k;failure(node,name,role,mode);}
 for(int k=1;k<=sc;k++){reset();string_fail=k;failure(node,name,role,mode);}
 for(int k=1;k<=ic;k++){reset();integer_fail=k;failure(node,name,role,mode);}
 for(int k=1;k<=uc;k++){reset();u32_fail=k;failure(node,name,role,mode);}
#else
 (void)ac;(void)sc;(void)ic;(void)uc;
#endif
 }
 }
 p->strings=raw;p->count=original_count;
#if CANDIDATE
 /* Malformed/missing referenced stage properties must not silently disappear. */
 for(int row=0;row<rows;row++)for(int col=7;col<=8;col++){
  const char *stage=raw[row*9+col];if(!strcmp(stage,"null"))continue;
  struct property *sp=property(node,stage);const u32 *saved=sp->numbers;int count=sp->number_count;
  reset();sp->numbers=NULL;failure(node,name,0,0);sp->numbers=saved;
  reset();sp->number_count=count-1;failure(node,name,0,0);sp->number_count=count;
 }
#endif
}
static void edge_cases(void) {
#if CANDIDATE
 const char *row[]={"0","10","0","0","1000","null","null","null","null"};const char *longrow[132];
 struct property p={"table",longrow,0,NULL,0};struct device_node n={&p,1};
 for(int width=9;width<=11;width+=2)for(int rows=1;rows<=12;rows++){
  for(int i=0;i<rows*width;i++)longrow[i]=width==9?row[i%9]:(i%11<5?row[i%11]:(i%11<7?"0":"null"));p.count=rows*width;
  reset();struct mca_quick_charge_info info={0};int ret=mca_quick_charge_parse_temp_para(&n,0,"table",&info,0);
  if(rows<=10){check(ret==0,"maximum group boundary accepted");check(info.batt_para[0].temp_para_size==rows,"row count");release(&info.batt_para[0]);}else {check(ret<0,"oversize rejected including ambiguous 99");check(!live,"oversize allocations released");}
 }
 for(int count=0;count<=13;count++){if(count==9||count==11)continue;reset();p.count=count;failure(&n,"table",0,0);}
 reset();failure(&n,"absent",0,0);
 /* Eleven-column explicit FV is not replaced by derivation. */
 const char *eleven[]={"0","10","1","2","1000","4311","4422","null","null","null","null"};p.strings=eleven;p.count=11;reset();struct mca_quick_charge_info info={0};check(!mca_quick_charge_parse_temp_para(&n,0,"table",&info,0),"explicit FV accepted");check(info.batt_para[0].temp_info[0].temp_para.normal_max_fv==4311 && info.batt_para[0].temp_info[0].temp_para.ffc_max_fv==4422,"explicit eleven-column FV unchanged");release(&info.batt_para[0]);
#endif
}
int main(void) {run_fixture(&fixture_cn,"batt_para_atl");run_fixture(&fixture_cn,"batt_para_cos");run_fixture(&fixture_gbl,"batt_para_atl");edge_cases();check(!live,"no final allocation leaks");printf("PASS scenarios=%u checks=%u candidate=%d\n",scenarios,checks,CANDIDATE);return 0;}
