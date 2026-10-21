static unsigned long cases;
#define CHECK(x) do { cases++;assert(x); } while(0)
static void frame(unsigned length,u16 cmd){memset(reply,0x53,sizeof(reply));reply[0]=cmd;reply[1]=cmd>>8;reply[35]=length;if(length>=4&&length<=36)reply[34]=checksum(reply,length-2);}
static void matrix(struct bq_fg_chip *bq){
 for(unsigned length=0;length<=32;length++)for(unsigned cap=0;cap<=33;cap++)for(unsigned min=0;min<=33;min++){
  u8 out[40],actual=0xa5;memset(out,0xa5,sizeof(out));reset();frame(length+4,0x4c);
  int r=fg_mac_read_block_variable(bq,0x4c,out,cap,min,&actual);
  bool valid=cap>0&&cap<=32&&min>0&&min<=cap&&length>=min&&length<=cap;
  CHECK((r==0)==valid);
  if(valid){CHECK(actual==length);CHECK(!memcmp(out,reply+2,length));for(unsigned k=length;k<sizeof(out);k++)CHECK(out[k]==0xa5);}
  else{CHECK(actual==0xa5);for(unsigned k=0;k<sizeof(out);k++)CHECK(out[k]==0xa5);}
 }
 for(unsigned length=0;length<256;length++){
  u8 out[32],actual=0x5a;memset(out,0x5a,sizeof(out));reset();frame(length,0x4c);
  int r=fg_mac_read_block_variable(bq,0x4c,out,32,3,&actual);
  CHECK((r==0)==(length>=7&&length<=36));
  if(r){CHECK(actual==0x5a);for(unsigned k=0;k<32;k++)CHECK(out[k]==0x5a);}
 }
 for(unsigned byte=0;byte<2;byte++)for(unsigned v=0;v<256;v++){
  reset();frame(20,0x4c);reply[byte]=v;reply[34]=checksum(reply,18);u8 out[32],actual=77;memset(out,77,sizeof(out));
  int r=fg_mac_read_block_variable(bq,0x4c,out,32,3,&actual);CHECK((r==0)==(v==(byte?0:0x4c)));if(r)CHECK(actual==77);
 }
 for(unsigned byte=0;byte<35;byte++)for(unsigned bit=0;bit<8;bit++){
  reset();frame(36,0x4c);reply[byte]^=1<<bit;u8 out[32],actual=77;memset(out,77,sizeof(out));
  CHECK(fg_mac_read_block_variable(bq,0x4c,out,32,3,&actual)<0);CHECK(actual==77);
 }
 for(unsigned len=1;len<=32;len++){
  reset();frame(36,0x4c);u8 out[40];memset(out,99,sizeof(out));CHECK(fg_mac_read_block(bq,0x4c,out,len)==0);CHECK(!memcmp(out,reply+2,len));for(unsigned k=len;k<40;k++)CHECK(out[k]==99);
 }
}
static void transport(struct bq_fg_chip *bq){
 const int bad[]={0,1,3,-EIO,-ETIMEDOUT};
 for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++){
  reset();frame(20,0x4c);u8 out[36];memset(out,0x5a,sizeof(out));for(int k=0;k<3;k++)returns[k]=bad[i];return_n=3;
  CHECK(__fg_read_block(bq->client,0x3e,out,sizeof(out))<0);CHECK(wire_n==3);for(unsigned k=0;k<36;k++)CHECK(out[k]==0x5a);
 }
 reset();frame(20,0x4c);u8 out[36];memset(out,0x5a,sizeof(out));returns[0]=1;returns[1]=2;return_n=2;CHECK(__fg_read_block(bq->client,0x3e,out,36)==2);CHECK(wire_n==2);CHECK(!memcmp(out,reply,36));
 reset();u8 value[2]={1,0};returns[0]=returns[1]=returns[2]=0;return_n=3;CHECK(fg_mac_write_block(bq,0x3e,value,2)==-EIO);CHECK(wire_n==3);for(int k=0;k<wire_n;k++)CHECK(wires[k].reg==0x3e);
 reset();returns[0]=1;returns[1]=returns[2]=returns[3]=0;return_n=4;CHECK(fg_mac_write_block(bq,0x3e,value,2)==-EIO);CHECK(wire_n==4);
 reset();CHECK(fg_mac_write_block(bq,0x3e,value,2)==0);CHECK(wire_n==2);CHECK(wires[0].reg==0x3e&&wires[1].reg==0x60);CHECK(wires[0].payload[0]==0x3e&&wires[0].payload[1]==0&&wires[0].payload[2]==1&&wires[0].payload[3]==0);CHECK(wires[1].payload[1]==6);
}
static void *auth_thread(void *arg){actor=1;u8 challenge[32];memset(challenge,0xa7,sizeof(challenge));int r=fg_sha256_auth(arg,challenge,32);return (void *)(intptr_t)r;}
static void *ffc_thread(void *arg){actor=2;int r=fg_set_fastcharge_mode(arg,true);return(void *)(intptr_t)r;}
static void *raw_thread(void *arg){actor=3;struct bq_fg_chip *bq=arg;u8 raw[2]={0x31,0};int ret=fg_write_block(bq,bq->regs[BQ_FG_REG_ALT_MAC],raw,2);return(void *)(intptr_t)(ret==1?0:ret);}
static void concurrency(struct bq_fg_chip *bq){
 reset();memset(bq->digest,0x11,32);memset(digest_reply,0xa2,32);auth_pause=1;bq->fast_mode=false;
 pthread_t auth,ffc,raw;CHECK(!pthread_create(&auth,NULL,auth_thread,bq));pthread_mutex_lock(&phase_mutex);while(!auth_paused)pthread_cond_wait(&phase_cond,&phase_mutex);pthread_mutex_unlock(&phase_mutex);
 CHECK(wire_n==1);CHECK(atomic_load(&bq->digest_in_process)==1);CHECK(!pthread_create(&ffc,NULL,ffc_thread,bq));CHECK(!pthread_create(&raw,NULL,raw_thread,bq));
 pthread_mutex_lock(&phase_mutex);while(waiters<2)pthread_cond_wait(&phase_cond,&phase_mutex);CHECK(wire_n==1);CHECK(!bq->fast_mode);auth_release=1;pthread_cond_broadcast(&phase_cond);pthread_mutex_unlock(&phase_mutex);
 void *ret;CHECK(!pthread_join(auth,&ret)&&ret==NULL);CHECK(!pthread_join(ffc,&ret)&&ret==NULL);CHECK(!pthread_join(raw,&ret));CHECK(wire_n==5);CHECK(wires[0].actor==1&&wires[0].reg==0x3e&&!wires[0].read);CHECK(wires[1].actor==1&&wires[1].reg==0x40&&wires[1].read);CHECK(!memcmp(bq->digest,digest_reply,32));CHECK(bq->fast_mode);CHECK(!atomic_load(&bq->digest_in_process));
 reset();bq->fast_mode=false;returns[0]=returns[1]=returns[2]=-ETIMEDOUT;return_n=3;CHECK(fg_set_fastcharge_mode(bq,true)==-ETIMEDOUT);CHECK(!bq->fast_mode);
 reset();u8 challenge[32]={0};memset(bq->digest,0x19,32);returns[0]=1;returns[1]=returns[2]=returns[3]=1;return_n=4;CHECK(fg_sha256_auth(bq,challenge,32)==-EIO);for(unsigned k=0;k<32;k++)CHECK(bq->digest[k]==0x19);CHECK(!atomic_load(&bq->digest_in_process));
}
static void parse_cases(struct bq_fg_chip *bq){
 char input[70];u8 out[32];unsigned int length;
 for(unsigned pos=0;pos<64;pos++)for(unsigned v=1;v<256;v++){
  memset(input,'0',64);input[64]=0;input[pos]=v;memset(out,0x39,32);length=0xabcdef;
  bool hex=(v>='0'&&v<='9')||(v>='a'&&v<='f')||(v>='A'&&v<='F');int ret=StringToHex(input,out,&length);CHECK((ret==32)==hex);if(!hex){CHECK(length==0xabcdef);for(unsigned k=0;k<32;k++)CHECK(out[k]==0x39);}else{unsigned nibble=v<='9'?v-'0':(v<='F'?v-'A'+10:v-'a'+10);CHECK(length==32);for(unsigned k=0;k<32;k++)CHECK(out[k]==(k==pos/2?(pos&1?nibble:nibble<<4):0));}
 }
 for(unsigned length2=0;length2<70;length2++){
  memset(input,'0',sizeof(input));input[length2]=0;reset();int ret=set_verify_digest(bq,(u8*)input);CHECK((ret==0)==(length2==64));if(length2!=64)CHECK(wire_n==0);
 }
 memset(input,'0',64);input[64]='\n';input[65]=0;reset();CHECK(set_verify_digest(bq,(u8*)input)==0);CHECK(wire_n==2);
 char digest[66];memset(bq->digest,0xab,32);CHECK(get_verify_digest(bq,digest)==65);for(unsigned i=0;i<64;i++)CHECK(digest[i]==(i&1?'b':'a'));CHECK(digest[64]==0);
}
int main(void){struct bq_fg_chip bq;init_chip(&bq);matrix(&bq);transport(&bq);concurrency(&bq);parse_cases(&bq);finish_chip(&bq);printf("PASS peer assertions=%lu\n",cases);return 0;}
