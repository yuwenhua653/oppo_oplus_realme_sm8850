static void parser_cases(void) {
 char text[80];u8 out[32],before[32];unsigned count;
 const char *valid[] = {"00","09","AF","af","Ff","0123456789ABCDEFabcdef"};
 for(unsigned k=0;k<sizeof(valid)/sizeof(valid[0]);k++) { memset(out,0xa5,32);count=99;CHECK(StringToHex((char *)valid[k],out,&count)==(int)strlen(valid[k])/2);CHECK(count==strlen(valid[k])/2);group(); }
 const char *bad[]={"","0","000","0g","g0","0/",":0","@0","G0","`0","\x7f""0","0\n"};
 for(unsigned k=0;k<sizeof(bad)/sizeof(bad[0]);k++) { memset(out,0xa5,32);memcpy(before,out,32);count=99;CHECK(StringToHex((char *)bad[k],out,&count)==-EINVAL);CHECK(!memcmp(out,before,32)&&count==99);group(); }
 memset(text,'0',sizeof(text));text[66]=0;count=99;memset(out,0xa5,32);memcpy(before,out,32);CHECK(StringToHex(text,out,&count)==-EINVAL);CHECK(count==99&&!memcmp(out,before,32));group();
 CHECK(StringToHex(NULL,out,&count)==-EINVAL);CHECK(StringToHex("00",NULL,&count)==-EINVAL);CHECK(StringToHex("00",out,NULL)==-EINVAL);group();
 for(unsigned pos=0;pos<64;pos++) for(unsigned byte=1;byte<128;byte++) {
  memset(text,'0',64);text[64]=0;text[pos]=(char)byte;memset(out,0xa5,32);memcpy(before,out,32);count=99;
  bool ok=(byte>='0'&&byte<='9')||(byte>='A'&&byte<='F')||(byte>='a'&&byte<='f');
  int ret=StringToHex(text,out,&count);CHECK(ok?(ret==32&&count==32):(ret==-EINVAL&&count==99&&!memcmp(out,before,32)));group();
 }
}
static void auth_basic_cases(void) {
 struct bq_fg_chip b;struct i2c_client c;u8 rand[32],before[32];for(unsigned i=0;i<32;i++)rand[i]=(u8)i;
 reset_bus();init_chip(&b,&c);CHECK(fg_sha256_auth(&b,rand,32)==0);CHECK(write_calls==1&&read_calls==1&&sleep_calls==1);CHECK(last_challenge[0]==0&&last_challenge[1]==0&&!memcmp(last_challenge+2,rand,32));CHECK(last_challenge[34]==checksum(rand,32)&&last_challenge[35]==0x24);for(unsigned i=0;i<32;i++)CHECK(b.digest[i]==(u8)((rand[0]^0xa5)+i));CHECK(atomic_read(&b.digest_in_process)==0);destroy_chip(&b);group();
 int failures[]={-EREMOTEIO,-ETIMEDOUT,0,1,2,3};
 for(unsigned k=0;k<sizeof(failures)/sizeof(failures[0]);k++) { if(failures[k]==1)continue;reset_bus();init_chip(&b,&c);memcpy(before,b.digest,32);write_result=failures[k];CHECK(fg_sha256_auth(&b,rand,32)==(failures[k]<0?failures[k]:-EIO));CHECK(!read_calls&&!sleep_calls&&!memcmp(before,b.digest,32));CHECK(!atomic_read(&b.digest_in_process));destroy_chip(&b);group(); }
 for(unsigned k=0;k<sizeof(failures)/sizeof(failures[0]);k++) { if(failures[k]==2)continue;reset_bus();init_chip(&b,&c);memcpy(before,b.digest,32);read_result=failures[k];CHECK(fg_sha256_auth(&b,rand,32)==(failures[k]<0?failures[k]:-EIO));CHECK(read_calls==1&&sleep_calls==1&&!memcmp(before,b.digest,32));CHECK(!atomic_read(&b.digest_in_process));destroy_chip(&b);group(); }
 reset_bus();init_chip(&b,&c);atomic_set(&b.pm_suspend,1);CHECK(fg_sha256_auth(&b,rand,32)==-EAGAIN);CHECK(!write_calls&&!read_calls);destroy_chip(&b);group();
 reset_bus();init_chip(&b,&c);for(int n=-2;n<=35;n++) if(n!=32) { CHECK(fg_sha256_auth(&b,rand,n)==-EINVAL);CHECK(!write_calls&&!read_calls);group(); }CHECK(fg_sha256_auth(NULL,rand,32)==-EINVAL);CHECK(fg_sha256_auth(&b,NULL,32)==-EINVAL);b.client=NULL;CHECK(fg_sha256_auth(&b,rand,32)==-ENODEV);b.client=&c;c.adapter=NULL;CHECK(fg_sha256_auth(&b,rand,32)==-ENODEV);destroy_chip(&b);group();
}
static void setter_cases(void) {
 struct bq_fg_chip b;struct i2c_client c;char text[70];u8 before[32];
 reset_bus();init_chip(&b,&c);memset(text,'0',64);text[64]=0;CHECK(set_verify_digest(&b,(u8 *)text)==0);CHECK(write_calls==1&&read_calls==1);destroy_chip(&b);group();
 reset_bus();init_chip(&b,&c);memset(text,'F',64);text[64]='\n';text[65]=0;CHECK(set_verify_digest(&b,(u8 *)text)==0);for(unsigned i=0;i<32;i++)CHECK(last_challenge[i+2]==0xff);destroy_chip(&b);group();
 for(unsigned n=0;n<=67;n++) { if(n==64)continue;reset_bus();init_chip(&b,&c);memcpy(before,b.digest,32);memset(text,'0',n);text[n]=0;CHECK(set_verify_digest(&b,(u8 *)text)==-EINVAL);CHECK(!write_calls&&!memcmp(b.digest,before,32));destroy_chip(&b);group(); }
 for(unsigned pos=0;pos<64;pos++) { reset_bus();init_chip(&b,&c);memset(text,'0',64);text[pos]='G';text[64]=0;CHECK(set_verify_digest(&b,(u8 *)text)==-EINVAL);CHECK(!write_calls);destroy_chip(&b);group(); }
 reset_bus();init_chip(&b,&c);memset(text,'0',64);text[64]=0;write_result=-ETIMEDOUT;CHECK(set_verify_digest(&b,(u8 *)text)==-ETIMEDOUT);CHECK(!read_calls);CHECK(set_verify_digest(NULL,(u8 *)text)==-EINVAL&&set_verify_digest(&b,NULL)==-EINVAL);destroy_chip(&b);group();
}
static void mode_cases(void) {
 struct bq_fg_chip b;struct i2c_client c;
 reset_bus();init_chip(&b,&c);atomic_set(&b.digest_in_process,1);CHECK(fg_set_fastcharge_mode(&b,true)==0);CHECK(mode_calls==1&&b.fast_mode);CHECK(last_mode_cmd==0x3e&&last_mode_len==2&&last_mode_data[0]==1&&last_mode_data[1]==0);CHECK(fg_set_fastcharge_mode(&b,true)==0&&mode_calls==1);CHECK(fg_set_fastcharge_mode(&b,false)==0&&mode_calls==2&&!b.fast_mode);CHECK(last_mode_cmd==0x3f&&last_mode_len==2&&last_mode_data[0]==0&&last_mode_data[1]==0);destroy_chip(&b);group();
 int fails[]={-EIO,-EREMOTEIO,1};for(unsigned k=0;k<3;k++) { reset_bus();init_chip(&b,&c);mode_result=fails[k];CHECK(fg_set_fastcharge_mode(&b,true)==(fails[k]<0?fails[k]:-EIO));CHECK(!b.fast_mode&&mode_calls==1);mode_result=0;CHECK(!fg_set_fastcharge_mode(&b,true)&&b.fast_mode&&mode_calls==2);mode_result=-EIO;CHECK(fg_set_fastcharge_mode(&b,false)==-EIO&&b.fast_mode);destroy_chip(&b);group(); }
 reset_bus();init_chip(&b,&c);b.fg_vendor=MPC7021;CHECK(!fg_set_fastcharge_mode(&b,true));CHECK(last_mode_len==0&&last_mode_cmd==0x3e);CHECK(!fg_set_fastcharge_mode(&b,false));CHECK(last_mode_len==0&&last_mode_cmd==0x3f);CHECK(fg_set_fastcharge_mode(NULL,true)==-EINVAL);destroy_chip(&b);group();
}
static void getter_force_cases(void) {
 struct bq_fg_chip b;struct i2c_client c;char text[70];reset_bus();init_chip(&b,&c);for(unsigned i=0;i<32;i++)b.digest[i]=(u8)i;memset(text,'x',70);CHECK(get_verify_digest(&b,text)==65);CHECK(!strcmp(text,"000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"));CHECK(text[65]=='x');CHECK(get_verify_digest(NULL,text)==-EINVAL&&get_verify_digest(&b,NULL)==-EINVAL);fg_set_force_report_full(&b);CHECK(write_calls==1);fg_set_force_report_full(NULL);destroy_chip(&b);group();
}
struct call { struct bq_fg_chip *b;int rc;char digest[65];unsigned id;u8 challenge[32]; };
static void done(void) { lock_state();finished|=1u<<actor;CHECK(pthread_cond_broadcast(&state_cond)==0);unlock_state(); }
static void *auth_thread(void *v) { struct call *c=v;actor=c->id;c->rc=fg_sha256_auth(c->b,c->challenge,32);done();return NULL; }
static void *raw_thread(void *v) { struct call *c=v;actor=c->id;u8 b[2]={0x31,0};c->rc=fg_write_block(c->b,0x3e,b,2);done();return NULL; }
static void *mode_thread(void *v) { struct call *c=v;actor=c->id;c->rc=fg_set_fastcharge_mode(c->b,true);done();return NULL; }
static void *get_thread(void *v) { struct call *c=v;actor=c->id;c->rc=get_verify_digest(c->b,c->digest);done();return NULL; }
static void timed_wait(void) { struct timespec ts;CHECK(clock_gettime(CLOCK_REALTIME,&ts)==0);ts.tv_sec+=5;CHECK(pthread_cond_timedwait(&state_cond,&state_lock,&ts)==0); }
static void concurrency_cases(void) {
 for(unsigned iter=0;iter<16;iter++) {
  struct bq_fg_chip b;struct i2c_client c;pthread_t a,r,m,g;struct call ca={.b=&b,.id=10},cr={.b=&b,.id=11},cm={.b=&b,.id=12},cg={.b=&b,.id=13};
  memset(ca.challenge,(int)iter,32);reset_bus();init_chip(&b,&c);pause_armed=true;CHECK(!pthread_create(&a,NULL,auth_thread,&ca));
  lock_state();while(!pause_entered)timed_wait();unlock_state();
  CHECK(pthread_mutex_trylock(&b.data_lock.raw)==EBUSY);CHECK(pthread_mutex_trylock(&b.i2c_rw_lock.raw)==EBUSY);CHECK(atomic_read(&b.digest_in_process)==1);
  CHECK(!pthread_create(&r,NULL,raw_thread,&cr));CHECK(!pthread_create(&m,NULL,mode_thread,&cm));CHECK(!pthread_create(&g,NULL,get_thread,&cg));
  lock_state();unsigned mask=(1u<<11)|(1u<<12)|(1u<<13);while((attempted&mask)!=mask)timed_wait();CHECK(!(finished&mask));CHECK(wire_count==1);pause_release=true;CHECK(!pthread_cond_broadcast(&state_cond));unlock_state();
  CHECK(!pthread_join(a,NULL));CHECK(!pthread_join(r,NULL));CHECK(!pthread_join(m,NULL));CHECK(!pthread_join(g,NULL));CHECK(ca.rc==0&&cr.rc==1&&cm.rc==0&&cg.rc==65&&b.fast_mode);CHECK(wire_count==4&&wire_actor[0]==10&&wire_kind[0]==1&&wire_actor[1]==10&&wire_kind[1]==2);CHECK(!atomic_read(&b.digest_in_process));char expected[65];CHECK(get_verify_digest(&b,expected)==65);CHECK(!memcmp(expected,cg.digest,65));destroy_chip(&b);group();
 }
 /* Two digest requests cannot overwrite each other's challenge window. */
 struct bq_fg_chip b;struct i2c_client c;pthread_t t1,t2;struct call first={.b=&b,.id=10},second={.b=&b,.id=20};memset(first.challenge,0x11,32);memset(second.challenge,0x22,32);reset_bus();init_chip(&b,&c);pause_armed=true;CHECK(!pthread_create(&t1,NULL,auth_thread,&first));lock_state();while(!pause_entered)timed_wait();unlock_state();CHECK(!pthread_create(&t2,NULL,auth_thread,&second));lock_state();while(!(attempted&(1u<<20)))timed_wait();CHECK(wire_count==1);pause_release=true;CHECK(!pthread_cond_broadcast(&state_cond));unlock_state();CHECK(!pthread_join(t1,NULL)&&!pthread_join(t2,NULL));CHECK(first.rc==0&&second.rc==0&&wire_count==4);CHECK(wire_actor[0]==10&&wire_actor[1]==10&&wire_actor[2]==20&&wire_actor[3]==20);destroy_chip(&b);group();
}
static void original_negative(const char *name) {
 struct bq_fg_chip b;struct i2c_client c;u8 challenge[32]={0},before[32];reset_bus();init_chip(&b,&c);
 if(!strcmp(name,"busy-drop")) { atomic_set(&b.digest_in_process,1);CHECK(fg_set_fastcharge_mode(&b,true)==0);CHECK(mode_calls==1&&b.fast_mode); }
 else if(!strcmp(name,"short-auth")) { require_locked_sleep=false;write_result=0;CHECK(fg_sha256_auth(&b,challenge,32)==-EIO); }
 else if(!strcmp(name,"digest-publication")) { require_locked_sleep=false;read_result=-EREMOTEIO;memcpy(before,b.digest,32);CHECK(fg_sha256_auth(&b,challenge,32)==-EREMOTEIO);CHECK(!memcmp(before,b.digest,32)); }
 else if(!strcmp(name,"auth-error-propagation")) { char hex[65];memset(hex,'0',64);hex[64]=0;write_result=-ETIMEDOUT;CHECK(set_verify_digest(&b,(u8 *)hex)==-ETIMEDOUT); }
 else CHECK(0);
 destroy_chip(&b);
}
int main(int argc,char **argv) {
 if(argc==2) { original_negative(argv[1]);return 0; }
 parser_cases();auth_basic_cases();setter_cases();mode_cases();getter_force_cases();concurrency_cases();printf("PASS production control functions: %u groups\n",groups);return 0;
}
