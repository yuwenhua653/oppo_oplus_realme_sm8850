/* Entirely synthetic measurements. No device identifiers or capture logs. */
static int tests;
#define PASS(name) do{tests++;printf("PASS %02d %s\n",tests,name);}while(0)
static void reset(void){
 release_all();nr=reads=fail_at=monitored_form=register_error=refs=registrations=unregistrations=driver_adds=driver_dels=driver_error=probe_attempts=owner=release_count=0;
 compatible=capable=true;alloc_fail=existing_psy=auto_attach=false;registered_driver=NULL;
 values[0]=50;values[1]=4000;values[2]=2982;read_error=-EREMOTEIO;client.addr=0x55;client.dev.of_node=(void *)1;enable_readonly=true;enable_extended_readonly=false;values[3]=0;values[4]=0;
}
static int property(enum power_supply_property p,int *output){union power_supply_propval v={.intval=1234567};int r=myron_readonly_get_property(active_psy,p,&v);*output=v.intval;return r;}
static void start(void){auto_attach=true;assert(myron_readonly_init()==0&&driver_adds==1&&probe_attempts==1&&owner==2&&active_psy);}
static void extended_tests(void);
int main(void){int out;
 assert(!enable_readonly);assert(myron_readonly_init()==-EPERM&&driver_adds==0&&reads==0);PASS("compiled default off rejects module load before driver registration or I/O");
 assert(myron_readonly_probe(&client)==-EPERM&&reads==0&&nr==0);PASS("probe also refuses absent enable");
 reset();start();assert(reads==6);assert(!strcmp(registered_driver->driver.name,"myron_bq_readonly"));assert(!strcmp(active_psy->desc->name,"battery"));assert(active_psy->desc->num_properties==5&&active_psy->desc->no_thermal);assert(!active_psy->desc->set_property&&!active_psy->desc->property_is_writeable);PASS("explicit enable creates five-property read-only supply with ready callback context");
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
