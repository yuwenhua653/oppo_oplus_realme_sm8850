#include "fake_kernel.h"
#include "production_under_test.c"

struct pmic_glink_client { struct pmic_glink_client_data cb; pthread_mutex_t lock;pthread_cond_t cv;bool detached;unsigned callbacks; };
static struct pmic_glink_client *registered;
static unsigned frees,unregisters,tx_count,groups,platform_registrations;
static int registration_error,create_error;
static bool early_down,group_present;
static enum { OK, REMOTE_ERROR, SEND_ERROR, SILENT, DOWN_THEN_REPLY, REPLY_THEN_DOWN, MISMATCH_THEN_OK, OLD_THEN_OK, BLOCK_SEND } mode;
static u32 raw_value=0x81234567U,remote_error=0xffffffffU;
static struct mr_request last_request,prior_request;
static pthread_mutex_t gate_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t gate_cv=PTHREAD_COND_INITIALIZER;
static bool send_entered,release_send,callback_entered,release_callback,show_entered,release_show,unregister_entered;
static unsigned active_shows;

static struct mr_response reply(const struct mr_request *q)
{
 struct mr_response r={0};r.hdr=q->hdr;r.property=q->property;r.seq=q->seq;memcpy(r.data,&raw_value,sizeof(raw_value));return r;
}
static void deliver(struct pmic_glink_client *c,struct mr_response *r,size_t len,bool pause)
{
 assert(!pthread_mutex_lock(&c->lock));assert(!c->detached);c->callbacks++;assert(!pthread_mutex_unlock(&c->lock));
 if(pause){assert(!pthread_mutex_lock(&gate_lock));callback_entered=true;assert(!pthread_cond_broadcast(&gate_cv));while(!release_callback)assert(!pthread_cond_wait(&gate_cv,&gate_lock));assert(!pthread_mutex_unlock(&gate_lock));}
 assert(!c->cb.msg_cb(c->cb.priv,r,len));
 assert(!pthread_mutex_lock(&c->lock));c->callbacks--;assert(!pthread_cond_broadcast(&c->cv));assert(!pthread_mutex_unlock(&c->lock));
}
struct pmic_glink_client *pmic_glink_register_client(struct device *d,const struct pmic_glink_client_data *cb)
{
 (void)d;assert(cb->id==0x800aU && cb->msg_cb && cb->state_cb);
 if(registration_error)return ERR_PTR(registration_error);
 assert(!registered);struct pmic_glink_client *c=calloc(1,sizeof(*c));assert(c);c->cb=*cb;assert(!pthread_mutex_init(&c->lock,NULL));assert(!pthread_cond_init(&c->cv,NULL));registered=c;
 if(early_down)cb->state_cb(cb->priv,PMIC_GLINK_STATE_DOWN);
 return c;
}
int pmic_glink_unregister_client_sync(struct pmic_glink_client *c)
{
 struct mr_device *m=c->cb.priv;assert(m->stopping);assert(!m->work.running);assert(!group_present);assert(!active_shows);
 assert(!pthread_mutex_lock(&gate_lock));unregister_entered=true;assert(!pthread_cond_broadcast(&gate_cv));assert(!pthread_mutex_unlock(&gate_lock));
 assert(!pthread_mutex_lock(&c->lock));c->detached=true;while(c->callbacks)assert(!pthread_cond_wait(&c->cv,&c->lock));assert(!pthread_mutex_unlock(&c->lock));
 unregisters++;registered=NULL;assert(!pthread_mutex_destroy(&c->lock));assert(!pthread_cond_destroy(&c->cv));free(c);return 0;
}
int pmic_glink_write(struct pmic_glink_client *c,void *data,size_t len)
{
 assert(c==registered && len==276);struct mr_request q;memcpy(&q,data,len);last_request=q;tx_count++;
 assert(q.hdr.owner==0x800aU && q.hdr.type==1 && q.hdr.opcode==1 && mr_property_allowed(q.property));
 for(unsigned i=0;i<sizeof(q.data);i++)assert(!q.data[i]);
 struct mr_device *m=c->cb.priv;struct mr_response r=reply(&q),bad;
 switch(mode){
 case SEND_ERROR:return -EIO;
 case SILENT:return 0;
 case BLOCK_SEND:
  assert(!pthread_mutex_lock(&gate_lock));send_entered=true;assert(!pthread_cond_broadcast(&gate_cv));while(!release_send)assert(!pthread_cond_wait(&gate_cv,&gate_lock));assert(!pthread_mutex_unlock(&gate_lock));return 0;
 case DOWN_THEN_REPLY:c->cb.state_cb(m,PMIC_GLINK_STATE_DOWN);deliver(c,&r,sizeof(r),false);return 0;
 case REPLY_THEN_DOWN:deliver(c,&r,sizeof(r),false);c->cb.state_cb(m,PMIC_GLINK_STATE_DOWN);return 0;
 case REMOTE_ERROR:r.remote_status=remote_error;break;
 case MISMATCH_THEN_OK:
  bad=r;bad.hdr.owner=0x8009;deliver(c,&bad,sizeof(bad),false);assert(m->pending);
  bad=r;bad.hdr.type=2;deliver(c,&bad,sizeof(bad),false);assert(m->pending);
  bad=r;bad.hdr.opcode=2;deliver(c,&bad,sizeof(bad),false);assert(m->pending);
  bad=r;bad.property=0xdeadbeefU;deliver(c,&bad,sizeof(bad),false);assert(m->pending);
  bad=r;bad.property=mr_properties[(q.property==mr_properties[0])?1:0];deliver(c,&bad,sizeof(bad),false);assert(m->pending);
  bad=r;bad.seq++;deliver(c,&bad,sizeof(bad),false);assert(m->pending);
  deliver(c,&r,sizeof(r)-1,false);assert(m->pending);deliver(c,&r,sizeof(r)+1,false);assert(m->pending);break;
 case OLD_THEN_OK:bad=reply(&prior_request);deliver(c,&bad,sizeof(bad),false);assert(m->pending);break;
 case OK:break;
 }
 deliver(c,&r,sizeof(r),false);return 0;
}
void kfree(void *p){if(p){frees++;free(p);}}
int sysfs_create_group(struct kobject *k,const struct attribute_group *g){(void)k;assert(!strcmp(g->name,"myron_mca_readonly"));assert(g->attrs[0]->mode==0444 && !g->attrs[1]);if(create_error)return create_error;group_present=true;return 0;}
void sysfs_remove_group(struct kobject *k,const struct attribute_group *g){(void)k;(void)g;assert(!pthread_mutex_lock(&gate_lock));group_present=false;while(active_shows)assert(!pthread_cond_wait(&gate_cv,&gate_lock));assert(!pthread_mutex_unlock(&gate_lock));}
int sysfs_emit_at(char *buf,int at,const char *fmt,...){va_list ap;va_start(ap,fmt);int n=vsnprintf(buf+at,PAGE_SIZE-at,fmt,ap);va_end(ap);assert(n>=0 && at+n<PAGE_SIZE);return n;}
int sysfs_emit(char *buf,const char *fmt,...){va_list ap;va_start(ap,fmt);int n=vsnprintf(buf,PAGE_SIZE,fmt,ap);va_end(ap);assert(n>=0 && n<PAGE_SIZE);return n;}
int platform_driver_register(struct platform_driver *d){assert(d==&mr_driver);platform_registrations++;return 0;}
void platform_driver_unregister(struct platform_driver *d){assert(d==&mr_driver);}
/* Match pinned Linux OF unflattening: full_name is the node basename. */
static struct device_node node={"mca,adsp_glink"};
static struct device_node *lookup_node=&node;
static unsigned node_lookups,node_puts,node_refs;
struct device_node *of_find_node_by_path(const char *path)
{
 assert(!strcmp(path,"/soc/pmic-glink/mca,adsp_glink"));node_lookups++;
 if(lookup_node)node_refs++;
 return lookup_node;
}
void of_node_put(struct device_node *np)
{
 if(np){assert(np==lookup_node&&node_refs);node_refs--;node_puts++;}
}
static struct device parent;
static struct platform_device *probe_new(void)
{
 struct platform_device *p=calloc(1,sizeof(*p));assert(p);p->dev.parent=&parent;p->dev.of_node=&node;assert(!mr_probe(p));assert(!node_refs);return p;
}
static void reset(void)
{
 assert(!registered&&!node_refs);lookup_node=&node;node_lookups=node_puts=0;registration_error=create_error=0;early_down=group_present=false;mode=OK;raw_value=0x81234567U;remote_error=0xffffffffU;tx_count=0;enable_readonly=true;
 send_entered=release_send=callback_entered=release_callback=show_entered=release_show=unregister_entered=false;active_shows=0;
}
static void destroy(struct platform_device *p){mr_remove(p);assert(!p->dev.data);free(p);}
static void run_one(struct mr_device *m)
{
 struct delayed_work *w=&m->work;assert(!pthread_mutex_lock(&w->lock));assert(w->queued&&!w->running);w->queued=false;w->running=true;assert(!pthread_mutex_unlock(&w->lock));
 w->work.fn(&w->work);
 assert(!pthread_mutex_lock(&w->lock));w->running=false;assert(!pthread_cond_broadcast(&w->cv));assert(!pthread_mutex_unlock(&w->lock));
}
static void *work_thread(void *arg){run_one(arg);return NULL;}
static void *remove_thread(void *arg){mr_remove(arg);return NULL;}
static void *callback_thread(void *arg){struct mr_response r={0};deliver(arg,&r,sizeof(r),true);return NULL;}
static void *show_thread(void *arg)
{
 struct platform_device *p=arg;char buf[PAGE_SIZE];
 assert(!pthread_mutex_lock(&gate_lock));assert(group_present);active_shows++;show_entered=true;assert(!pthread_cond_broadcast(&gate_cv));while(!release_show)assert(!pthread_cond_wait(&gate_cv,&gate_lock));assert(!pthread_mutex_unlock(&gate_lock));
 assert(snapshot_show(&p->dev,NULL,buf)>0);
 assert(!pthread_mutex_lock(&gate_lock));active_shows--;assert(!pthread_cond_broadcast(&gate_cv));assert(!pthread_mutex_unlock(&gate_lock));return NULL;
}
static void wait_flag(bool *flag){assert(!pthread_mutex_lock(&gate_lock));while(!*flag)assert(!pthread_cond_wait(&gate_cv,&gate_lock));assert(!pthread_mutex_unlock(&gate_lock));}
static void release_flag(bool *flag){assert(!pthread_mutex_lock(&gate_lock));*flag=true;assert(!pthread_cond_broadcast(&gate_cv));assert(!pthread_mutex_unlock(&gate_lock));}
static void assert_invalid(const struct mr_sample *s,int err){assert(s->error==err&&!s->raw);}
int main(void)
{
 _Static_assert(sizeof(struct mr_request)==276,"request wire size");_Static_assert(sizeof(struct mr_response)==280,"response wire size");
 reset();enable_readonly=false;assert(mr_init()==-EPERM&&!platform_registrations);enable_readonly=true;assert(!mr_init());mr_exit();groups++;
 reset();struct platform_device *exact=probe_new();
 assert(node_lookups==1&&node_puts==1&&!node_refs&&!tx_count);
 destroy(exact);groups++;
 /* Exact DT identity: same basename elsewhere, absent node/path and a forged
  * full-path string cannot pass; lookup references are balanced on rejection. */
 for(unsigned failure=0;failure<5;failure++){
  reset();struct device_node other={failure==3?MR_NODE:"mca,adsp_glink"};
  struct platform_device invalid={.dev={.parent=&parent,.of_node=&node}};
  unsigned f=frees,u=unregisters;
  if(failure==0)invalid.dev.of_node=NULL;
  else if(failure==1)lookup_node=NULL;
  else if(failure==4)enable_readonly=false;
  else invalid.dev.of_node=&other;
  assert(mr_probe(&invalid)==(failure==4?-EPERM:-ENODEV));
  assert(!invalid.dev.data&&!registered&&!group_present&&!tx_count);
  assert(frees==f&&unregisters==u&&!node_refs);
  assert(node_lookups==(failure==4?0:1));
  assert(node_puts==((failure==1||failure==4)?0:1));groups++;
 }
 for(unsigned failure=0;failure<2;failure++){
  reset();struct platform_device p={.dev={.parent=&parent,.of_node=&node}};unsigned f=frees,u=unregisters;if(failure)create_error=-ENOMEM;else registration_error=-ENOSPC;
  assert(mr_probe(&p)==(failure?-ENOMEM:-ENOSPC));assert(!p.dev.data&&!registered&&frees==f+1&&unregisters==u+failure);groups++;
 }
 reset();early_down=true;struct platform_device *p=probe_new();struct mr_device *m=p->dev.data;assert(!m->link_up&&!m->initial_link_assumed);run_one(m);assert(!tx_count);assert_invalid(&m->cache.samples[0],-ENOTCONN);for(unsigned i=1;i<6;i++)assert_invalid(&m->cache.samples[i],-ECANCELED);destroy(p);groups++;
 reset();p=probe_new();m=p->dev.data;char buf[PAGE_SIZE];assert(snapshot_show(&p->dev,NULL,buf)>0);assert(strstr(buf,"round=0")&&strstr(buf,"valid=0")&&!tx_count);groups++;
 mode=MISMATCH_THEN_OK;run_one(m);assert(tx_count==6&&m->cache.round==1);for(unsigned i=0;i<6;i++){assert(m->cache.samples[i].property==mr_properties[i]);assert(!m->cache.samples[i].error&&m->cache.samples[i].raw==0x81234567U&&m->cache.samples[i].attempted);assert(m->cache.samples[i].end_ms>=m->cache.samples[i].start_ms);}unsigned tx=tx_count;assert(snapshot_show(&p->dev,NULL,buf)>0&&tx_count==tx);groups++;
 for(unsigned i=0;i<6;i++){
  struct mr_sample s;mode=REMOTE_ERROR;mr_get(m,mr_properties[i],&s);assert_invalid(&s,-EREMOTEIO);assert(s.response_seen&&s.remote_status==0xffffffffU);groups++;
 }
 struct mr_sample s;tx=tx_count;mr_get(m,0x2003,&s);assert_invalid(&s,-EINVAL);assert(tx_count==tx&&!s.attempted);groups++;
 mode=SILENT;mr_get(m,mr_properties[0],&s);assert_invalid(&s,-ETIMEDOUT);prior_request=last_request;struct mr_response late=reply(&prior_request);deliver(registered,&late,sizeof(late),false);assert(!m->pending);mode=OLD_THEN_OK;mr_get(m,mr_properties[0],&s);assert(!s.error&&s.seq!=prior_request.seq);groups++;
 mode=DOWN_THEN_REPLY;mr_get(m,mr_properties[0],&s);assert_invalid(&s,-ENOTCONN);mr_state(m,PMIC_GLINK_STATE_UP);mode=REPLY_THEN_DOWN;mr_get(m,mr_properties[0],&s);assert(!s.error&&s.raw==raw_value);groups++;
 mr_state(m,PMIC_GLINK_STATE_UP);m->next_seq=U32_MAX;tx=tx_count;mr_get(m,mr_properties[0],&s);assert_invalid(&s,-EOVERFLOW);assert(tx_count==tx);destroy(p);groups++;
 reset();p=probe_new();m=p->dev.data;mode=SILENT;for(unsigned i=0;i<3;i++)run_one(m);assert(m->finished&&m->stop_reason==2&&m->cache.round==3&&tx_count==3&&!m->work.queued);for(unsigned i=1;i<6;i++)assert_invalid(&m->cache.samples[i],-ECANCELED);destroy(p);groups++;
 reset();p=probe_new();m=p->dev.data;for(unsigned i=0;i<60;i++)run_one(m);assert(m->finished&&m->stop_reason==1&&tx_count==360&&m->requests_sent==360&&!m->work.queued);assert(snapshot_show(&p->dev,NULL,buf)>0&&strstr(buf,"finished=1"));destroy(p);groups++;
 /* Removal cannot free the object/client while a transport send is blocked. */
 reset();p=probe_new();m=p->dev.data;mode=BLOCK_SEND;pthread_t work,remove;unsigned f=frees,u=unregisters;assert(!pthread_create(&work,NULL,work_thread,m));wait_flag(&send_entered);assert(!pthread_create(&remove,NULL,remove_thread,p));
 for(;;){unsigned long flags;spin_lock_irqsave(&m->lock,flags);bool stop=m->stopping;spin_unlock_irqrestore(&m->lock,flags);if(stop)break;}
 assert(frees==f&&unregisters==u);release_flag(&release_send);assert(!pthread_join(work,NULL));assert(!pthread_join(remove,NULL));assert(frees==f+1&&unregisters==u+1&&!p->dev.data);free(p);groups++;
 /* Underlying unregister drain must finish before private memory is freed. */
 reset();p=probe_new();pthread_t callback;f=frees;assert(!pthread_create(&callback,NULL,callback_thread,registered));wait_flag(&callback_entered);assert(!pthread_create(&remove,NULL,remove_thread,p));wait_flag(&unregister_entered);assert(frees==f);release_flag(&release_callback);assert(!pthread_join(callback,NULL));assert(!pthread_join(remove,NULL));assert(frees==f+1);free(p);groups++;
 /* Sysfs removal drains an already admitted cache reader. */
 reset();p=probe_new();pthread_t show;f=frees;assert(!pthread_create(&show,NULL,show_thread,p));wait_flag(&show_entered);assert(!pthread_create(&remove,NULL,remove_thread,p));release_flag(&release_show);assert(!pthread_join(show,NULL));assert(!pthread_join(remove,NULL));assert(frees==f+1);free(p);groups++;
 printf("{\"status\":\"PASS\",\"groups\":%u,\"whole_production_TU\":true,\"max_gets\":360,\"teardown_concurrency_cases\":3}\n",groups);return 0;
}
