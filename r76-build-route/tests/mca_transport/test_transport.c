#include "fake_kernel.h"
#include "production_under_test.c"

static struct mca_adsp_glink_dev dev;
static struct pmic_glink_client *fake_client=(void *)1;
static struct mca_adsp_glink_req_msg last_tx;
static int tx_count;
static u32 remote_status;
static unsigned rx_byte=0x42;
static enum { REPLY_OK, REMOTE_ERR, SEND_ERR, SILENT, DOWN_REPLY, REPLY_DOWN,
 DOWN_UP_REPLY, BAD_THEN_GOOD, OLD_THEN_GOOD, ASYNC_SILENT } mode;
static pthread_mutex_t sent_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t sent_cv=PTHREAD_COND_INITIALIZER;
static bool sent;
static u32 prior_seq;
static int callback_count;

struct pmic_glink_client *pmic_glink_register_client(struct device *d,const struct pmic_glink_client_data *c) { (void)d;(void)c;return fake_client; }
int pmic_glink_unregister_client(struct pmic_glink_client *c) { (void)c;abort(); }
static struct mca_adsp_glink_resp_msg response(const struct mca_adsp_glink_req_msg *q,u32 ret) {
 struct mca_adsp_glink_resp_msg r={0}; r.hdr=q->hdr;r.property_id=q->property_id;r.seq=q->seq;r.retcode=ret;memset(r.data,rx_byte,sizeof(r.data));return r;
}
static void deliver(struct mca_adsp_glink_resp_msg *r,size_t len) { ++callback_count;assert(mca_adsp_glink_callback(&dev,r,len)==0); }
int pmic_glink_write(struct pmic_glink_client *c,void *data,size_t len) {
 assert(c==fake_client && len==276);memcpy(&last_tx,data,len);tx_count++;
 assert(last_tx.hdr.type==MCA_ADSP_GLINK_MSG_REQ);
 assert(last_tx.hdr.owner==MCA_ADSP_GLINK_OWNER || last_tx.hdr.owner==MCA_ADSP_GLINK_QBG_OWNER);
 assert(last_tx.hdr.opcode==MCA_ADSP_GLINK_OPCODE_READ || last_tx.hdr.opcode==MCA_ADSP_GLINK_OPCODE_WRITE);
 struct mca_adsp_glink_resp_msg r=response(&last_tx,mode==REMOTE_ERR?remote_status:0), bad;
 switch(mode) {
 case SEND_ERR:return -EIO;
 case SILENT:return 0;
 case ASYNC_SILENT:
  assert(!pthread_mutex_lock(&sent_lock));sent=true;assert(!pthread_cond_signal(&sent_cv));assert(!pthread_mutex_unlock(&sent_lock));return 0;
 case DOWN_REPLY:
  mca_adsp_glink_state_cb(&dev,PMIC_GLINK_STATE_DOWN);deliver(&r,sizeof(r));return 0;
 case DOWN_UP_REPLY:
  mca_adsp_glink_state_cb(&dev,PMIC_GLINK_STATE_DOWN);mca_adsp_glink_state_cb(&dev,PMIC_GLINK_STATE_UP);deliver(&r,sizeof(r));return 0;
 case BAD_THEN_GOOD:
  bad=r;bad.hdr.owner^=1;deliver(&bad,sizeof(bad));assert(dev.pending);
  bad=r;bad.hdr.type=2;deliver(&bad,sizeof(bad));assert(dev.pending);
  bad=r;bad.hdr.opcode=3;deliver(&bad,sizeof(bad));assert(dev.pending);
  bad=r;bad.property_id++;deliver(&bad,sizeof(bad));assert(dev.pending);
  bad=r;bad.seq++;deliver(&bad,sizeof(bad));assert(dev.pending);
  deliver(&r,sizeof(r)-1);assert(dev.pending);deliver(&r,sizeof(r)+1);assert(dev.pending);
  assert(!mca_adsp_glink_callback(&dev,NULL,0));assert(dev.pending);break;
 case OLD_THEN_GOOD:
  bad=r;bad.seq=prior_seq;memset(bad.data,0xee,sizeof(bad.data));deliver(&bad,sizeof(bad));assert(dev.pending);break;
 case REPLY_DOWN:case REPLY_OK:case REMOTE_ERR:break;
 }
 deliver(&r,sizeof(r));
 if(mode==REPLY_DOWN)mca_adsp_glink_state_cb(&dev,PMIC_GLINK_STATE_DOWN);
 return 0;
}
static void init_dev(void) {
 memset(&dev,0,sizeof(dev));mutex_init(&dev.rw_lock);spin_lock_init(&dev.pending_lock);init_completion(&dev.ack);
 dev.glink_state=PMIC_GLINK_STATE_UP;dev.client=fake_client;dev.cur_property_id=UINT32_MAX;INIT_WORK(&dev.sync_work,mca_adsp_glink_sync_work);g_mca_adsp_glink=&dev;
}
static void fresh(void) {
 assert(!dev.pending);mca_adsp_glink_state_cb(&dev,PMIC_GLINK_STATE_UP);tx_count=0;callback_count=0;mode=REPLY_OK;remote_status=0;rx_byte=0x42;sent=false;
}
static int invoke(unsigned api,unsigned char *value) {
 switch(api) {
 case 0:return mca_adsp_glink_read_prop(0x20001,value,8);
 case 1:return mca_adsp_glink_write_prop(0x20001,value,8);
 case 2:return mca_adsp_glink_qbg_read_prop(0x20001,value,8);
 case 3:return mca_adsp_glink_qbg_write_prop(0x20001,value,8);
 }abort();
}
static bool is_read(unsigned api) {return !(api&1);}
static void unchanged(const unsigned char *v) {for(unsigned i=0;i<8;i++)assert(v[i]==0xa5);}
static void succeeded(unsigned api,const unsigned char *v) {for(unsigned i=0;i<8;i++)assert(v[i]==(is_read(api)?0x42:0xa5));}
static unsigned groups;
static void group_all_paths(unsigned api) {
 unsigned char value[8];int ret;
 fresh();memset(value,0xa5,8);assert(invoke(api,value)==0);succeeded(api,value);assert(tx_count==1&&!dev.pending);assert(last_tx.hdr.owner==(api<2?0x800a:0x8009));assert(last_tx.hdr.opcode==(is_read(api)?1:2));groups++;
 fresh();mca_adsp_glink_state_cb(&dev,PMIC_GLINK_STATE_DOWN);memset(value,0xa5,8);assert(invoke(api,value)==-ENOTCONN);unchanged(value);assert(!tx_count&&!dev.pending);groups++;
 fresh();mode=DOWN_REPLY;memset(value,0xa5,8);assert(invoke(api,value)==-ENOTCONN);unchanged(value);assert(tx_count==1&&!dev.pending);groups++;
 fresh();mode=DOWN_UP_REPLY;memset(value,0xa5,8);assert(invoke(api,value)==-ENOTCONN);unchanged(value);assert(!dev.pending);groups++;
 fresh();mode=REPLY_DOWN;memset(value,0xa5,8);assert(invoke(api,value)==0);succeeded(api,value);assert(!dev.pending);groups++;
 for(unsigned i=0;i<5;i++) {
  const u32 errs[]={1,5,0x7fffffffU,0x80000000U,0xffffffffU};
  fresh();mode=REMOTE_ERR;remote_status=errs[i];memset(value,0xa5,8);assert(invoke(api,value)==-EREMOTEIO);unchanged(value);assert(dev.remote_retcode==errs[i]);assert(!dev.pending);groups++;
 }
 fresh();mode=SEND_ERR;memset(value,0xa5,8);assert(invoke(api,value)==-EIO);unchanged(value);assert(!dev.pending);groups++;
 fresh();mode=BAD_THEN_GOOD;memset(value,0xa5,8);assert(invoke(api,value)==0);succeeded(api,value);assert(callback_count==8);groups++;
 fresh();mode=SILENT;memset(value,0xa5,8);ret=invoke(api,value);assert(ret==-ETIMEDOUT);unchanged(value);assert(!dev.pending);prior_seq=last_tx.seq;
 struct mca_adsp_glink_resp_msg late=response(&last_tx,0);deliver(&late,sizeof(late));unchanged(value);assert(!dev.pending);groups++;
 fresh();mode=OLD_THEN_GOOD;memset(value,0xa5,8);assert(invoke(api,value)==0);succeeded(api,value);assert(dev.remote_retcode==0);groups++;
 fresh();memset(dev.read_buf,0xee,sizeof(dev.read_buf));mode=SEND_ERR;memset(value,0xa5,8);assert(invoke(api,value)==-EIO);unchanged(value);for(unsigned i=0;i<sizeof(dev.read_buf);i++)assert(dev.read_buf[i]==0);groups++;
}
struct caller {unsigned api;int rc;unsigned char value[8];};
static void *call_thread(void *arg) {struct caller *c=arg;c->rc=invoke(c->api,c->value);return NULL;}
static void async_down_test(unsigned api) {
 fresh();mode=ASYNC_SILENT;struct caller c={.api=api};memset(c.value,0xa5,8);pthread_t t;assert(!pthread_create(&t,NULL,call_thread,&c));
 assert(!pthread_mutex_lock(&sent_lock));while(!sent)assert(!pthread_cond_wait(&sent_cv,&sent_lock));assert(!pthread_mutex_unlock(&sent_lock));
 mca_adsp_glink_state_cb(&dev,PMIC_GLINK_STATE_DOWN);assert(!pthread_join(t,NULL));assert(c.rc==-ENOTCONN);unchanged(c.value);assert(!dev.pending);groups++;
}
static void admission_order_test(void) {
 /* Hold the real pending lock; a sender must not admit itself using an earlier UP read. */
 fresh();unsigned long flags;spin_lock_irqsave(&dev.pending_lock,flags);
 struct caller c={.api=0};memset(c.value,0xa5,8);pthread_t t;assert(!pthread_create(&t,NULL,call_thread,&c));
 /* This simulates the state transition's critical section before releasing admission. */
 dev.glink_state=PMIC_GLINK_STATE_DOWN;spin_unlock_irqrestore(&dev.pending_lock,flags);
 assert(!pthread_join(t,NULL));assert(c.rc==-ENOTCONN);assert(!tx_count);unchanged(c.value);groups++;
}
static void request_helper_test(void) {
 fresh();struct mca_adsp_glink_req_msg q={.hdr={0x800a,1,1},.property_id=0x20001,.seq=123};
 memset(dev.read_buf,0xee,sizeof(dev.read_buf));dev.remote_retcode=99;
 assert(mca_adsp_glink_begin_request(&dev,&q)==0);assert(dev.pending&&dev.cur_seq==123&&dev.remote_retcode==0);
 for(unsigned i=0;i<sizeof(dev.read_buf);i++)assert(dev.read_buf[i]==0);
 mca_adsp_glink_state_cb(&dev,PMIC_GLINK_STATE_DOWN);assert(!dev.pending&&dev.retcode==-ENOTCONN);
 mca_adsp_glink_end_request(&dev);groups++;
}
int main(void) {
 _Static_assert(sizeof(struct mca_adsp_glink_req_msg)==276,"request wire ABI");
 _Static_assert(sizeof(struct mca_adsp_glink_resp_msg)==280,"response wire ABI");
 _Static_assert(sizeof(struct mca_adsp_glink_notify_msg)==272,"notify wire ABI");
 (void)mca_adsp_driver;init_dev();
 for(unsigned api=0;api<4;api++){group_all_paths(api);async_down_test(api);}
 admission_order_test();request_helper_test();
 printf("{\"status\":\"PASS\",\"fixture_groups\":%u,\"production_translation_unit\":true,\"wire_sizes\":[276,280,272]}\n",groups);
 return 0;
}
