#include <test_shim.h>
#include SOURCE_PATH

struct expected_io {int write,prop,rc;size_t bytes;unsigned char data[128];};
static struct expected_io expect[64];
static unsigned nexp,nseen,total_io;
#ifndef NEGATIVE_CONTROL
static struct adsp_pd_protocol *disconnect_pd;
static int disconnect_prop, disconnect_down;
#endif
static char lifecycle[64];
static unsigned lifecycle_len;
static int register_fail;
static struct protocol_class_pd_ops *registered_ops;
static void *registered_priv;
static unsigned notifier_mask;
static void mark(char c) {lifecycle[lifecycle_len++]=c;lifecycle[lifecycle_len]=0;}
static void reset_io(void) {assert(nseen==nexp);nseen=nexp=0;}
static void queue_io(int write,int prop,size_t bytes,const void *buf,int rc) {
 assert(nexp<64 && bytes<=128);struct expected_io *e=&expect[nexp++];
 *e=(struct expected_io){.write=write,.prop=prop,.rc=rc,.bytes=bytes};
 if(buf && bytes)memcpy(e->data,buf,bytes);
}
static int io(int write,int prop,void *buf,size_t bytes) {
 assert(mock_lock_depth==0);++total_io;assert(nseen<nexp);struct expected_io *e=&expect[nseen++];
#ifndef NEGATIVE_CONTROL
 if (disconnect_pd && prop==disconnect_prop) {
  if(disconnect_down)adsp_pd_protocol_abnormal_cb(&disconnect_pd->abnormal_nb,0x2e,NULL);
  else adsp_pd_protocol_event_cb(&disconnect_pd->event_nb,MCA_EVENT_USB_DISCONNECT,NULL);
  disconnect_pd=NULL;
 }
#endif
 if(e->write!=write || e->prop!=prop || e->bytes!=bytes) {
  fprintf(stderr,"wire mismatch actual=%c/0x%x/%zu expected=%c/0x%x/%zu\n",write?'W':'R',prop,bytes,e->write?'W':'R',e->prop,e->bytes);abort();
 }
 if(write && bytes)assert(!memcmp(e->data,buf,bytes));
 if(!write && !e->rc && bytes)memcpy(buf,e->data,bytes);
 return e->rc;
}
int mca_adsp_glink_write_prop(int prop,void *buf,size_t bytes) {return io(1,prop,buf,bytes);}
int mca_adsp_glink_read_prop(int prop,void *buf,size_t bytes) {return io(0,prop,buf,bytes);}
int mca_event_block_notify_register(unsigned type,struct notifier_block *nb) {
 assert(nb->notifier_call);assert(type==MCA_EVENT_TYPE_CHARGER_CONNECT || type==MCA_EVENT_CHARGE_STATUS);
 int stage=type==MCA_EVENT_TYPE_CHARGER_CONNECT?1:2;mark(stage==1?'E':'A');
 if(register_fail==stage)return -EIO;
 notifier_mask|=1u<<stage;return 0;
}
int mca_event_block_notify_unregister(unsigned type,struct notifier_block *nb) {
 assert(nb->notifier_call);int stage=type==MCA_EVENT_TYPE_CHARGER_CONNECT?1:2;
 assert(notifier_mask&(1u<<stage));notifier_mask&=~(1u<<stage);mark(stage==1?'e':'a');return 0;
}
int protocol_class_pd_register_ops(unsigned port,struct protocol_class_pd_ops *ops,void *data) {
 assert(port==0);mark('P');
#ifndef NEGATIVE_CONTROL
 assert(notifier_mask==6);assert(!registered_ops);
#endif
 if(register_fail==3)return -EIO;
 registered_ops=ops;registered_priv=data;return 0;
}
int protocol_class_pd_unregister_ops(unsigned port,struct protocol_class_pd_ops *ops,void *data) {
 assert(port==0 && ops==registered_ops && data==registered_priv);mark('p');registered_ops=NULL;registered_priv=NULL;return 0;
}
static void lifecycle_reset(void) {assert(!registered_ops && !notifier_mask);lifecycle_len=0;lifecycle[0]=0;}
#ifdef NEGATIVE_CONTROL
int main(void) {
 /* Deliberately assert Myron's stock wire ID against the exact old source. */
 u32 v=(9000u/20u)<<16 | (3000u/50u);
 queue_io(1,0x21018,4,&v,0);
 return g_adsp_pd_ops.protocol_pd_pps_pdo_select(9000,3000,NULL);
}
#else
#define READ_SCALAR(member,prop,type,value) do {type out=0,want=(value);reset_io();queue_io(0,(prop),sizeof(out),&want,0);assert(g_adsp_pd_ops.member(&out,&pd)==0 && out==want);reset_io();} while(0)
#define WRITE_SCALAR(member,prop,type,value) do {type val=(value);reset_io();queue_io(1,(prop),sizeof(val),&val,0);assert(g_adsp_pd_ops.member(val,&pd)==0);reset_io();} while(0)
static void test_wire(void) {
 struct adsp_pd_protocol pd={0};unsigned int out=17,volt=1,curr=2;int type=-1;u32 word;
 _Static_assert(sizeof(struct pd_pdo)==16,"stock PDO stride");
 word=(9000u/20u)<<16 | (3050u/50u);
 queue_io(1,0x21018,4,&word,0);
 assert(g_adsp_pd_ops.protocol_pd_pps_pdo_select(9000,3050,&pd)==0);reset_io();
 queue_io(1,0x21018,4,&word,-ETIMEDOUT);
 assert(g_adsp_pd_ops.protocol_pd_pps_pdo_select(9000,3050,&pd)==-ETIMEDOUT);reset_io();
 WRITE_SCALAR(protocol_pd_fixed_pdo_set_vol,0x21019,int,9000);
 pd.verify_process=1;assert(g_adsp_pd_ops.protocol_pd_fixed_pdo_set_vol(9000,&pd)==0 && nexp==0);pd.verify_process=0;
 WRITE_SCALAR(protocol_pd_set_gear_shift,0x21029,int,2);
 READ_SCALAR(protocol_pd_get_pps_ptf,0x21026,int,3);
 READ_SCALAR(protocol_pd_get_pps_max_cur,0x21014,unsigned int,5000);
 READ_SCALAR(protocol_pd_get_pps_apdo_max,0x21015,unsigned int,100);
 READ_SCALAR(protocol_pd_get_typec_mode,0x21016,int,4);
 READ_SCALAR(protocol_pd_get_typec_cc_orientation,0x21017,int,1);
 READ_SCALAR(protocol_pd_get_adapter_id,0x2100f,unsigned int,0x1111);
 READ_SCALAR(protocol_pd_get_adapter_svid,0x21010,unsigned int,0x2717);
 READ_SCALAR(protocol_pd_get_has_dp,0x2101f,bool,true);
 READ_SCALAR(protocol_pd_get_cid_status,0x21020,bool,true);
 READ_SCALAR(protocol_pd_get_otg_plugin_status,0x21021,bool,true);
 WRITE_SCALAR(protocol_pd_set_cc_toggle,0x21022,u8,1);
 READ_SCALAR(protocol_pd_get_cc_toggle,0x21022,bool,true);
 READ_SCALAR(protocol_pd_get_snk_src_mode,0x21023,int,2);
 READ_SCALAR(protocol_pd_get_cc_status,0x21024,bool,true);
 READ_SCALAR(protocol_pd_get_cc_short_vbus,0x21025,int,1);
 READ_SCALAR(protocol_pd_get_suspend_support_status,0x21027,bool,true);
 READ_SCALAR(protocol_pd_get_zimi_cypress_flag,0x21028,int,1);
 WRITE_SCALAR(protocol_pd_set_verify_process,0x21002,int,1);
 READ_SCALAR(protocol_pd_get_verify_process,0x21002,int,1);
 out=100;queue_io(1,0x2101c,4,&out,0);assert(g_adsp_pd_ops.protocol_pd_pps_get_max_power(&out,&pd)==0);reset_io();
 word=(11000u/20u)<<16 | (2500u/50u);queue_io(0,0x2101a,4,&word,0);
 assert(g_adsp_pd_ops.protocol_pd_get_pps_status(&volt,&curr,&pd)==0 && volt==11000 && curr==2500);reset_io();
 queue_io(0,0x2101a,4,&word,-EIO);volt=123;curr=456;
 assert(g_adsp_pd_ops.protocol_pd_get_pps_status(&volt,&curr,&pd)==-EIO && volt==123 && curr==456);reset_io();
 struct pd_pdo wire_pdos[7]={{5000,5000,3000,0},{3300,11000,5000,3}},pdos[7]={0};
 queue_io(0,0x21012,sizeof(pdos),wire_pdos,0);assert(g_adsp_pd_ops.protocol_pd_get_pdos(pdos,7,&pd)==0 && !memcmp(pdos,wire_pdos,sizeof(pdos)));reset_io();
 assert(g_adsp_pd_ops.protocol_pd_get_pdos(pdos,8,&pd)==-EINVAL);
 assert(g_adsp_pd_ops.protocol_pd_get_pdos(pdos,0,&pd)==-EINVAL);
 assert(g_adsp_pd_ops.protocol_pd_get_pdos(pdos,-1,&pd)==-EINVAL);
 assert(g_adsp_pd_ops.protocol_pd_get_pdos(NULL,1,&pd)==-EINVAL);
 queue_io(0,0x21012,sizeof(pdos),NULL,-EIO);assert(g_adsp_pd_ops.protocol_pd_get_pdos(pdos,7,&pd)==-EIO);reset_io();
 word=11;queue_io(0,0x2000c,4,&word,0);assert(g_adsp_pd_ops.protocol_pd_get_pd_type(&type,&pd)==0 && type==11);reset_io();
 pd.pd_verifed=1;queue_io(0,0x2000c,4,&word,0);assert(g_adsp_pd_ops.protocol_pd_get_pd_type(&type,&pd)==0 && type==12);reset_io();
 word=12;queue_io(0,0x2000c,4,&word,0);assert(g_adsp_pd_ops.protocol_pd_get_pd_type(&type,&pd)==0 && type==0);reset_io();
 type=77;queue_io(0,0x2000c,4,&word,-EIO);assert(g_adsp_pd_ops.protocol_pd_get_pd_type(&type,&pd)==-EIO && type==77);reset_io();
 unsigned char role=0;word=2;queue_io(0,0x2100d,4,&word,0);assert(g_adsp_pd_ops.protocol_pd_get_data_role(&role,&pd)==0 && role==2);reset_io();
 char state[64];word=2;queue_io(0,0x2100e,4,&word,0);assert(g_adsp_pd_ops.protocol_pd_get_current_state(state,64,&pd)==0 && !strcmp(state,"SNK_Ready"));reset_io();
 assert(g_adsp_pd_ops.protocol_pd_set_pd_active(1,&pd)==0);type=0;assert(g_adsp_pd_ops.protocol_pd_get_pd_active(&type,&pd)==0 && type==1);
}
static void test_auth_and_vdm(void) {
 struct adsp_pd_protocol pd={0};int one=1,keep=7,verified=-1,cmd;struct usbpd_vdm_data vdm={0};
 queue_io(1,0x21011,4,&one,-EIO);assert(g_adsp_pd_ops.protocol_pd_set_pd_verifed(one,&pd)==-EIO && pd.pd_verifed==0);reset_io();
 queue_io(1,0x21011,4,&one,0);queue_io(0,0x2100b,4,&keep,0);assert(g_adsp_pd_ops.protocol_pd_set_pd_verifed(one,&pd)==0);reset_io();
 assert(g_adsp_pd_ops.protocol_pd_get_pd_verifed(&verified,&pd)==0 && verified==1);
 assert(g_adsp_pd_ops.protocol_pd_get_support_keep_pdo(&verified,&pd)==0 && verified==7);
 int zero=0;queue_io(1,0x21011,4,&zero,-EIO);
 assert(g_adsp_pd_ops.protocol_pd_set_pd_verifed(0,&pd)==-EIO && pd.pd_verifed==1 && pd.support_keep_pdo==7);reset_io();
 queue_io(1,0x21002,4,&one,-EIO);
 assert(g_adsp_pd_ops.protocol_pd_set_verify_process(1,&pd)==-EIO && pd.verify_process==1);reset_io();
 queue_io(1,0x21011,4,&one,0);queue_io(0,0x2100b,4,&keep,-EIO);assert(g_adsp_pd_ops.protocol_pd_set_pd_verifed(one,&pd)==-EIO && pd.support_keep_pdo==0);reset_io();
 pd.verify_process=1;pd.support_keep_pdo=1;assert(adsp_pd_protocol_event_cb(&pd.event_nb,MCA_EVENT_USB_DISCONNECT,NULL)==0 && pd.pd_verifed==0 && pd.verify_process==0 && pd.support_keep_pdo==0);
 pd.pd_verifed=pd.support_keep_pdo=1;assert(adsp_pd_protocol_abnormal_cb(&pd.abnormal_nb,0x2e,NULL)==0 && pd.pd_verifed==0 && pd.support_keep_pdo==0);
 struct {int cmd,prop;} simple[]={{1,0x21003},{2,0x21004},{3,0x21005},{6,0x21008},{7,0x21009},{0xfe,0x2100b},{0xff,0x2100c},{200,0x2100d}};
 for(size_t i=0;i<sizeof(simple)/sizeof(*simple);++i) {
  u32 value=0x1234;queue_io(1,simple[i].prop,4,&value,0);assert(g_adsp_pd_ops.protocol_pd_request_vdm_cmd(simple[i].cmd,&value,4,&pd)==0);reset_io();
 }
 u32 value=0;queue_io(1,0x2100c,0,NULL,0);assert(g_adsp_pd_ops.protocol_pd_request_vdm_cmd(0xff,&value,0,&pd)==0);reset_io();
 for(int down=0;down<2;++down) {
  disconnect_pd=&pd;disconnect_prop=0x21011;disconnect_down=down;
  queue_io(1,0x21011,4,&one,0);
  assert(g_adsp_pd_ops.protocol_pd_set_pd_verifed(1,&pd)==-ENOTCONN && pd.pd_verifed==0 && pd.support_keep_pdo==0);reset_io();
  disconnect_pd=&pd;disconnect_prop=0x2100b;disconnect_down=down;
  queue_io(1,0x21011,4,&one,0);queue_io(0,0x2100b,4,&keep,0);
  assert(g_adsp_pd_ops.protocol_pd_set_pd_verifed(1,&pd)==-ENOTCONN && pd.pd_verifed==0 && pd.support_keep_pdo==0);reset_io();
 }
 int authcmds[]={4,5,8};int authprops[]={0x21006,0x21007,0x2100a};size_t shortlens[]={0,1,3,4,15};
 for(size_t c=0;c<3;++c) {
  for(size_t i=0;i<5;++i) {
   size_t n=shortlens[i];u32 *shortbuf=malloc(n?n:1);memset(shortbuf,0x5a,n?n:1);unsigned before=total_io;
   assert(g_adsp_pd_ops.protocol_pd_request_vdm_cmd(authcmds[c],shortbuf,n,&pd)==-EINVAL && total_io==before);free(shortbuf);
  }
  u32 data[4]={0x12345678,0x90abcdef,0x10203040,0x50607080},wire[4];for(int i=0;i<4;++i)wire[i]=__builtin_bswap32(data[i]);
  queue_io(1,authprops[c],16,wire,0);assert(g_adsp_pd_ops.protocol_pd_request_vdm_cmd(authcmds[c],data,16,&pd)==0);reset_io();
 }
 assert(g_adsp_pd_ops.protocol_pd_request_vdm_cmd(123,&value,4,&pd)==-EINVAL);
 assert(g_adsp_pd_ops.protocol_pd_request_vdm_cmd(4,NULL,16,&pd)<0);
 for(int c=1;c<=3;++c) {
  int r=21;queue_io(0,0x21013,4,&c,0);queue_io(0,0x21002+c,4,&r,0);assert(g_adsp_pd_ops.protocol_pd_get_vdm_cmd(&cmd,&vdm,&pd)==0 && cmd==c);reset_io();
 }
 cmd=5;u32 response[4]={1,2,3,4};queue_io(0,0x21013,4,&cmd,0);queue_io(0,0x21007,16,response,0);assert(g_adsp_pd_ops.protocol_pd_get_vdm_cmd(&cmd,&vdm,&pd)==0 && vdm.s_secert[4]==1 && vdm.s_secert[7]==4);reset_io();
 vdm.s_secert[4]=99;queue_io(0,0x21013,4,&cmd,0);queue_io(0,0x21007,16,response,-EIO);assert(g_adsp_pd_ops.protocol_pd_get_vdm_cmd(&cmd,&vdm,&pd)==-EIO && vdm.s_secert[4]==99);reset_io();
}
static void test_lifecycle_and_diagnostics(void) {
 struct platform_device p={0};allocation_fail=1;assert(adsp_pd_protocol_probe(&p)==-ENOMEM);allocation_fail=0;
 const char *failure_order[]={"","E","EAe","EAPae"};
 for(int stage=1;stage<=3;++stage) {
  lifecycle_reset();register_fail=stage;
  assert(adsp_pd_protocol_probe(&p)==-EIO && !registered_ops && !notifier_mask);
  assert(!strcmp(lifecycle,failure_order[stage]));free(p.data);p.data=NULL;
  assert(!adsp_pd_status.registered);
 }
 lifecycle_reset();register_fail=0;unsigned before=total_io;
 assert(adsp_pd_protocol_probe(&p)==0 && !strcmp(lifecycle,"EAP") && registered_ops==&g_adsp_pd_ops && adsp_pd_status.registered==1);
 char status[PAGE_SIZE];for(int i=0;i<100;++i)assert(adsp_pd_status_ops.get(status,NULL)>0);
 assert(total_io==before && strstr(status,"registered=1") && strstr(status,"select_mv=9000"));
 assert(!strstr(status,"seed") && !strstr(status,"secret") && !strstr(status,"adapter_id"));
 adsp_pd_protocol_remove(&p);assert(!strcmp(lifecycle,"EAPpae") && !registered_ops && !notifier_mask && !adsp_pd_status.registered);free(p.data);
 assert(total_io==before);
}
int main(void) {test_wire();test_auth_and_vdm();test_lifecycle_and_diagnostics();assert(nseen==nexp);puts("PASS: stock wire transactions, I/O failures, VDM bounds, cache and lifecycle, read-only status");return 0;}
#endif
