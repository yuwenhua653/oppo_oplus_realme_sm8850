/* Entirely synthetic measurements. No device identifiers or capture logs. */
#include "production_under_test.c"
static int tests;
#define PASS(name) do{tests++;printf("PASS %02d %s\n",tests,name);}while(0)
static void reset(void){
 assert(usb_refs==0&&!usb_psy.dev.lock_held);
 release_all();nr=reads=fail_at=monitored_form=register_error=refs=registrations=unregistrations=driver_adds=driver_dels=driver_error=probe_attempts=owner=release_count=0;
 compatible=capable=true;alloc_fail=existing_psy=auto_attach=false;registered_driver=NULL;
 values[0]=50;values[1]=4000;values[2]=2982;read_error=-EREMOTEIO;client.addr=0x55;client.dev.of_node=(void *)1;enable_readonly=true;enable_extended_readonly=false;values[3]=0;values[4]=0;
 enable_status_readonly=false;client.data=NULL;usb_exists=false;usb_context_alive=true;usb_psy.removing=false;
 enable_manufacturer_query=false;query_capable=true;query_calls=query_delay_calls=0;query_results[0]=1;query_results[1]=2;memset(query_frame,0,sizeof(query_frame));
 usb_model="myron-mca-readonly";usb_status=POWER_SUPPLY_STATUS_CHARGING;usb_model_error=usb_status_error=usb_puts=usb_lookups=usb_model_calls=usb_status_calls=changed_calls=0;
 property_hook=NULL;changed_hook=NULL;
}
static void assert_no_gauge_lock(void){if(active_psy)assert(!((struct myron_readonly_gauge *)active_psy->drv_data)->lock.held);}
static void assert_query_lock(void){assert(nr==1&&resources[0].type==1&&!active_psy);assert(((struct myron_readonly_gauge *)resources[0].ptr)->lock.held);}
static int property(enum power_supply_property p,int *output){union power_supply_propval v={.intval=1234567};int r=myron_readonly_get_property(active_psy,p,&v);*output=v.intval;return r;}
static void start(void){auto_attach=true;assert(myron_readonly_init()==0&&driver_adds==1&&probe_attempts==1&&owner==2&&active_psy);}
static void extended_tests(void);
static void status_tests(void);
static void manufacturer_tests(void);
int main(void){int out;
 assert(!enable_readonly);assert(myron_readonly_init()==-EPERM&&driver_adds==0&&reads==0);PASS("compiled default off rejects module load before driver registration or I/O");
 assert(myron_readonly_probe(&client)==-EPERM&&reads==0&&nr==0);PASS("probe also refuses absent enable");
 reset();start();assert(reads==6);assert(!strcmp(registered_driver->driver.name,"myron_bq_readonly"));assert(!strcmp(active_psy->desc->name,"battery"));assert(active_psy->desc->num_properties==5&&!active_psy->desc->no_thermal);assert(!active_psy->desc->set_property&&!active_psy->desc->property_is_writeable);PASS("explicit enable creates five-property read-only supply with ready callback context");
 assert(property(POWER_SUPPLY_PROP_CAPACITY,&out)==0&&out==50);assert(property(POWER_SUPPLY_PROP_VOLTAGE_NOW,&out)==0&&out==4000000);assert(property(POWER_SUPPLY_PROP_TEMP,&out)==0&&out==251);PASS("synthetic sample units percent/uV/0.1C");
 values[0]=49;values[1]=4100;values[2]=3001;assert(property(POWER_SUPPLY_PROP_CAPACITY,&out)==0&&out==49);assert(property(POWER_SUPPLY_PROP_VOLTAGE_NOW,&out)==0&&out==4100000);assert(property(POWER_SUPPLY_PROP_TEMP,&out)==0&&out==270);PASS("fresh readings replace no cached or fabricated fields");
 values[2]=2731;assert(property(POWER_SUPPLY_PROP_TEMP,&out)==0&&out==-1);values[2]=2732;assert(property(POWER_SUPPLY_PROP_TEMP,&out)==0&&out==1);PASS("exact Kelvin offset and signed half-away rounding");
 values[2]=1452;assert(property(POWER_SUPPLY_PROP_TEMP,&out)==0&&out==-1280);values[2]=4011;assert(property(POWER_SUPPLY_PROP_TEMP,&out)==0&&out==1280);PASS("telemetry-valid temperature endpoints");
 values[2]=1451;assert(property(POWER_SUPPLY_PROP_CAPACITY,&out)==-ERANGE&&out==1234567);values[2]=4012;assert(property(POWER_SUPPLY_PROP_TEMP,&out)==-ERANGE&&out==1234567);PASS("bad temperature rejects whole sample without output modification");
 values[2]=2982;values[0]=0;values[1]=1;assert(property(POWER_SUPPLY_PROP_CAPACITY,&out)==0&&out==0);values[0]=100;values[1]=10000;assert(property(POWER_SUPPLY_PROP_VOLTAGE_NOW,&out)==0&&out==10000000);PASS("zero/full SOC and voltage bounds");
 values[0]=101;assert(property(POWER_SUPPLY_PROP_CAPACITY,&out)==-ERANGE&&out==1234567);values[0]=50;values[1]=0;assert(property(POWER_SUPPLY_PROP_CAPACITY,&out)==-ERANGE&&out==1234567);values[1]=10001;assert(property(POWER_SUPPLY_PROP_TEMP,&out)==-ERANGE&&out==1234567);PASS("SOC/zero-voltage/high-voltage reject without clamping");
 values[1]=4000;int invalid[]={32768,65535,INT_MAX};for(size_t i=0;i<ARRAY_SIZE(invalid);i++){values[2]=invalid[i];assert(property(POWER_SUPPLY_PROP_TEMP,&out)==-ERANGE&&out==1234567);}values[2]=2982;for(size_t i=0;i<ARRAY_SIZE(invalid);i++){values[1]=invalid[i];assert(property(POWER_SUPPLY_PROP_VOLTAGE_NOW,&out)==-ERANGE&&out==1234567);}PASS("invalid raw signed-domain/oversize words rejected before overflow");
 values[1]=4000;for(int n=1;n<=3;n++){reads=0;fail_at=n;read_error=n==1?-EIO:n==2?-EREMOTEIO:-ETIMEDOUT;assert(property(POWER_SUPPLY_PROP_CAPACITY,&out)==read_error&&out==1234567&&reads==n);}PASS("each read failure returns original errno and stops acquisition");
 for(int err=0;err<2;err++){reads=0;fail_at=1;read_error=err?-EHOSTDOWN:-ESHUTDOWN;assert(property(POWER_SUPPLY_PROP_TEMP,&out)==read_error&&out==1234567&&reads==1);}PASS("EHOSTDOWN/ESHUTDOWN adapter errors preserved without fake zero");
 reads=0;fail_at=0;assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_UNKNOWN);assert(property(POWER_SUPPLY_PROP_HEALTH,&out)==0&&out==POWER_SUPPLY_HEALTH_UNKNOWN);assert(reads==0);PASS("status/health unknown without unsupported measurement");
 assert(property(POWER_SUPPLY_PROP_PRESENT,&out)==-EINVAL&&out==1234567);assert(property(POWER_SUPPLY_PROP_CURRENT_NOW,&out)==-EINVAL&&out==1234567);for(size_t i=0;i<active_psy->desc->num_properties;i++)assert(active_psy->desc->properties[i]!=POWER_SUPPLY_PROP_PRESENT&&active_psy->desc->properties[i]!=POWER_SUPPLY_PROP_CURRENT_NOW);PASS("no PRESENT/current or unsupported getter fallback");
 int old_reads=reads;myron_readonly_exit();assert(driver_dels==1&&owner==0&&!active_psy&&unregistrations==1&&release_order[0]==2&&release_order[1]==1&&reads==old_reads);PASS("unregister before context free, removal performs no hardware I/O");
 reset();owner=1;auto_attach=true;assert(myron_readonly_init()==0&&owner==1&&probe_attempts==0&&reads==0&&!active_psy);myron_readonly_exit();assert(owner==1&&reads==0);PASS("bounded core model preserves pre-existing driver owner without probing");
 reset();driver_error=-ENOMEM;assert(myron_readonly_init()==-ENOMEM&&reads==0&&!registered_driver);PASS("driver registration failure preserved without I/O");
 reset();client.addr=0x54;assert(myron_readonly_probe(&client)==-ENODEV&&reads==0&&nr==0);PASS("wrong address refused before acquisition");
 reset();compatible=false;assert(myron_readonly_probe(&client)==-ENODEV&&reads==0);client.dev.of_node=NULL;assert(myron_readonly_probe(&client)==-ENODEV&&reads==0);PASS("wrong compatible/missing OF node refused");
 reset();capable=false;assert(myron_readonly_probe(&client)==-EOPNOTSUPP&&reads==0);PASS("adapter without SMBus word-read refused");
 for(int form=1;form<=3;form++){reset();monitored_form=form;assert(myron_readonly_probe(&client)==-EOPNOTSUPP&&nr==0&&reads==0&&!active_psy);}PASS("normal/empty/malformed monitored-battery all refused before core parsing");
 reset();existing_psy=true;assert(myron_readonly_probe(&client)==-EBUSY&&refs==0&&reads==0&&nr==0);PASS("existing battery supply retained and reference put");
 reset();alloc_fail=true;assert(myron_readonly_probe(&client)==-ENOMEM&&reads==0&&nr==0);PASS("allocation failure cannot publish a supply");
 for(int n=1;n<=3;n++){reset();fail_at=n;assert(myron_readonly_probe(&client)==-EREMOTEIO&&reads==n&&nr==1&&!active_psy);release_all();assert(release_order[0]==1);}PASS("every initial read error unwinds context on failed probe");
 reset();values[0]=101;assert(myron_readonly_probe(&client)==-ERANGE&&nr==1&&!active_psy);release_all();PASS("invalid initial sample never published");
 reset();register_error=-EEXIST;assert(myron_readonly_probe(&client)==-EEXIST&&nr==1&&!active_psy);release_all();PASS("racing same-name registration error retained with cleanup");
 reset();register_error=-ENOMEM;assert(myron_readonly_probe(&client)==-ENOMEM&&nr==1&&!active_psy);release_all();PASS("managed power-supply registration error retained with cleanup");
 reset();fail_at=4;assert(myron_readonly_probe(&client)==-EREMOTEIO&&nr==1&&!active_psy);release_all();PASS("register-time callback failure has initialized context and cleanup");
 extended_tests();
 manufacturer_tests();
 status_tests();
 printf("TOTAL %d standalone driver fixture groups passed\n",tests);return 0;
}

