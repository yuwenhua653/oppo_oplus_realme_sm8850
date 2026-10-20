static unsigned int cases;
static void reset_io(void){clock_depth=prepare_depth=irq_depth=writes=reads=0;trace_len=0;trace[0]=0;io_failure=0;}
static void balanced(struct dsi_display*d){assert(!clock_depth&&!prepare_depth&&!irq_depth&&!d->display_lock.locked&&!d->panel->lock.locked);if(d->drm_dev&&d->drm_dev->kms->vm)assert(!d->drm_dev->kms->vm->vm_res_lock.locked);cases++;}
static void result(struct myron_clone*s,const char*expected){char b[32];assert(flatmode_check_show(s->device,NULL,b)==2);assert(!strcmp(b,expected));balanced(s->owner);}
int main(void)
{
 run_base_tests();
 static const u8 offset[]={0x39,1,0,0,1,0,3,0xb0,0,0x53};
 static const u8 status[]={0x06,1,0,0,0,0,1,0x53};
 static const u8 end[]={0x15,1,0,0,0,0,2,0xb0,0};
 u32 lengths[]={2},expected[]={0x20,0x40};
 struct property props[]={
  {"mi,flatmode-status-check-enabled","",0},
  {"mi,mdss-dsi-panel-flatmode-status-offset-command",offset,sizeof(offset)},
  {"mi,mdss-dsi-panel-flatmode-status-command",status,sizeof(status)},
  {"mi,mdss-dsi-panel-flatmode-status-offset-end-command",end,sizeof(end)},
  {"mi,mdss-dsi-panel-flatmode-status-read-length",lengths,sizeof(lengths)},
  {"mi,mdss-dsi-panel-flatmode-on-status-value",expected,sizeof(expected)},
  {"mi,mdss-dsi-panel-flatmode-status-command-state","dsi_lp_mode",12},
 };
 struct device_node node={.props=props,.nr=7};
 struct dsi_panel panel={.panel_of_node=&node,.name="xiaomi p11u 42 0d 0a cmd mode dsc dsi panel",.panel_initialized=true};
 struct dsi_ctrl ctrl={0};struct sde_vm vm={.owns=true};struct sde_kms kms={.vm=&vm};struct drm_device drm={.kms=&kms};
 struct dsi_display d={.panel=&panel,.panel_node=&node,.display_type="primary",.drm_dev=&drm,.ctrl={{&ctrl}},.ctrl_count=1,.host_ready=true};
 active_display=&d;assert(!myron_mi_clone_attach(&d));struct myron_clone*s=myron_clone_owner;
 read_bytes[0]=0x20;read_bytes[1]=0x40;
 reset_io();result(s,"1\n");assert(writes==2&&reads==1);assert(!strcmp(trace,"ABCWDIPRUiWc"));assert(read_flags&MIPI_DSI_MSG_USE_LPM);
 read_bytes[1]=0;reset_io();result(s,"0\n");assert(reads==1);read_bytes[1]=0x40;
 for(int failure=1;failure<=7;failure++){reset_io();io_failure=failure;result(s,"0\n");assert(!allocated_blocks||allocated_blocks==1);if(failure>=2)assert(writes==2);}
 for(int failure=8;failure<=9;failure++){reset_io();io_failure=failure;d.tx_cmd_buf=NULL;result(s,"0\n");assert(!writes&&!reads&&!clock_depth);}
 props[1].name="absent-offset";props[3].name="absent-end";reset_io();d.tx_cmd_buf=NULL;result(s,"1\n");assert(!writes&&reads==1&&!strcmp(trace,"ABCIPRUic"));props[1].name="mi,mdss-dsi-panel-flatmode-status-offset-command";props[3].name="mi,mdss-dsi-panel-flatmode-status-offset-end-command";
 reset_io();panel.panel_initialized=false;result(s,"0\n");assert(!writes&&!reads);panel.panel_initialized=true;
 reset_io();panel.esd_recovery_pending=1;result(s,"0\n");assert(!trace_len);panel.esd_recovery_pending=0;
 reset_io();d.host_ready=false;result(s,"0\n");assert(!trace_len);d.host_ready=true;
 reset_io();d.sim=true;result(s,"0\n");assert(!trace_len);d.sim=false;
 reset_io();d.bypass=true;result(s,"0\n");assert(!trace_len);d.bypass=false;
 reset_io();kms.suspended=true;result(s,"0\n");assert(!trace_len);kms.suspended=false;
 reset_io();vm.owns=false;result(s,"0\n");assert(!trace_len);vm.owns=true;
 reset_io();ctrl.secure_mode=true;result(s,"0\n");assert(!trace_len);ctrl.secure_mode=false;
 reset_io();d.ctrl_count=0;result(s,"0\n");assert(!trace_len);d.ctrl_count=1;
 /* Busy display and VM paths must never wait in reverse lock order. */
 char b[32];reset_io();mutex_lock(&d.display_lock);assert(flatmode_check_show(s->device,NULL,b)==2&&!strcmp(b,"0\n"));assert(!trace_len);mutex_unlock(&d.display_lock);balanced(&d);
 reset_io();mutex_lock(&vm.vm_res_lock);assert(flatmode_check_show(s->device,NULL,b)==2&&!strcmp(b,"0\n"));assert(!trace_len);mutex_unlock(&vm.vm_res_lock);balanced(&d);
 reset_io();alloc_fail=1;result(s,"0\n");alloc_fail=0;assert(!trace_len);
 /* No check capability means the upstream default unconfirmed result. */
 props[0].name="absent";reset_io();result(s,"0\n");assert(!trace_len);props[0].name="mi,flatmode-status-check-enabled";
 props[2].size--;reset_io();result(s,"0\n");assert(!trace_len);props[2].size++;
 lengths[0]=0;reset_io();result(s,"0\n");assert(!trace_len);lengths[0]=257;reset_io();result(s,"0\n");assert(!trace_len);lengths[0]=2;
 expected[0]=256;reset_io();result(s,"0\n");assert(!trace_len);expected[0]=0x20;
 props[4].size=3;reset_io();result(s,"0\n");assert(!trace_len);props[4].size=4;
 props[5].size=4;reset_io();result(s,"0\n");assert(!trace_len);props[5].size=8;
 props[6].data="bogus";props[6].size=6;reset_io();result(s,"0\n");assert(!trace_len);
 props[6].data="dsi_hs_mode";props[6].size=12;reset_io();result(s,"1\n");assert(!(read_flags&MIPI_DSI_MSG_USE_LPM));
 u8 bad[9];memcpy(bad,status,sizeof(status));props[2].data=bad;
 bad[0]=0x39;reset_io();result(s,"0\n");assert(!trace_len);bad[0]=status[0];
 bad[3]=MIPI_DSI_MSG_BATCH_COMMAND;reset_io();result(s,"0\n");assert(!trace_len);bad[3]=0;
 bad[1]=0x41;reset_io();result(s,"0\n");assert(!trace_len);bad[1]=1;
 bad[2]=4;reset_io();result(s,"0\n");assert(!trace_len);bad[2]=0;
 bad[8]=0;props[2].size=9;reset_io();result(s,"0\n");assert(!trace_len);props[2].size=sizeof(status);props[2].data=status;
 props[2].size=6;reset_io();result(s,"0\n");assert(!trace_len);props[2].size=sizeof(status);
 u8 many[9*sizeof(status)];for(unsigned int i=0;i<9;i++)memcpy(many+i*sizeof(status),status,sizeof(status));props[2].data=many;props[2].size=sizeof(many);reset_io();result(s,"0\n");assert(!trace_len);
 struct myron_flat_set eight={.data=many,.length=8*sizeof(status)};assert(!myron_flat_validate_packets(&eight,true)&&eight.count==8);cases++;
 u8 oversized[7+257]={0x06,1,0,0,0,1,1};props[2].data=oversized;props[2].size=sizeof(oversized);reset_io();result(s,"0\n");assert(!trace_len);props[2].data=status;props[2].size=sizeof(status);
 /* Read-only attribute is present; no writable operation has been added. */
 assert(myron_clone_attrs[2]==&dev_attr_flatmode_check.attr);
 struct file file={0};struct inode inode={.i_cdev=&s->cdev};assert(!myron_clone_open(&inode,&file));
 myron_mi_clone_detach(&d);struct device retained={.data=s};reset_io();assert(flatmode_check_show(&retained,NULL,b)==-ENODEV);assert(!trace_len);assert(!myron_clone_release(NULL,&file));assert(!allocated_blocks);
 printf("PASS: %u flatmode actual-C I/O, parser, lock, cleanup and lifecycle cases\n",cases);
 return 0;
}
