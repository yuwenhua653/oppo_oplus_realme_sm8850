/* Entirely synthetic measurements. No device identifiers or capture logs. */
static int tests;
#define PASS(name) do{tests++;printf("PASS %02d %s\n",tests,name);}while(0)
static void reset(void){
 release_all();nr=reads=fail_at=monitored_form=register_error=refs=registrations=unregistrations=driver_adds=driver_dels=driver_error=probe_attempts=owner=release_count=0;
 compatible=capable=true;alloc_fail=existing_psy=auto_attach=false;registered_driver=NULL;
 values[0]=50;values[1]=4000;values[2]=2982;read_error=-EREMOTEIO;client.addr=0x55;client.dev.of_node=(void *)1;enable_readonly=true;
}
static int property(enum power_supply_property p,int *output){union power_supply_propval v={.intval=1234567};int r=myron_readonly_get_property(active_psy,p,&v);*output=v.intval;return r;}
static void start(void){auto_attach=true;assert(myron_readonly_init()==0&&driver_adds==1&&probe_attempts==1&&owner==2&&active_psy);}
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
 printf("TOTAL %d standalone driver fixture groups passed\n",tests);return 0;
}