static ssize_t raw_status(char *buf){return battery_status_raw_show(&active_psy->dev,&dev_attr_battery_status_raw,buf);}
static void extended_tests(void){
 int out;char buf[4096];
 reset();enable_readonly=false;enable_extended_readonly=true;
 assert(myron_readonly_init()==-EPERM&&driver_adds==0&&reads==0);assert(myron_readonly_probe(&client)==-EPERM&&nr==0&&reads==0);
 PASS("extended flag alone refuses before register/probe/I2C");
 reset();start();assert(active_psy->groups==NULL&&active_psy->desc->num_properties==5&&reads==6);
 assert(myron_readonly_extended_word(active_psy->drv_data,0x0c)==-EOPNOTSUPP&&reads==6);
 assert(property(POWER_SUPPLY_PROP_CURRENT_NOW,&out)==-EINVAL&&out==1234567&&reads==6);
 PASS("original flag alone retains five properties and only original three commands");
 reset();enable_extended_readonly=true;start();
 assert(active_psy->desc->num_properties==6&&active_psy->groups==myron_readonly_diag_groups);
 assert(active_psy->groups[0]==&myron_readonly_diag_group&&active_psy->groups[1]==NULL);
 assert(!strcmp(active_psy->groups[0]->name,"myron_readonly_diag"));
 assert(dev_attr_battery_status_raw.attr.mode==0444&&dev_attr_battery_status_raw.store==NULL);
 assert(active_psy->groups[0]->attrs[0]==&dev_attr_battery_status_raw.attr&&active_psy->groups[0]->attrs[1]==NULL);
 assert(!active_psy->desc->set_property&&!active_psy->desc->property_is_writeable);
 assert(reads==6);PASS("both opt-ins expose current and one read-only raw-status group without extra probe reads");
 static const struct { int raw,ua; } pairs[]={ {0,0},{1,1000},{32767,32767000},{32768,-32768000},{65535,-1000},{65534,-2000} };
 for(size_t i=0;i<ARRAY_SIZE(pairs);i++){reads=0;values[3]=pairs[i].raw;assert(property(POWER_SUPPLY_PROP_CURRENT_NOW,&out)==0&&out==pairs[i].ua&&reads==1&&ports[0]==0x0c);}
 PASS("current signed16 conversion endpoints and all-ones valid negative measurement");
 for(int err=0;err<4;err++){reads=0;fail_at=1;read_error=err==0?-EIO:err==1?-ETIMEDOUT:err==2?-EHOSTDOWN:-EREMOTEIO;assert(property(POWER_SUPPLY_PROP_CURRENT_NOW,&out)==read_error&&out==1234567&&reads==1);assert(!((struct myron_readonly_gauge *)active_psy->drv_data)->lock.held);}
 PASS("current negative errno returned before cast with output unchanged and lock released");
 reads=0;fail_at=0;values[3]=65536;assert(property(POWER_SUPPLY_PROP_CURRENT_NOW,&out)==-ERANGE&&out==1234567&&reads==1);values[3]=INT_MAX;assert(property(POWER_SUPPLY_PROP_CURRENT_NOW,&out)==-ERANGE&&out==1234567);
 PASS("current impossible above-word values rejected rather than wrapping");
 values[3]=-EIO;values[4]=-EREMOTEIO;reads=0;
 assert(property(POWER_SUPPLY_PROP_CAPACITY,&out)==0&&out==50);assert(property(POWER_SUPPLY_PROP_VOLTAGE_NOW,&out)==0&&out==4000000);assert(property(POWER_SUPPLY_PROP_TEMP,&out)==0&&out==251);
 for(int i=0;i<9;i++)assert(ports[i]==(i%3==0?0x2c:i%3==1?0x08:0x06));
 PASS("unavailable new commands leave original SOC voltage temperature reads independent");
 values[0]=101;values[3]=42;reads=0;assert(property(POWER_SUPPLY_PROP_CURRENT_NOW,&out)==0&&out==42000&&reads==1);values[3]=-1;assert(property(POWER_SUPPLY_PROP_CURRENT_NOW,&out)==-1&&out==1234567);values[0]=50;
 PASS("current has no hidden dependency on original SOC sample and no successful cache");
 int flags[]={0,0x0080,0x0040,0x0020,0x0010,0x4000,0x0800,0x0200,0xffff};
 for(size_t i=0;i<ARRAY_SIZE(flags);i++){char want[32];snprintf(want,sizeof(want),"0x%04x\n",flags[i]);values[4]=flags[i];reads=0;strcpy(buf,"sentinel");assert(raw_status(buf)==7&&!strcmp(buf,want)&&reads==1&&ports[0]==0x0a);}
 PASS("raw BatteryStatus retains INIT DSG FC FD alarms and reserved bits without interpretation");
 for(int err=0;err<3;err++){reads=0;fail_at=1;read_error=err==0?-EIO:err==1?-ETIMEDOUT:-EHOSTDOWN;strcpy(buf,"sentinel");assert(raw_status(buf)==read_error&&!strcmp(buf,"sentinel")&&reads==1);assert(!((struct myron_readonly_gauge *)active_psy->drv_data)->lock.held);}
 fail_at=0;values[4]=65536;strcpy(buf,"sentinel");assert(raw_status(buf)==-ERANGE&&!strcmp(buf,"sentinel"));
 PASS("raw flags read errors and above-word returns preserved without buffer mutation");
 reads=0;assert(myron_readonly_extended_word(active_psy->drv_data,0x3e)==-EINVAL&&reads==0);assert(myron_readonly_extended_word(active_psy->drv_data,0x00)==-EINVAL&&reads==0);
 PASS("extended helper rejects commands outside exact 0x0a and 0x0c allowlist");
 values[4]=0xffff;values[3]=300;reads=0;
 assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_UNKNOWN);assert(property(POWER_SUPPLY_PROP_HEALTH,&out)==0&&out==POWER_SUPPLY_HEALTH_UNKNOWN&&reads==0);assert(property(POWER_SUPPLY_PROP_PRESENT,&out)==-EINVAL&&out==1234567);
 PASS("extended mode still does not infer charging health or presence from current or flags");
 int before=reads;myron_readonly_exit();assert(!active_psy&&release_order[0]==2&&release_order[1]==1&&reads==before);PASS("extended groups share supply cleanup before context release without removal I2C");
 reset();enable_extended_readonly=true;register_error=-EEXIST;assert(myron_readonly_probe(&client)==-EEXIST&&nr==1&&!active_psy);release_all();
 reset();enable_extended_readonly=true;existing_psy=true;assert(myron_readonly_probe(&client)==-EBUSY&&reads==0&&refs==0&&nr==0);
 PASS("extended registration/collision errors preserve original cleanup and ownership gates");
 reset();enable_extended_readonly=true;monitored_form=2;assert(myron_readonly_probe(&client)==-EOPNOTSUPP&&reads==0&&nr==0);release_all();
 PASS("extended mode never bypasses monitored-battery refusal");
}

