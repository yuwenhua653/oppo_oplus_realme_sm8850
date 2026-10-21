static struct i2c_adapter adapter;
static struct i2c_client client={.addr=0x55,.adapter=&adapter};
static struct bq_fg_chip bq;
static void reset(u16 cmd,int payload)
{
 assert(live_allocations==0);
 memset(&bq,0,sizeof(bq));bq.client=&client;bq.regs[0]=0x3e;bq.regs[1]=0x60;
 memset(response,0,sizeof(response));response[0]=(u8)cmd;response[1]=(u8)(cmd>>8);
 for(int i=0;i<payload;i++)response[i+2]=(u8)(i+7);
 response[35]=(u8)(payload+4);response[34]=checksum(response,(u8)(payload+2));
 read_result=read_first_result=2;write_result=1;write_fail_after=-1;write_after_result=0;
 alloc_fail=0;calls=reads=writes=sleep4=sleep100=0;memset(captured,0,sizeof(captured));
}
static void check_unlocked(void) { assert(!bq.data_lock.held&&!bq.i2c_rw_lock.held); }
#ifdef ORIGINAL_NEGATIVE
int main(void)
{
 (void)groups;(void)cases;
 int reproduced=0;u8 out[32];
 reset(0x4c,16);response[0]^=1;response[34]=checksum(response,18);memset(out,0xab,sizeof(out));
 int ret=fg_mac_read_block(&bq,0x4c,out,3);
 if(ret>=0&&out[0]==7)reproduced++;
 reset(0x4c,16);read_result=read_first_result=1;memset(out,0xab,sizeof(out));
 ret=__fg_read_block(&client,0x3e,out,16);
 if(ret==1&&out[0]!=0xab)reproduced++;
 reset(0x4c,16);write_result=0;
 if(__fg_write_block(&client,0x3e,out,2)==0)reproduced++;
 assert(reproduced==3);puts("PASS: three original defects reproduced (wrong echo, short read publication, short write success)");return 0;
}
#else
static void test_transport(void)
{
 u8 out[40];const int fails[]={0,1,3,-EIO,-ETIMEDOUT,-EREMOTEIO};
 for(unsigned i=0;i<sizeof(fails)/sizeof(fails[0]);i++){
  reset(0x4c,16);read_result=read_first_result=fails[i];memset(out,0xab,sizeof(out));
  int ret=__fg_read_block(&client,0x3e,out,16);assert(ret==(fails[i]<0?fails[i]:-EIO));
  assert(reads==FG_I2C_RETRY_CNT&&sleep4==FG_I2C_RETRY_CNT);for(unsigned j=0;j<sizeof(out);j++)assert(out[j]==0xab);cases++;
 }
 reset(0x4c,16);read_first_result=1;memset(out,0xab,sizeof(out));assert(__fg_read_block(&client,0x3e,out,16)==2);assert(reads==2&&sleep4==1&&memcmp(out,response,16)==0&&out[16]==0xab);cases++;
 reset(0x4c,16);assert(__fg_read_block(NULL,0,out,1)==-ENODEV&&calls==0);assert(__fg_read_block(&client,0,NULL,1)==-EINVAL&&calls==0);assert(__fg_read_block(&client,0,out,0)==-EINVAL&&calls==0);cases+=3;
 const int wf[]={0,2,-EIO,-ETIMEDOUT,-EREMOTEIO};
 for(unsigned i=0;i<sizeof(wf)/sizeof(wf[0]);i++){
  reset(0x4c,16);write_result=wf[i];int ret=__fg_write_block(&client,0x3e,out,2);assert(ret==(wf[i]<0?wf[i]:-EIO));assert(writes==FG_I2C_RETRY_CNT&&sleep4==FG_I2C_RETRY_CNT);cases++;
 }
 reset(0x4c,16);alloc_fail=1;assert(__fg_write_block(&client,0,out,2)==-ENOMEM&&calls==0);cases++;
 reset(0x4c,16);assert(__fg_write_block(&client,0,NULL,1)==-EINVAL&&calls==0);assert(__fg_write_block(NULL,0,out,2)==-ENODEV&&calls==0);cases+=2;
 groups++;
}
static void test_variable_bounds(void)
{
 u8 out[40],actual;
 for(int payload=1;payload<=32;payload++)for(int minimum=1;minimum<=32;minimum++){
  reset(0x4c,payload);memset(out,0xab,sizeof(out));actual=0xed;
  int ret=fg_mac_read_block_variable(&bq,0x4c,out,32,(u8)minimum,&actual);
  if(payload>=minimum){assert(ret==0&&actual==payload&&memcmp(out,response+2,(size_t)payload)==0);for(unsigned j=(unsigned)payload;j<sizeof(out);j++)assert(out[j]==0xab);}
  else {assert(ret==-EMSGSIZE&&actual==0xed);for(unsigned j=0;j<sizeof(out);j++)assert(out[j]==0xab);}
  check_unlocked();cases++;
 }
 for(int capacity=0;capacity<=255;capacity++){
  reset(0x4c,16);memset(out,0xab,sizeof(out));actual=0xed;
  int ret=fg_mac_read_block_variable(&bq,0x4c,out,(u8)capacity,1,&actual);
  if(capacity==0||capacity>32){assert(ret==-EINVAL&&calls==0&&actual==0xed);}
  else if(capacity<16){assert(ret==-EMSGSIZE&&actual==0xed&&out[0]==0xab);}
  else assert(ret==0&&actual==16);
  check_unlocked();cases++;
 }
 for(int length=0;length<=255;length++){
  reset(0x4c,16);response[35]=(u8)length;
  if(length>=4&&length<=36)response[34]=checksum(response,(u8)(length-2));
  memset(out,0xab,sizeof(out));actual=0xed;
  int ret=fg_mac_read_block_variable(&bq,0x4c,out,32,1,&actual);
  if(length<4||length>36)assert(ret==-EPROTO&&actual==0xed&&out[0]==0xab);
  else if(length==4)assert(ret==-EMSGSIZE&&actual==0xed&&out[0]==0xab);
  else assert(ret==0&&actual==length-4);
  check_unlocked();cases++;
 }
 reset(0x4c,16);assert(fg_mac_read_block_variable(&bq,0x4c,out,2,3,&actual)==-EINVAL&&calls==0);assert(fg_mac_read_block_variable(&bq,0x4c,out,32,0,&actual)==-EINVAL&&calls==0);assert(fg_mac_read_block_variable(&bq,0x4c,out,32,1,NULL)==-EINVAL&&calls==0);assert(fg_mac_read_block_variable(NULL,0x4c,out,32,1,&actual)==-EINVAL&&calls==0);cases+=4;
 groups++;
}
static void test_frame_failures(void)
{
 u8 out[40],actual;
 for(int byte=0;byte<2;byte++)for(int bit=0;bit<8;bit++){
  reset(0x4c,16);response[byte]^=(u8)(1u<<bit);response[34]=checksum(response,18);memset(out,0xab,sizeof(out));actual=0xed;
  assert(fg_mac_read_block_variable(&bq,0x4c,out,32,3,&actual)==-EPROTO&&actual==0xed&&out[0]==0xab);check_unlocked();cases++;
 }
 for(int bit=0;bit<8;bit++){
  reset(0x4c,16);response[34]^=(u8)(1u<<bit);memset(out,0xab,sizeof(out));actual=0xed;
  assert(fg_mac_read_block_variable(&bq,0x4c,out,32,3,&actual)==-EBADMSG&&actual==0xed&&out[0]==0xab);check_unlocked();cases++;
 }
 reset(0x4c,16);bq.pm_suspend=1;actual=0xed;out[0]=0xab;assert(fg_mac_read_block_variable(&bq,0x4c,out,32,3,&actual)==-EAGAIN&&calls==0&&actual==0xed&&out[0]==0xab);check_unlocked();cases++;
 reset(0x4c,16);write_result=0;out[0]=0xab;actual=0xed;assert(fg_mac_read_block_variable(&bq,0x4c,out,32,3,&actual)==-EIO&&reads==0&&writes==5&&out[0]==0xab&&actual==0xed);check_unlocked();cases++;
 reset(0x4c,16);read_result=read_first_result=1;out[0]=0xab;actual=0xed;assert(fg_mac_read_block_variable(&bq,0x4c,out,32,3,&actual)==-EIO&&reads==5&&out[0]==0xab&&actual==0xed);check_unlocked();cases++;
 groups++;
}
static void test_prefix_and_legacy(void)
{
 u8 out[40];
 for(int len=1;len<=32;len++){
  reset(0x4c,32);memset(out,0xab,sizeof(out));assert(fg_mac_read_block(&bq,0x4c,out,(u8)len)==0&&memcmp(out,response+2,(size_t)len)==0&&out[len]==0xab);check_unlocked();cases++;
  reset(0x4c,len-1);memset(out,0xab,sizeof(out));assert(fg_mac_read_block(&bq,0x4c,out,(u8)len)==-EMSGSIZE&&out[0]==0xab);check_unlocked();cases++;
 }
 reset(0x4c,32);assert(fg_mac_read_block(&bq,0x4c,out,36)==-EINVAL&&calls==0);assert(fg_mac_read_block(&bq,0x4c,out,0)==-EINVAL&&calls==0);cases+=2;
 reset(0x4c,16);mutex_lock(&bq.i2c_rw_lock);memset(out,0xab,sizeof(out));assert(__fg_mac_read_block(&bq,0x4c,out,3)==0&&memcmp(out,response+2,3)==0&&out[3]==0xab);check_unlocked();cases++;
 reset(0x4c,16);mutex_lock(&bq.i2c_rw_lock);response[0]^=1;response[34]=checksum(response,18);out[0]=0xab;assert(__fg_mac_read_block(&bq,0x4c,out,3)==-EPROTO&&out[0]==0xab);check_unlocked();cases++;
 reset(0x4c,16);mutex_lock(&bq.i2c_rw_lock);out[0]=0xab;assert(__fg_mac_read_block(&bq,0x4c,out,36)==-EINVAL&&calls==0&&out[0]==0xab);check_unlocked();cases++;
 reset(0x4c,16);mutex_lock(&bq.i2c_rw_lock);out[0]=0xab;assert(__fg_mac_read_block(&bq,0x4c,out,17)==-EMSGSIZE&&out[0]==0xab);check_unlocked();cases++;
 reset(0x4c,16);memset(out,0xab,sizeof(out));assert(fg_mac_read_block_checked(&bq,0x4c,out,3)==0&&out[3]==0xab);check_unlocked();cases++;
 groups++;
}
static void test_write_transaction(void)
{
 u8 data[32];for(unsigned i=0;i<sizeof(data);i++)data[i]=(u8)(i+11);
 for(int len=0;len<=32;len++){
  reset(0x4c,16);assert(fg_mac_write_block(&bq,0x3e,data,(u8)len)==0&&writes==2&&reads==0&&sleep100==0);
  assert(captured[0].len==len+3&&captured[0].bytes[0]==0x3e&&captured[0].bytes[1]==0x3e&&captured[0].bytes[2]==0);
  assert(memcmp(captured[0].bytes+3,data,(size_t)len)==0&&captured[1].len==3&&captured[1].bytes[0]==0x60&&captured[1].bytes[1]==checksum(captured[0].bytes+1,(u8)(len+2))&&captured[1].bytes[2]==len+4);check_unlocked();cases++;
 }
 reset(0x4c,16);write_result=0;assert(fg_mac_write_block(&bq,0x3e,data,2)==-EIO&&writes==5&&captured[0].bytes[0]==0x3e&&captured[4].bytes[0]==0x3e);check_unlocked();cases++;
 reset(0x4c,16);write_fail_after=1;write_after_result=0;assert(fg_mac_write_block(&bq,0x3e,data,2)==-EIO&&writes==6);for(int i=1;i<6;i++)assert(captured[i].bytes[0]==0x60);check_unlocked();cases++;
 reset(0x4c,16);write_fail_after=1;write_after_result=-EREMOTEIO;assert(fg_mac_write_block(&bq,0x456e,data,2)==-EREMOTEIO&&writes==6&&sleep100==1);check_unlocked();cases++;
 reset(0x4c,16);mutex_lock(&bq.data_lock);assert(fg_mac_write_block_locked(&bq,0x456e,data,2)==0&&bq.data_lock.held&&sleep100==1);mutex_unlock(&bq.data_lock);check_unlocked();cases++;
 reset(0x4c,16);bq.pm_suspend=1;assert(fg_mac_write_block(&bq,0x3e,data,2)==-EAGAIN&&calls==0);check_unlocked();cases++;
 reset(0x4c,16);assert(fg_mac_write_block(&bq,0x3e,data,33)==-EINVAL&&calls==0);assert(fg_mac_write_block(&bq,0x3e,NULL,1)==-EINVAL&&calls==0);check_unlocked();cases+=2;
 groups++;
}
static void test_actual_manufacturer(void)
{
 static const u8 raw[16]={0x4d,0x49,0x37,0x34,0x43,0x37,0x7a,0x57,0x42,0x39,0x23,0x40,0x40,0x40,0x32,0};u8 out[32],actual;
 reset(0x4c,16);memcpy(response+2,raw,sizeof(raw));response[34]=checksum(response,18);actual=0;
 assert(fg_mac_read_block_variable(&bq,0x4c,out,32,3,&actual)==0&&actual==16&&out[2]==0x37&&memcmp(out,raw,16)==0);cases++;
 assert(fg_get_manufacture_data(&bq)==0&&reads==2);check_unlocked();cases++;
 reset(0x4c,8);int previous[MANU_DATA_LEN];for(int i=0;i<MANU_DATA_LEN;i++){manu_info[i].data=0x1234;previous[i]=manu_info[i].data;}
 assert(fg_get_manufacture_data(&bq)==-EMSGSIZE);for(int i=0;i<MANU_DATA_LEN;i++)assert(manu_info[i].data==previous[i]);check_unlocked();cases++;
 groups++;
}
static void test_consumer_failures(void)
{
 int value;
 reset(FG_MAC_CMD_LIFETIME1,7);response[8]=35;response[34]=checksum(response,9);value=0x1234;assert(fg_get_temp_max(&bq,&value)==0&&value==35&&reads==1);check_unlocked();cases++;
 reset(FG_MAC_CMD_LIFETIME1,7);read_result=read_first_result=-EREMOTEIO;value=0x1234;assert(fg_get_temp_max(&bq,&value)==-EREMOTEIO&&value==0x1234&&reads==5);check_unlocked();cases++;
 reset(FG_MAC_CMD_LIFETIME1,7);response[8]=0;response[34]=checksum(response,9);value=0x1234;assert(fg_get_temp_max(&bq,&value)==0&&value==0&&reads==2);check_unlocked();cases++;
 reset(FG_MAC_CMD_QMAX_CYCLECOUNT,4);bq.fg_vendor=MPC7021;value=0x1234;assert(fg_read_max_cell_volt(&bq,&value)==0&&value==((10<<8)|9));cases++;
 reset(FG_MAC_CMD_QMAX_CYCLECOUNT,3);bq.fg_vendor=MPC7021;value=0x1234;assert(fg_read_max_cell_volt(&bq,&value)==-EMSGSIZE&&value==0x1234);cases++;
 reset(FG_MAC_CMD_CALIBRATION_INFO_1,30);bq.batt_temp=500;value=0x1234;assert(fg_get_calibration_ffc_iterm(&bq,&value)==0&&value==((36<<8)|35));cases++;
 reset(FG_MAC_CMD_CALIBRATION_INFO_1,29);bq.batt_temp=500;value=0x1234;assert(fg_get_calibration_ffc_iterm(&bq,&value)==-EMSGSIZE&&value==0x1234);cases++;
 reset(FG_MAC_CMD_CALIBRATION_INFO_2,32);bq.batt_temp=500;value=0x1234;assert(fg_get_calibration_charge_energy(&bq,&value)==0&&value==((38<<8)|37));cases++;
 reset(FG_MAC_CMD_CALIBRATION_INFO_4,3);value=0x1234;assert(fg_get_real_supplement_energy(&bq,&value)==0&&value==((9<<8)|8));cases++;
 reset(FG_MAC_CMD_ITSTATUS1,18);bq.fg_vendor=MPC7012;u32 uv=0x1234;assert(fg_read_tsim(&bq,&uv)==0&&uv==((24u<<8)|23u));cases++;
 reset(FG_MAC_CMD_ITSTATUS1,14);bq.fg_vendor=BQ27Z561;uv=0x1234;assert(fg_read_tsim(&bq,&uv)==0&&uv==((20u<<8)|19u));cases++;
 reset(FG_MAC_CMD_ITSTATUS1,10);bq.fg_vendor=MPC7012;uv=0x1234;assert(fg_read_tambient(&bq,&uv)==0&&uv==((16u<<8)|15u));cases++;
 reset(FG_MAC_CMD_ITSTATUS1,16);bq.fg_vendor=BQ27Z561;uv=0x1234;assert(fg_read_tambient(&bq,&uv)==0&&uv==((22u<<8)|21u));cases++;
 reset(FG_MAC_CMD_ITSTATUS1,2);uv=0x1234;assert(fg_read_tremq(&bq,&uv)==0&&uv==((8u<<8)|7u));cases++;
 reset(FG_MAC_CMD_ITSTATUS1,4);uv=0x1234;assert(fg_read_tfullchgq(&bq,&uv)==0&&uv==((10u<<8)|9u));cases++;
 reset(FG_MAC_CMD_LIFETIME1,8);bq.fg_vendor=MPC7012;value=0x1234;assert(fg_get_temp_min(&bq,&value)==0&&value==14);cases++;
 groups++;
}
int main(void)
{
 test_transport();test_variable_bounds();test_frame_failures();test_prefix_and_legacy();test_write_transaction();test_actual_manufacturer();test_consumer_failures();
 printf("PASS %u groups, %u boundary/transport/frame/consumer cases; actual production function bodies\n",groups,cases);return 0;
}
#endif
