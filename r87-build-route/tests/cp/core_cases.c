static unsigned long assertions;
#define CHECK(x) do {assertions++;if(!(x)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x);exit(2);}}while(0)
static struct i2c_client client;
static void reset_bus(void) {memset(regs,0,sizeof(regs));bus_at=fail_at=fail_persistent=read_error=write_error=0;reads=writes=block_reads=events=judges=gate_writes=0;block_return=gate_readback_override=-1;}
static void init_chip(struct sc8581_device *b,int vendor) {
 memset(b,0,sizeof(*b));b->client=&client;b->chip_vendor=vendor;b->cp_role=SC8581_MASTER;b->i2c_is_working=true;
 b->cfg.bat_ovp_th=4500;b->cfg.bat_ovp_alarm_th=4400;b->cfg.wpc_ovp_th=22000;b->cfg.out_ovp_th=5000;b->cfg.pmid2out_ovp_th=600;
 for(int i=0;i<3;i++){b->cfg.bus_ovp_th[i]=i==0?22000:(i==1?11000:5000);b->cfg.usb_ovp_th[i]=i==0?22000:(i==1?14000:6500);b->cfg.bus_ocp_th[i]=5000;b->cfg.pmid2out_uvp_th[i]=100;}
 regs[SC8581_REG_6E]=vendor==SC8585?SC8585_DEVICE_ID:(vendor==SC8581?SC8581_DEVICE_ID:SC8561_DEVICE_ID);
}
static void transport(void) {
 u8 out[32];reset_bus();regs[7]=0xaa;read_error=-ETIMEDOUT;CHECK(cp_update_bits(&client,7,0x0f,3)==-ETIMEDOUT);CHECK(writes==0);CHECK(regs[7]==0xaa);
 reset_bus();regs[7]=0xaa;write_error=-ENXIO;CHECK(cp_update_bits(&client,7,0x0f,3)==-ENXIO);CHECK(regs[7]==0xaa);
 reset_bus();regs[7]=0xaa;CHECK(cp_update_bits(&client,7,0x0f,3)==0);CHECK(regs[7]==0xa3);
 for(int len=1;len<=32;len++)for(int count=0;count<=32;count++){
  reset_bus();memset(out,0x5a,sizeof(out));memset(regs,0xb6,sizeof(regs));block_return=count;int r=cp_read_i2c_block_data(&client,0,len,out);
  CHECK((r==len)==(count==len));for(int j=0;j<32;j++)CHECK(out[j]==(count==len&&j<len?0xb6:0x5a));
 }
 for(int e=-EIO;e>=-EIO-4;e--){reset_bus();memset(out,0x5a,32);block_return=e;CHECK(cp_read_i2c_block_data(&client,0,16,out)==e);for(int j=0;j<32;j++)CHECK(out[j]==0x5a);}
 reset_bus();CHECK(cp_read_i2c_block_data(NULL,0,1,out)==-EINVAL);CHECK(cp_read_i2c_block_data(&client,0,0,out)==-EINVAL);CHECK(cp_read_i2c_block_data(&client,0,33,out)==-EINVAL);CHECK(cp_read_i2c_block_data(&client,0,1,NULL)==-EINVAL);CHECK(block_reads==0);
}
static void mode_matrix(void) {
 for(int vendor=SC8561;vendor<=SC8585;vendor++)for(int mode=0;mode<8;mode++){
  struct sc8581_device b;reset_bus();init_chip(&b,vendor);b.work_mode=CP_MODE_DIV2;b.operation_mode=SC8581_FORWARD_2_1_CHARGER_MODE;
  CHECK(sc8581_set_operation_mode(&b,mode)==0);int n=bus_at;CHECK(n>20);CHECK(b.operation_mode==(mode==3?2:(mode==7?6:mode)));
  for(int fail=1;fail<=n;fail++){
   reset_bus();init_chip(&b,vendor);b.work_mode=CP_MODE_DIV2;b.operation_mode=SC8581_FORWARD_2_1_CHARGER_MODE;fail_at=fail;fail_persistent=1;
   CHECK(sc8581_set_operation_mode(&b,mode)==-EREMOTEIO);CHECK(b.work_mode==CP_MODE_DIV2);CHECK(b.operation_mode==SC8581_FORWARD_2_1_CHARGER_MODE);CHECK(bus_at==fail);
  }
 }
}
static void init_matrix(void) {
 for(int vendor=SC8561;vendor<=SC8585;vendor++){
  struct sc8581_device b;reset_bus();init_chip(&b,vendor);CHECK(sc8581_init_device(&b)==0);int n=bus_at;CHECK(n>40);
  for(int fail=1;fail<=n;fail++) {reset_bus();init_chip(&b,vendor);fail_at=fail;fail_persistent=1;CHECK(sc8581_init_device(&b)==-EREMOTEIO);CHECK(bus_at<=n*ERROR_RECOVERY_COUNT);}
  /* A transient retryable setup error may recover; previous failed attempts
   * must not poison the next attempt's result. Reset/parallel are mandatory. */
  reset_bus();init_chip(&b,vendor);fail_at=5;CHECK(sc8581_init_device(&b)==0);
 }
}
static void detect_cases(void) {
 struct sc8581_device b;
 for(int vendor=SC8561;vendor<=SC8585;vendor++){reset_bus();init_chip(&b,vendor);b.chip_vendor=-1;CHECK(cp_charge_detect_device(&b)==0);CHECK(b.chip_vendor==vendor);}
 reset_bus();init_chip(&b,SC8585);regs[SC8581_REG_6E]=0xff;b.chip_vendor=-1;CHECK(cp_charge_detect_device(&b)<0);CHECK(b.chip_vendor==-1);
 reset_bus();init_chip(&b,SC8585);read_error=-ETIMEDOUT;b.chip_vendor=-1;CHECK(cp_charge_detect_device(&b)==-ETIMEDOUT);CHECK(b.chip_vendor==-1);CHECK(reads==ERROR_RECOVERY_COUNT);
}
static void irq_cases(void) {
 struct sc8581_device b;reset_bus();init_chip(&b,SC8585);b.ovpgate_en=true;block_return=0;CHECK(sc8581_dump_important_regs(&b,NULL)==-EIO);CHECK(writes==0&&events==0);
 reset_bus();init_chip(&b,SC8585);b.ovpgate_en=true;block_return=-ETIMEDOUT;CHECK(sc8581_dump_important_regs(&b,NULL)==-ETIMEDOUT);CHECK(writes==0&&events==0);
 reset_bus();init_chip(&b,SC8585);read_error=-ENXIO;sc8581_irq_handler(&b.irq_handle_work.work);CHECK(events==0&&block_reads==0);
 reset_bus();init_chip(&b,SC8585);bool value=true;read_error=-ENXIO;CHECK(sc8581_get_int_stat(&b,VUSB_PRESENT_STAT,&value)==-ENXIO);CHECK(value);
}
static void gate_cases(void) {
 struct sc8581_device b;
 reset_bus();init_chip(&b,SC8585);CHECK(sc8581_enable_ovpgate(&b,true)==0);CHECK(b.ovpgate_en);CHECK(regs[SC8581_REG_0B]&SC8581_OVPGATE_EN_MASK);
 CHECK(sc8581_enable_ovpgate(&b,false)==0);CHECK(!b.ovpgate_en);CHECK(!(regs[SC8581_REG_0B]&SC8581_OVPGATE_EN_MASK));
 for(int fail=1;fail<=3;fail++) {reset_bus();init_chip(&b,SC8585);fail_at=fail;fail_persistent=1;CHECK(sc8581_enable_ovpgate(&b,true)==-EREMOTEIO);CHECK(!b.ovpgate_en);}
 reset_bus();init_chip(&b,SC8585);gate_readback_override=0;CHECK(sc8581_enable_ovpgate(&b,true)==-EIO);CHECK(!b.ovpgate_en);CHECK(writes==MCA_SET_OVPGATE_COUNT);
 reset_bus();init_chip(&b,SC8585);fail_at=1;CHECK(sc8581_enable_ovpgate(&b,true)==0);CHECK(b.ovpgate_en);
}
static void *first_rmw(void *arg) {(void)arg;actor=1;int r=cp_update_bits(&client,7,1,1);return (void *)(intptr_t)r;}
static void *second_rmw(void *arg) {(void)arg;actor=2;int r=cp_update_bits(&client,7,2,2);pthread_mutex_lock(&phase_lock);second_finished=1;pthread_cond_broadcast(&phase_cond);pthread_mutex_unlock(&phase_lock);return (void *)(intptr_t)r;}
static void concurrency(void) {
 reset_bus();pause_read=1;first_read_paused=release_read=second_lock_attempt=second_finished=0;pthread_t a,b;void *ra,*rb;
 CHECK(!pthread_create(&a,NULL,first_rmw,NULL));pthread_mutex_lock(&phase_lock);while(!first_read_paused)pthread_cond_wait(&phase_cond,&phase_lock);pthread_mutex_unlock(&phase_lock);
 CHECK(!pthread_create(&b,NULL,second_rmw,NULL));pthread_mutex_lock(&phase_lock);while(!second_lock_attempt&&!second_finished)pthread_cond_wait(&phase_cond,&phase_lock);release_read=1;pthread_cond_broadcast(&phase_cond);pthread_mutex_unlock(&phase_lock);
 CHECK(!pthread_join(a,&ra)&&ra==NULL);CHECK(!pthread_join(b,&rb)&&rb==NULL);CHECK(regs[7]==3);pause_read=0;
}
static void successful_images(void) {
 for(int vendor=SC8561;vendor<=SC8585;vendor++){
  struct sc8581_device b;reset_bus();init_chip(&b,vendor);CHECK(sc8581_init_device(&b)==0);uint64_t digest=1469598103934665603ULL;for(unsigned i=0;i<256;i++){digest^=regs[i];digest*=1099511628211ULL;}printf("SUCCESS variant=%d regs=%016llx\n",vendor,(unsigned long long)digest);
 }
}
int main(int argc,char **argv) {
 if(argc>1){if(!strcmp(argv[1],"success")){successful_images();return 0;}if(!strcmp(argv[1],"rmw")){reset_bus();read_error=-EIO;CHECK(cp_update_bits(&client,7,1,1)==-EIO);CHECK(writes==0);return 0;}if(!strcmp(argv[1],"block")){reset_bus();u8 out[16];memset(out,0x5a,16);block_return=1;CHECK(cp_read_i2c_block_data(&client,0,16,out)==-EIO);return 0;}if(!strcmp(argv[1],"init")){struct sc8581_device b;reset_bus();init_chip(&b,SC8585);fail_at=1;CHECK(sc8581_init_device(&b)==-EREMOTEIO);return 0;}if(!strcmp(argv[1],"irq")){irq_cases();return 0;}if(!strcmp(argv[1],"concurrency")){concurrency();return 0;}return 1;}
 transport();mode_matrix();init_matrix();detect_cases();irq_cases();gate_cases();concurrency();successful_images();printf("PASS CP core assertions=%lu\n",assertions);return 0;
}