static void status_start(void){reset();enable_extended_readonly=enable_status_readonly=true;usb_exists=true;start();reads=0;}
static pthread_mutex_t race_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t race_cond=PTHREAD_COND_INITIALIZER;
static bool race_started,race_finished,race_gauge;
static pthread_t removal_thread;
static void *racing_remove(void *unused){
 (void)unused;struct device *d=race_gauge?&active_psy->dev:&usb_psy.dev;
 /* Force the remover to observe the production reader/callback holding the barrier. */
 assert(pthread_mutex_trylock(&d->lock)==EBUSY);
 assert(!pthread_mutex_lock(&race_lock));race_started=true;assert(!pthread_cond_signal(&race_cond));assert(!pthread_mutex_unlock(&race_lock));
 if(race_gauge){myron_readonly_remove(&client);}else{device_lock(d);usb_psy.removing=true;usb_context_alive=false;device_unlock(d);}
 assert(!pthread_mutex_lock(&race_lock));race_finished=true;assert(!pthread_mutex_unlock(&race_lock));return NULL;
}
static void start_racing_remove(void){
 race_started=race_finished=false;
 assert(!pthread_create(&removal_thread,NULL,racing_remove,NULL));
 assert(!pthread_mutex_lock(&race_lock));while(!race_started)assert(!pthread_cond_wait(&race_cond,&race_lock));assert(!race_finished);assert(!pthread_mutex_unlock(&race_lock));
}
static void supplier_removal_hook(enum power_supply_property p){
 assert(p==POWER_SUPPLY_PROP_MODEL_NAME);property_hook=NULL;race_gauge=false;start_racing_remove();
}
static void consumer_removal_hook(void){changed_hook=NULL;race_gauge=true;start_racing_remove();}
static void status_tests(void){
 int out;
 reset();assert(!enable_status_readonly);start();usb_exists=true;
 assert(active_psy->desc==&myron_readonly_desc&&!active_psy->desc->external_power_changed);
 reads=0;assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_UNKNOWN&&reads==0&&usb_lookups==0);
 PASS("status opt-in defaults off and original descriptor performs no provider lookup or event forwarding");
 reset();enable_extended_readonly=true;start();usb_exists=true;
 assert(active_psy->desc==&myron_readonly_extended_desc&&!active_psy->desc->external_power_changed);
 reads=0;assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_UNKNOWN&&reads==0&&usb_lookups==0);
 PASS("extended-only mode retains unknown status without provider callback or lookup");
 for(int original=0;original<2;original++)for(int extended=0;extended<2;extended++){
  if(original&&extended)continue;reset();enable_readonly=original;enable_extended_readonly=extended;enable_status_readonly=true;
  assert(myron_readonly_init()==-EPERM&&driver_adds==0&&reads==0);assert(myron_readonly_probe(&client)==-EPERM&&nr==0&&reads==0&&usb_lookups==0);
 }
 PASS("status flag requires both earlier opt-ins before registration allocation or hardware access");
 status_start();assert(active_psy->desc==&myron_readonly_status_desc&&active_psy->desc->num_properties==6);
 assert(active_psy->desc->external_power_changed==myron_readonly_external_power_changed);
 assert(!active_psy->desc->set_property&&!active_psy->desc->property_is_writeable&&!active_psy->desc->no_thermal);
 assert(i2c_get_clientdata(&client)==active_psy->drv_data&&((struct myron_readonly_gauge *)active_psy->drv_data)->psy==active_psy);
 PASS("status opt-in selects separate read-only six-property descriptor with ready removal context");
 const int known[]={POWER_SUPPLY_STATUS_UNKNOWN,POWER_SUPPLY_STATUS_CHARGING,POWER_SUPPLY_STATUS_DISCHARGING,POWER_SUPPLY_STATUS_NOT_CHARGING,POWER_SUPPLY_STATUS_FULL};
 for(size_t i=0;i<ARRAY_SIZE(known);i++){usb_status=known[i];assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==known[i]&&usb_refs==0&&reads==0);}
 assert(usb_lookups==5&&usb_puts==5&&usb_model_calls==5&&usb_status_calls==5);
 PASS("all explicit Linux status enums forward with balanced provider refs and no I2C");
 const int invalid[]={-1,5,255,INT_MIN,INT_MAX};
 for(size_t i=0;i<ARRAY_SIZE(invalid);i++){usb_status=invalid[i];assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_UNKNOWN&&usb_refs==0&&reads==0);}
 PASS("invalid provider enum values become unknown without clamp or inference");
 status_start();usb_exists=false;
 assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_UNKNOWN&&usb_lookups==1&&usb_puts==0&&usb_model_calls==0&&usb_status_calls==0&&reads==0);
 PASS("missing usb provider returns unknown without a put on nonexistent reference");
 const char *models[]={NULL,"","other","myron-mca-readonly-extra","myron-mca-readonly ","MYRON-MCA-READONLY","myron-mca-readonl"};
 for(size_t i=0;i<ARRAY_SIZE(models);i++){status_start();usb_model=models[i];assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_UNKNOWN&&usb_model_calls==1&&usb_status_calls==0&&usb_refs==0&&usb_puts==1&&reads==0);}
 PASS("null truncated suffix case and unrelated provider models rejected before status dispatch");
 const int errors[]={-EINVAL,-ENODEV,-EAGAIN,-ENODATA,-ETIMEDOUT,-EIO};
 for(size_t i=0;i<ARRAY_SIZE(errors);i++){
  status_start();usb_model_error=errors[i];assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_UNKNOWN&&usb_status_calls==0&&usb_refs==0&&usb_puts==1);
  status_start();usb_status_error=errors[i];assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_UNKNOWN&&usb_status_calls==1&&usb_refs==0&&usb_puts==1);
 }
 PASS("model status stale unavailable and driver errors return unknown and put every reference");
 status_start();usb_status=POWER_SUPPLY_STATUS_CHARGING;assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_CHARGING);
 usb_status_error=-ENODATA;assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_UNKNOWN);
 usb_status_error=0;usb_status=POWER_SUPPLY_STATUS_DISCHARGING;assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_DISCHARGING);
 PASS("status never retains previously successful charge state across stale provider errors");
 status_start();usb_psy.removing=true;usb_context_alive=false;
 assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_UNKNOWN&&usb_model_calls==0&&usb_status_calls==0&&usb_puts==1&&usb_refs==0);
 PASS("already removing provider skips both callbacks without dereferencing freed context");
 status_start();property_hook=supplier_removal_hook;
 assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_CHARGING);assert(!pthread_join(removal_thread,NULL));
 assert(race_finished&&usb_psy.removing&&!usb_context_alive&&usb_refs==0&&usb_puts==1&&usb_model_calls==1&&usb_status_calls==1);
 assert(property(POWER_SUPPLY_PROP_STATUS,&out)==0&&out==POWER_SUPPLY_STATUS_UNKNOWN&&usb_model_calls==1&&usb_status_calls==1&&usb_refs==0&&usb_puts==2);
 PASS("supplier remove blocks through complete model and status read then subsequent query refuses dead context");
 status_start();reads=0;int lookups=usb_lookups;
 active_psy->desc->external_power_changed(active_psy);assert(changed_calls==1&&reads==0&&usb_lookups==lookups);
 void *saved=active_psy->drv_data;active_psy->drv_data=NULL;active_psy->desc->external_power_changed(active_psy);assert(changed_calls==2);active_psy->drv_data=saved;
 PASS("external change only schedules battery event without querying supply reading gauge or dereferencing context");
 changed_hook=consumer_removal_hook;active_psy->desc->external_power_changed(active_psy);assert(!pthread_join(removal_thread,NULL));
 assert(race_finished&&active_psy->removing&&changed_calls==3);active_psy->drv_data=NULL;
 active_psy->desc->external_power_changed(active_psy);assert(changed_calls==3&&reads==0&&usb_lookups==lookups);active_psy->drv_data=saved;
 PASS("gauge removal barrier drains prior event scheduling and prevents queue-after-cancel with no context access");
 status_start();reads=0;values[4]=0xffff;values[3]=123;
 assert(property(POWER_SUPPLY_PROP_HEALTH,&out)==0&&out==POWER_SUPPLY_HEALTH_UNKNOWN&&reads==0);
 assert(property(POWER_SUPPLY_PROP_PRESENT,&out)==-EINVAL&&out==1234567);assert(property(POWER_SUPPLY_PROP_ONLINE,&out)==-EINVAL&&out==1234567);
 assert(property(POWER_SUPPLY_PROP_MODEL_NAME,&out)==-EINVAL&&out==1234567);assert(usb_lookups==0);
 assert(property(POWER_SUPPLY_PROP_CURRENT_NOW,&out)==0&&out==123000&&reads==1&&ports[0]==0x0c);
 char buf[4096];assert(raw_status(buf)==7&&!strcmp(buf,"0xffff\n")&&reads==2&&ports[1]==0x0a);
 assert(property(POWER_SUPPLY_PROP_CAPACITY,&out)==0&&out==50&&reads==5);
 PASS("status mode preserves health unknown unsupported properties raw flags current and original sample restrictions");
 int before=reads;myron_readonly_exit();assert(!active_psy&&unregistrations==1&&release_order[0]==2&&release_order[1]==1&&reads==before&&usb_refs==0);
 PASS("status remove barrier keeps managed supply-before-context release without hardware access");
 reset();
}

