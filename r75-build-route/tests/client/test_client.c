#include "fake_kernel.h"
#ifndef current
#error "The host kernel surface must retain Linux's current macro"
#endif
#include "production_under_test.c"

struct pmic_glink_client { struct pmic_glink_client_data cb; pthread_mutex_t lock;pthread_cond_t cv;bool detached;unsigned callbacks; };
static struct pmic_glink_client *registered;
static unsigned frees,unregisters,tx_count,groups,platform_registrations;
static int registration_error,create_error;
static bool early_down,group_present;
static enum { OK, REMOTE_ERROR, SEND_ERROR, SILENT, DOWN_THEN_REPLY, REPLY_THEN_DOWN, MISMATCH_THEN_OK, OLD_THEN_OK, BLOCK_SEND } mode, extra_mode;
static u32 raw_value=0x81234567U,remote_error=0xffffffffU;
static struct mr_request last_request,prior_request;
static pthread_mutex_t gate_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t gate_cv=PTHREAD_COND_INITIALIZER;
static bool send_entered,release_send,callback_entered,release_callback,show_entered,release_show,unregister_entered;
static unsigned active_shows;
static unsigned psy_registers,psy_unregisters,psy_changes,active_psy_reads;
static int psy_registration_error;
static struct power_supply *registered_psy;
static bool per_property,flip_epoch,psy_read_entered,release_psy_read,psy_unregister_entered;
static u32 raw_properties[MR_PROPERTIES];
static u32 extra_raw_properties[MR_EXTRA_PROPERTIES];
static u32 wire_properties[1024],wire_seqs[1024];
static bool extra_flip_epoch;
static bool block_notify,notify_entered,release_notify,barrier_entered,release_barrier;

