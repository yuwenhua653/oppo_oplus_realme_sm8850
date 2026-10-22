static void *set_thread(void *data) { int ret=fg_set_fastcharge_mode(data,true); return (void *)(intptr_t)ret; }
struct getter_call { struct bq_fg_chip *b; int out,ret; };
static void *get_thread(void *data) { struct getter_call *call=data;getter_actor=true;call->ret=fg_get_fastcharge_mode(call->b,&call->out);atomic_store(&getter_done,true);return NULL; }
static void negative(const char *which) {
 struct bq_fg_chip b;init_chip(&b);reset_wire();
 if (!strcmp(which,"cold-disable")) { CHECK(fg_set_fastcharge_mode(&b,false)==0);CHECK(mode_calls==1); }
 else if (!strcmp(which,"unknown-getter")) { int out=87;CHECK(fg_get_fastcharge_mode(&b,&out)==-EAGAIN);CHECK(out==87); }
 else if (!strcmp(which,"unknown-sysfs")) { char out[PAGE_SIZE];memset(out,0x5a,sizeof(out));CHECK(fast_mode_sysfs(&b,out)==-EAGAIN);CHECK(out[0]==0x5a); }
 else abort();
 finish_chip(&b);
}
static void normal(void) {
 struct bq_fg_chip b;init_chip(&b);reset_wire();int out=87;char buf[PAGE_SIZE];memset(buf,0x5a,sizeof(buf));
 CHECK(fg_get_fastcharge_mode(&b,&out)==-EAGAIN);CHECK(out==87);CHECK(fast_mode_sysfs(&b,buf)==-EAGAIN);CHECK(buf[0]==0x5a);
 CHECK(fg_get_fastcharge_mode(NULL,&out)==-EINVAL);CHECK(fg_get_fastcharge_mode(&b,NULL)==-EINVAL);CHECK(fg_set_fastcharge_mode(NULL,false)==-EINVAL);
 CHECK(fg_set_fastcharge_mode(&b,false)==0);CHECK(mode_calls==1);CHECK(last_cmd==0x3f&&last_len==2&&last_data[0]==0&&last_data[1]==0);CHECK(b.fast_mode_valid&&!b.fast_mode);
 CHECK(!fg_get_fastcharge_mode(&b,&out)&&out==0);CHECK(fast_mode_sysfs(&b,buf)==2&&!strcmp(buf,"0\n"));
 CHECK(!fg_set_fastcharge_mode(&b,false)&&mode_calls==1);
 CHECK(!fg_set_fastcharge_mode(&b,true));CHECK(mode_calls==2&&b.fast_mode&&b.fast_mode_valid);CHECK(last_cmd==0x3e&&last_len==2&&last_data[0]==1&&last_data[1]==0);
 CHECK(!fg_set_fastcharge_mode(&b,true)&&mode_calls==2);
 const int fails[]={-EIO,-ETIMEDOUT,1};
 for (unsigned k=0;k<sizeof(fails)/sizeof(fails[0]);k++) { mode_result=fails[k];CHECK(fg_set_fastcharge_mode(&b,false)==(fails[k]<0?fails[k]:-EIO));CHECK(b.fast_mode&&b.fast_mode_valid);out=87;CHECK(!fg_get_fastcharge_mode(&b,&out)&&out==1); }
 mode_result=0;CHECK(!fg_set_fastcharge_mode(&b,false));CHECK(!b.fast_mode&&b.fast_mode_valid);finish_chip(&b);
 for (unsigned k=0;k<sizeof(fails)/sizeof(fails[0]);k++) { init_chip(&b);reset_wire();mode_result=fails[k];CHECK(fg_set_fastcharge_mode(&b,false)==(fails[k]<0?fails[k]:-EIO));CHECK(mode_calls==1&&!b.fast_mode&&!b.fast_mode_valid);out=87;CHECK(fg_get_fastcharge_mode(&b,&out)==-EAGAIN&&out==87);mode_result=0;CHECK(!fg_set_fastcharge_mode(&b,false));CHECK(mode_calls==2&&b.fast_mode_valid&&!b.fast_mode);finish_chip(&b); }
 init_chip(&b);reset_wire();b.fg_vendor=MPC7021;CHECK(!fg_set_fastcharge_mode(&b,false));CHECK(mode_calls==1&&last_len==0&&last_cmd==0x3f);CHECK(!fg_set_fastcharge_mode(&b,true));CHECK(mode_calls==2&&last_len==0&&last_cmd==0x3e);finish_chip(&b);
 for (unsigned failure=0;failure<2;failure++) { init_chip(&b);reset_wire();pause_write=true;mode_result=failure?-ETIMEDOUT:0;pthread_t writer,reader;CHECK(!pthread_create(&writer,NULL,set_thread,&b));CHECK(!pthread_mutex_lock(&state));while(!write_entered)CHECK(!pthread_cond_wait(&cond,&state));CHECK(!pthread_mutex_unlock(&state));struct getter_call call={.b=&b,.out=87,.ret=999};CHECK(!pthread_create(&reader,NULL,get_thread,&call));CHECK(!pthread_mutex_lock(&state));while(!getter_waiting)CHECK(!pthread_cond_wait(&cond,&state));CHECK(!atomic_load(&getter_done));release_write=true;CHECK(!pthread_cond_broadcast(&cond));CHECK(!pthread_mutex_unlock(&state));void *ret;CHECK(!pthread_join(writer,&ret));CHECK((intptr_t)ret==(failure?-ETIMEDOUT:0));CHECK(!pthread_join(reader,NULL));CHECK(atomic_load(&getter_done));CHECK(call.ret==(failure?-EAGAIN:0));CHECK(call.out==(failure?87:1));CHECK(b.fast_mode_valid==!failure);finish_chip(&b); }
}
int main(int argc,char **argv) { if (argc==2)negative(argv[1]);else normal();printf("PASS BQ cache-valid assertions=%u\n",atomic_load(&assertions));return 0; }