static void manufacturer_frame(unsigned int length){
 assert(length>=7&&length<=36);memset(query_frame,0xa5,sizeof(query_frame));query_frame[0]=0x4c;query_frame[1]=0;query_frame[2]='M';query_frame[3]='I';query_frame[4]='C';query_frame[35]=length;unsigned int sum=0;
 for(unsigned int i=0;i<length-2;i++)sum+=query_frame[i];query_frame[34]=(u8)(0xff-(sum&0xff));
}
static void manufacturer_enable(void){reset();enable_extended_readonly=enable_manufacturer_query=true;manufacturer_frame(36);}
static void manufacturer_tests(void){
 char buf[4096];int out;struct myron_readonly_gauge *g;
 reset();assert(!enable_manufacturer_query);start();assert(query_calls==0&&query_delay_calls==0&&active_psy->groups==NULL);PASS("manufacturer query is compiled default-off and base probe makes no selector write");
 reset();enable_extended_readonly=true;start();assert(query_calls==0&&active_psy->groups==myron_readonly_diag_groups&&active_psy->groups[0]->attrs[1]==NULL);PASS("extended status ABI and original group remain exact when manufacturer query is off");
 reset();enable_manufacturer_query=true;assert(myron_readonly_init()==-EPERM&&driver_adds==0&&query_calls==0);assert(myron_readonly_probe(&client)==-EPERM&&nr==0&&reads==0&&query_calls==0);PASS("query refuses missing extended telemetry opt-in before registration or I2C");
 manufacturer_enable();enable_readonly=false;assert(myron_readonly_init()==-EPERM&&driver_adds==0&&query_calls==0);assert(myron_readonly_probe(&client)==-EPERM&&nr==0&&reads==0);PASS("query cannot bypass original master telemetry opt-in");
 manufacturer_enable();start();g=active_psy->drv_data;assert(!g->manufacturer_error&&g->manufacturer_length==32&&g->manufacturer_name[2]=='C');assert(query_calls==2&&query_delay_calls==1&&reads==6);assert(active_psy->groups==myron_manufacturer_diag_groups&&active_psy->groups[0]->attrs[0]==&dev_attr_battery_status_raw.attr&&active_psy->groups[0]->attrs[1]==&dev_attr_manufacturer_name.attr&&active_psy->groups[0]->attrs[2]==NULL);assert(!dev_attr_manufacturer_name.store&&dev_attr_manufacturer_name.attr.mode==0444);PASS("explicit query makes one fixed selector and one complete read under lock before publishing immutable diagnostic group");
 int old_queries=query_calls;for(int i=0;i<100;i++){assert(manufacturer_name_show(&active_psy->dev,&dev_attr_manufacturer_name,buf)>0);assert(strstr(buf,"command=0x004c valid=1 length=32 discriminator=0x43 payload=4d4943"));}assert(query_calls==old_queries);assert(property(POWER_SUPPLY_PROP_TEMP,&out)==0&&out==251);assert(query_calls==old_queries);PASS("repeated sysfs and power-supply reads never repeat manufacturer command or reinterpret raw identity");
 myron_readonly_exit();assert(query_calls==old_queries&&owner==0&&!active_psy);PASS("remove drains managed lifetime and makes no manufacturer hardware access");
 manufacturer_enable();manufacturer_frame(7);start();g=active_psy->drv_data;assert(!g->manufacturer_error&&g->manufacturer_length==3&&!memcmp(g->manufacturer_name,"MIC",3));for(unsigned int i=3;i<32;i++)assert(g->manufacturer_name[i]==0);assert(manufacturer_name_show(&active_psy->dev,&dev_attr_manufacturer_name,buf)>0&&!strcmp(buf,"command=0x004c valid=1 length=3 discriminator=0x43 payload=4d4943\n"));PASS("minimum complete three-byte identity preserves real payload length without leaking frame padding");
 manufacturer_enable();query_capable=false;start();g=active_psy->drv_data;assert(g->manufacturer_error==-EOPNOTSUPP&&query_calls==0&&query_delay_calls==0&&g->manufacturer_length==0);assert(manufacturer_name_show(&active_psy->dev,&dev_attr_manufacturer_name,buf)>0&&!strcmp(buf,"command=0x004c valid=0 error=-95\n"));assert(property(POWER_SUPPLY_PROP_CAPACITY,&out)==0&&out==50);PASS("unsupported raw-I2C query is diagnosed while original battery telemetry remains available");
 const int faults[]={-EIO,-ETIMEDOUT,-EREMOTEIO,0,2,3};for(unsigned int i=0;i<ARRAY_SIZE(faults);i++){manufacturer_enable();query_results[0]=faults[i];start();g=active_psy->drv_data;assert(g->manufacturer_error==(faults[i]<0?faults[i]:-EIO)&&query_calls==1&&query_delay_calls==0&&g->manufacturer_length==0);for(int j=0;j<32;j++)assert(g->manufacturer_name[j]==0);assert(property(POWER_SUPPLY_PROP_CAPACITY,&out)==0&&out==50);}PASS("all selector failures and non-exact counts stop without retry read publication or battery failure");
 const int read_faults[]={-EIO,-ETIMEDOUT,-EREMOTEIO,0,1,3};for(unsigned int i=0;i<ARRAY_SIZE(read_faults);i++){manufacturer_enable();query_results[1]=read_faults[i];start();g=active_psy->drv_data;assert(g->manufacturer_error==(read_faults[i]<0?read_faults[i]:-EIO)&&query_calls==2&&query_delay_calls==1&&g->manufacturer_length==0);for(int j=0;j<32;j++)assert(g->manufacturer_name[j]==0);}PASS("partial or failed frame reads cannot publish even when returned buffer contains a plausible identity");
 for(int kind=0;kind<4;kind++){manufacturer_enable();if(kind==0)query_frame[0]=0x4d;if(kind==1)query_frame[35]=6;if(kind==2)query_frame[35]=37;if(kind==3)query_frame[34]^=1;start();g=active_psy->drv_data;assert(g->manufacturer_error==(kind==3?-EBADMSG:-EPROTO)&&g->manufacturer_length==0);assert(manufacturer_name_show(&active_psy->dev,&dev_attr_manufacturer_name,buf)>0&&strstr(buf,"valid=0 error="));assert(!strstr(buf,"payload=")&&!strstr(buf,"discriminator="));}PASS("wrong command malformed lengths and bad checksum expose only failure without valid raw or invented variant");
 manufacturer_enable();existing_psy=true;assert(myron_readonly_probe(&client)==-EBUSY&&query_calls==0&&reads==0);manufacturer_enable();alloc_fail=true;assert(myron_readonly_probe(&client)==-ENOMEM&&query_calls==0);manufacturer_enable();fail_at=2;assert(myron_readonly_probe(&client)==-EREMOTEIO&&query_calls==0);release_all();PASS("existing owner allocation and base sample failures all precede manufacturer transaction");
 manufacturer_enable();register_error=-EEXIST;assert(myron_readonly_probe(&client)==-EEXIST&&query_calls==2&&!active_psy);release_all();assert(release_order[0]==1);PASS("post-query PSY publication failure releases context without retry and cannot expose diagnostic");
 reset();
}