static struct mr_response reply(const struct mr_request *q)
{
 struct mr_response r={0};r.hdr=q->hdr;r.property=q->property;r.seq=q->seq;u32 raw=raw_value;
 if(per_property)for(unsigned i=0;i<MR_PROPERTIES;i++)if(q->property==mr_properties[i])raw=raw_properties[i];
 if(mr_extra_property_allowed(q->property))for(unsigned i=0;i<MR_EXTRA_PROPERTIES;i++)if(q->property==mr_extra_properties[i])raw=extra_raw_properties[i];
 memcpy(r.data,&raw,sizeof(raw));return r;
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
 assert(c==registered && len==276);struct mr_request q;memcpy(&q,data,len);last_request=q;assert(tx_count<ARRAY_SIZE(wire_properties));wire_properties[tx_count]=q.property;wire_seqs[tx_count]=q.seq;tx_count++;
 bool extra=mr_extra_property_allowed(q.property);
 assert(q.hdr.owner==0x800aU && q.hdr.type==1 && q.hdr.opcode==1 && (mr_property_allowed(q.property)||extra));
 for(unsigned i=0;i<sizeof(q.data);i++)assert(!q.data[i]);
 struct mr_device *m=c->cb.priv;struct mr_response r=reply(&q),bad;
 switch(extra?extra_mode:mode){
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
 deliver(c,&r,sizeof(r),false);
 if(flip_epoch && q.property==mr_properties[3]){c->cb.state_cb(m,PMIC_GLINK_STATE_DOWN);c->cb.state_cb(m,PMIC_GLINK_STATE_UP);}
 if(extra_flip_epoch && extra){c->cb.state_cb(m,PMIC_GLINK_STATE_DOWN);c->cb.state_cb(m,PMIC_GLINK_STATE_UP);}
 return 0;
}
struct power_supply *power_supply_register(struct device *dev,const struct power_supply_desc *desc,const struct power_supply_config *cfg)
{
 psy_registers++;assert(!strcmp(desc->name,"usb")&&desc->type==POWER_SUPPLY_TYPE_USB&&desc->no_thermal);
 assert(desc->num_properties==5&&cfg->num_supplicants==1&&!strcmp(cfg->supplied_to[0],"battery"));
 if(psy_registration_error)return ERR_PTR(psy_registration_error);
 assert(!registered_psy);registered_psy=calloc(1,sizeof(*registered_psy));assert(registered_psy);
 assert(!pthread_mutex_init(&registered_psy->dev.mutex,NULL));
 registered_psy->dev.parent=dev;registered_psy->desc=desc;registered_psy->drv_data=cfg->drv_data;
 struct mr_device *m=cfg->drv_data;
 assert(!m->notify_ready&&!m->notify_work.queued&&!m->notify_work.mod_calls);
 union power_supply_propval val;assert(desc->get_property(registered_psy,POWER_SUPPLY_PROP_ONLINE,&val)==-ENODATA);
 assert(!desc->get_property(registered_psy,POWER_SUPPLY_PROP_STATUS,&val)&&val.intval==POWER_SUPPLY_STATUS_UNKNOWN);
 return registered_psy;
}
void power_supply_unregister(struct power_supply *psy)
{
 struct mr_device *m=psy->drv_data;assert(m->stopping&&!m->work.running&&!m->notify_work.running&&!registered&&psy->removing);
 assert(!pthread_mutex_lock(&gate_lock));psy_unregister_entered=true;assert(!pthread_cond_broadcast(&gate_cv));while(active_psy_reads)assert(!pthread_cond_wait(&gate_cv,&gate_lock));assert(!pthread_mutex_unlock(&gate_lock));
 assert(psy==registered_psy);psy_unregisters++;registered_psy=NULL;assert(!pthread_mutex_destroy(&psy->dev.mutex));free(psy);
}
void power_supply_changed(struct power_supply *psy)
{
 assert(psy&&psy==registered_psy);struct mr_device *m=psy->drv_data;
 assert(!pthread_mutex_trylock(&m->lock));assert(!pthread_mutex_unlock(&m->lock));psy_changes++;
 if(block_notify){assert(!pthread_mutex_lock(&gate_lock));notify_entered=true;assert(!pthread_cond_broadcast(&gate_cv));while(!release_notify)assert(!pthread_cond_wait(&gate_cv,&gate_lock));assert(!pthread_mutex_unlock(&gate_lock));}
}
void kfree(void *p){if(p){frees++;free(p);}}
int sysfs_create_group(struct kobject *k,const struct attribute_group *g){(void)k;assert(!strcmp(g->name,"myron_mca_readonly"));assert(g->attrs[0]->mode==0444 && g->attrs[1]->mode==0444 && !strcmp(g->attrs[1]->name,"diagnostics") && !g->attrs[2]);if(create_error)return create_error;group_present=true;return 0;}
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
 assert(!registered&&!registered_psy&&!node_refs);lookup_node=&node;node_lookups=node_puts=0;registration_error=create_error=psy_registration_error=0;early_down=group_present=false;mode=OK;raw_value=0x81234567U;remote_error=0xffffffffU;tx_count=0;enable_readonly=true;enable_power_supply=false;per_property=flip_epoch=false;
 psy_registers=psy_unregisters=psy_changes=active_psy_reads=0;psy_read_entered=release_psy_read=psy_unregister_entered=false;
 block_notify=notify_entered=release_notify=barrier_entered=release_barrier=false;
 enable_extra_diagnostics=false;extra_mode=OK;extra_flip_epoch=false;
 send_entered=release_send=callback_entered=release_callback=show_entered=release_show=unregister_entered=false;active_shows=0;
}
static void destroy(struct platform_device *p){mr_remove(p);assert(!p->dev.data);free(p);}
static void run_work(struct delayed_work *w)
{
 assert(!pthread_mutex_lock(&w->lock));assert(w->queued&&!w->running);w->queued=false;w->running=true;assert(!pthread_mutex_unlock(&w->lock));
 w->work.fn(&w->work);
 assert(!pthread_mutex_lock(&w->lock));w->running=false;assert(!pthread_cond_broadcast(&w->cv));assert(!pthread_mutex_unlock(&w->lock));
}
static void run_one(struct mr_device *m){run_work(&m->work);}
static void *work_thread(void *arg){run_one(arg);return NULL;}
static void *notify_thread(void *arg){struct mr_device *m=arg;run_work(&m->notify_work);return NULL;}
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
static int read_int(struct mr_device *m,enum power_supply_property property,int expected_error)
{
 union power_supply_propval v={.intval=-12345};unsigned tx=tx_count;
 int got=mr_supply_get(m->psy,property,&v);
 if(got!=expected_error)fprintf(stderr,"group=%u property=%d got=%d wanted=%d valid=%d round=%u deadline=%llu now=%llu\n",groups,property,got,expected_error,m->supply.valid,m->cache.round,(unsigned long long)m->supply.expires_ms,(unsigned long long)atomic_load(&fake_clock)/1000000);
 assert(got==expected_error&&tx_count==tx);return v.intval;
}
static void supply_unknown(struct mr_device *m)
{
 assert(read_int(m,POWER_SUPPLY_PROP_STATUS,0)==POWER_SUPPLY_STATUS_UNKNOWN);
 read_int(m,POWER_SUPPLY_PROP_ONLINE,-ENODATA);read_int(m,POWER_SUPPLY_PROP_VOLTAGE_NOW,-ENODATA);read_int(m,POWER_SUPPLY_PROP_CURRENT_NOW,-ENODATA);
}
static struct platform_device *reporting_new(void)
{
 enable_power_supply=true;per_property=true;
 const u32 captured[]={1,4966000,494000,1,3,0xffffffffU};memcpy(raw_properties,captured,sizeof(captured));
 return probe_new();
}
static void *psy_read_thread(void *arg)
{
 struct power_supply *psy=arg;assert(!pthread_mutex_lock(&gate_lock));active_psy_reads++;psy_read_entered=true;assert(!pthread_cond_broadcast(&gate_cv));while(!release_psy_read)assert(!pthread_cond_wait(&gate_cv,&gate_lock));assert(!pthread_mutex_unlock(&gate_lock));
 union power_supply_propval v;assert(!mr_supply_get(psy,POWER_SUPPLY_PROP_STATUS,&v)&&v.intval==POWER_SUPPLY_STATUS_UNKNOWN);
 assert(!pthread_mutex_lock(&gate_lock));active_psy_reads--;assert(!pthread_cond_broadcast(&gate_cv));assert(!pthread_mutex_unlock(&gate_lock));return NULL;
}
static void *barrier_read_thread(void *arg)
{
 struct power_supply *psy=arg;device_lock(&psy->dev);assert(!psy->removing);
 assert(!pthread_mutex_lock(&gate_lock));barrier_entered=true;assert(!pthread_cond_broadcast(&gate_cv));while(!release_barrier)assert(!pthread_cond_wait(&gate_cv,&gate_lock));assert(!pthread_mutex_unlock(&gate_lock));
 union power_supply_propval v;assert(!psy->removing&&!mr_supply_get(psy,POWER_SUPPLY_PROP_STATUS,&v)&&v.intval==POWER_SUPPLY_STATUS_UNKNOWN);device_unlock(&psy->dev);return NULL;
}
#include "test_extra_diagnostics.inc"
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
 /* Separately opted-in reporting preserves the bounded default and requires
  * enable_readonly. Registration failure/collision never queues any GET. */
 reset();enable_power_supply=true;enable_readonly=false;assert(mr_init()==-EPERM);struct platform_device denied={.dev={.of_node=&node}};assert(mr_probe(&denied)==-EPERM&&!psy_registers);groups++;
 for(unsigned failure=0;failure<2;failure++){
  reset();enable_power_supply=true;psy_registration_error=failure?-EEXIST:-ENOMEM;struct platform_device fail={.dev={.of_node=&node}};f=frees;u=unregisters;
  assert(mr_probe(&fail)==psy_registration_error&&!fail.dev.data&&!registered&&!registered_psy&&!tx_count&&!group_present&&frees==f+1&&unregisters==u+1);groups++;
 }
 reset();p=reporting_new();m=p->dev.data;assert(m->psy->dev.parent==&p->dev&&m->reporting&&!tx_count);supply_unknown(m);
 union power_supply_propval model;assert(!mr_supply_get(m->psy,POWER_SUPPLY_PROP_MODEL_NAME,&model)&&!strcmp(model.strval,"myron-mca-readonly"));run_work(&m->notify_work);assert(!psy_changes);groups++;
 run_one(m);assert(read_int(m,POWER_SUPPLY_PROP_ONLINE,0)==1&&read_int(m,POWER_SUPPLY_PROP_VOLTAGE_NOW,0)==4966000&&read_int(m,POWER_SUPPLY_PROP_CURRENT_NOW,0)==494000&&read_int(m,POWER_SUPPLY_PROP_STATUS,0)==POWER_SUPPLY_STATUS_CHARGING);
 assert(snapshot_show(&p->dev,NULL,buf)>0&&strstr(buf,"max_rounds=4294967295")&&strstr(buf,"max_requests=4294967295")&&strstr(buf,"power_supply_reporting=1 freshness_ms=15000 supply_valid=1 generation=1\nproperty="));
 run_work(&m->notify_work);assert(psy_changes==1);run_work(&m->notify_work);assert(psy_changes==1);run_one(m);run_work(&m->notify_work);assert(psy_changes==1);groups++;
 const u32 wall[]={1,4828000,650000,11,3,3000};memcpy(raw_properties,wall,sizeof(wall));run_one(m);assert(read_int(m,POWER_SUPPLY_PROP_CURRENT_NOW,0)==650000&&read_int(m,POWER_SUPPLY_PROP_STATUS,0)==POWER_SUPPLY_STATUS_CHARGING);groups++;
 const u32 unplug[]={0,16000,0,0,7,100};memcpy(raw_properties,unplug,sizeof(unplug));run_one(m);assert(read_int(m,POWER_SUPPLY_PROP_ONLINE,0)==0&&read_int(m,POWER_SUPPLY_PROP_VOLTAGE_NOW,0)==16000&&read_int(m,POWER_SUPPLY_PROP_STATUS,0)==POWER_SUPPLY_STATUS_DISCHARGING);groups++;
 raw_properties[0]=1;raw_properties[1]=5000000;
 for(unsigned status=0;status<=9;status++){
  raw_properties[4]=status;run_one(m);int wanted=(status==0||status==9)?POWER_SUPPLY_STATUS_UNKNOWN:status==5?POWER_SUPPLY_STATUS_FULL:(status==6||status==7)?POWER_SUPPLY_STATUS_NOT_CHARGING:POWER_SUPPLY_STATUS_CHARGING;
  assert(read_int(m,POWER_SUPPLY_PROP_STATUS,0)==wanted);groups++;
 }
 /* Range/sentinel rejection is unavailable data, never clamp or wrap. */
 raw_properties[4]=3;
 for(unsigned bad=0;bad<7;bad++){
  u32 saved[6];memcpy(saved,raw_properties,sizeof(saved));
  if(bad==0)raw_properties[0]=2;
  if(bad==1)raw_properties[1]=MR_MAX_BUS_UV+1;
  if(bad==2)raw_properties[2]=MR_MAX_BUS_UA+1;
  if(bad==3)raw_properties[1]=0xffffffffU;
  if(bad==4)raw_properties[2]=0xffffffffU;
  if(bad==5)raw_properties[1]=999999;
  if(bad==6)raw_properties[0]=0; /* inconsistent offline/active status */
  run_one(m);supply_unknown(m);memcpy(raw_properties,saved,sizeof(saved));groups++;
 }
 run_one(m);run_work(&m->notify_work);unsigned changes=psy_changes;mr_state(m,PMIC_GLINK_STATE_DOWN);mr_state(m,PMIC_GLINK_STATE_UP);supply_unknown(m);run_work(&m->notify_work);assert(psy_changes==changes+1);run_work(&m->notify_work);assert(psy_changes==changes+1);groups++;
 flip_epoch=true;run_one(m);assert(m->link_up);supply_unknown(m);flip_epoch=false;run_one(m);assert(read_int(m,POWER_SUPPLY_PROP_ONLINE,0)==1);groups++;
 /* Expiry is measured from sample start, including time spent suspended. */
 u64 deadline=m->supply.expires_ms;atomic_store(&fake_clock,(deadline-1)*1000000);assert(read_int(m,POWER_SUPPLY_PROP_ONLINE,0)==1);supply_unknown(m);run_work(&m->notify_work);assert(!m->supply.valid);groups++;
 run_one(m);u64 earliest=m->cache.samples[0].start_ms;assert(m->supply.expires_ms==earliest+MR_FRESH_MS);atomic_store(&fake_clock,(earliest-100)*1000000);supply_unknown(m);run_work(&m->notify_work);assert(!m->supply.valid);groups++;
 /* Reporting continues past the original 60 rounds / 360 requests. */
 for(unsigned i=0;i<70;i++){run_one(m);}assert(!m->finished&&m->work.queued&&m->cache.round>60&&m->requests_sent>360);destroy(p);groups++;
 reset();p=reporting_new();m=p->dev.data;run_one(m);run_work(&m->notify_work);changes=psy_changes;mode=BLOCK_SEND;assert(!pthread_create(&work,NULL,work_thread,m));wait_flag(&send_entered);atomic_fetch_add(&fake_clock,20000ULL*1000000);supply_unknown(m);run_work(&m->notify_work);assert(psy_changes==changes+1&&!m->supply.valid&&m->work.running);release_flag(&release_send);assert(!pthread_join(work,NULL));destroy(p);groups++;
 reset();p=reporting_new();m=p->dev.data;run_one(m);mode=SILENT;for(unsigned i=0;i<3;i++)run_one(m);assert(m->finished&&m->stop_reason==2&&!m->work.queued);supply_unknown(m);run_work(&m->notify_work);assert(!m->notify_work.queued);destroy(p);groups++;
 for(unsigned exhausted=0;exhausted<4;exhausted++){
  reset();p=reporting_new();m=p->dev.data;run_one(m);
  if(exhausted==0)m->next_seq=U32_MAX;
  if(exhausted==1)m->requests_sent=U32_MAX;
  if(exhausted==2)m->cache.round=U32_MAX;
  if(exhausted==3){m->generation=U32_MAX;mr_state(m,PMIC_GLINK_STATE_UP);}
  tx=tx_count;run_one(m);assert(m->finished&&m->stop_reason==4&&tx_count==tx&&!m->work.queued);supply_unknown(m);destroy(p);groups++;
 }
 /* Removal drains already admitted power_supply readers, and it cancels
  * both workers before unregistering/freeing the reporting object. */
 reset();p=reporting_new();m=p->dev.data;run_one(m);pthread_t reader;f=frees;assert(!pthread_create(&reader,NULL,psy_read_thread,m->psy));wait_flag(&psy_read_entered);assert(!pthread_create(&remove,NULL,remove_thread,p));wait_flag(&psy_unregister_entered);assert(frees==f);release_flag(&release_psy_read);assert(!pthread_join(reader,NULL));assert(!pthread_join(remove,NULL));assert(frees==f+1&&psy_unregisters==1);free(p);groups++;
 /* Cooperative in-kernel consumers hold the PSY object's device lock. The
  * removing barrier must drain them before the private state can disappear. */
 reset();p=reporting_new();m=p->dev.data;run_one(m);f=frees;assert(!pthread_create(&reader,NULL,barrier_read_thread,m->psy));wait_flag(&barrier_entered);assert(!pthread_create(&remove,NULL,remove_thread,p));wait_flag(&unregister_entered);assert(frees==f);assert(!pthread_mutex_lock(&gate_lock));assert(!psy_unregister_entered);assert(!pthread_mutex_unlock(&gate_lock));release_flag(&release_barrier);assert(!pthread_join(reader,NULL));assert(!pthread_join(remove,NULL));assert(frees==f+1&&psy_unregisters==1);free(p);groups++;
 /* The independent expiry/notification worker is itself drained on remove. */
 reset();p=reporting_new();m=p->dev.data;run_one(m);block_notify=true;pthread_t notification;f=frees;assert(!pthread_create(&notification,NULL,notify_thread,m));wait_flag(&notify_entered);assert(!pthread_create(&remove,NULL,remove_thread,p));
 for(;;){unsigned long flags;spin_lock_irqsave(&m->lock,flags);bool stop=m->stopping;spin_unlock_irqrestore(&m->lock,flags);if(stop)break;}
 assert(frees==f);release_flag(&release_notify);assert(!pthread_join(notification,NULL));assert(!pthread_join(remove,NULL));assert(frees==f+1&&psy_unregisters==1);free(p);groups++;
 /* Reporting cadence changes independently of the original diagnostic
  * mode. Changed publications advance the watchdog to immediate work. */
 reset();p=probe_new();m=p->dev.data;run_one(m);assert(m->work.delay==5000&&!m->notify_ready&&!m->notify_work.queued);destroy(p);groups++;
 reset();p=reporting_new();m=p->dev.data;run_work(&m->notify_work);assert(m->notify_ready&&m->notify_work.delay==1000&&!m->notify_work.mod_calls);run_one(m);assert(m->work.delay==2000&&m->notify_work.delay==0&&m->notify_work.mod_calls==1);run_work(&m->notify_work);assert(psy_changes==1&&m->notify_work.delay==1000);run_one(m);assert(m->work.delay==2000&&m->notify_work.delay==1000&&m->notify_work.mod_calls==1);tx=tx_count;mr_state(m,PMIC_GLINK_STATE_DOWN);mr_state(m,PMIC_GLINK_STATE_UP);assert(m->notify_work.delay==0&&tx_count==tx);run_work(&m->notify_work);assert(psy_changes==2&&m->notify_work.delay==1000);supply_unknown(m);destroy(p);groups++;
 /* A new state event arriving while power_supply_changed is executing
  * must retain an immediate successor, rather than losing its wakeup. */
 reset();p=reporting_new();m=p->dev.data;run_one(m);block_notify=true;assert(!pthread_create(&notification,NULL,notify_thread,m));wait_flag(&notify_entered);assert(m->notify_work.delay==1000);mr_state(m,PMIC_GLINK_STATE_DOWN);mr_state(m,PMIC_GLINK_STATE_UP);assert(m->notify_work.queued&&m->notify_work.delay==0);release_flag(&release_notify);assert(!pthread_join(notification,NULL));assert(m->notify_work.queued&&m->notify_work.delay==0);block_notify=false;run_work(&m->notify_work);assert(psy_changes==2&&m->notify_work.delay==1000);destroy(p);groups++;
 /* A callback admitted before unregister may execute after both work
  * cancellations. The locked stop/notify_ready fence forbids requeue. */
 reset();p=reporting_new();m=p->dev.data;run_one(m);assert(!pthread_create(&callback,NULL,callback_thread,registered));wait_flag(&callback_entered);assert(!pthread_create(&remove,NULL,remove_thread,p));wait_flag(&unregister_entered);assert(m->stopping&&!m->notify_ready&&m->notify_work.cancelled&&!m->notify_work.queued);unsigned mods=m->notify_work.mod_calls;mr_state(m,PMIC_GLINK_STATE_DOWN);mr_state(m,PMIC_GLINK_STATE_UP);assert(m->notify_work.mod_calls==mods&&!m->notify_work.queued);release_flag(&release_callback);assert(!pthread_join(callback,NULL));assert(!pthread_join(remove,NULL));free(p);groups++;
 test_extra_diagnostics();
 printf("{\"status\":\"PASS\",\"groups\":%u,\"whole_production_TU\":true,\"default_max_gets\":360,\"reporting_exceeds_60_rounds\":true,\"reporting_interval_ms\":2000,\"diagnostic_interval_ms\":5000,\"extra_diagnostic_groups\":32,\"teardown_concurrency_cases\":8}\n",groups);return 0;
}
