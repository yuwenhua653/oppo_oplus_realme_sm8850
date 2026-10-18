#include "fake_kernel.h"
#include "api_under_test.h"
#include "production_functions.c"
static unsigned groups;
struct fixture {
 struct pmic_glink_dev pg;struct device parent,child;struct rpmsg_device rp;
 struct pmic_glink_client *client,*target,*added;
 pthread_mutex_t lock;pthread_cond_t cv;
 bool entered,allow,waiting,detached,unreg_done,rx_done,state_wait_rx;
 unsigned state_calls,msg_calls,state_active,state_max,notify_attempts;
 bool block_msg,block_state,do_write,try_unregister,add_client;
 int unregister_rc,callback_unregister_rc;
};
static struct fixture *wait_fixture;
static void signal_fixture(struct fixture*f){assert(!pthread_cond_broadcast(&f->cv));}
static void wait_flag(struct fixture*f,bool *flag){assert(!pthread_mutex_lock(&f->lock));while(!*flag)assert(!pthread_cond_wait(&f->cv,&f->lock));assert(!pthread_mutex_unlock(&f->lock));}
static void wait_cb(struct completion*c){(void)c;struct fixture*f=wait_fixture;if(!f)return;assert(!pthread_mutex_lock(&f->lock));f->waiting=true;signal_fixture(f);assert(!pthread_mutex_unlock(&f->lock));}
static void detached_cb(void*p){struct fixture*f=wait_fixture;if(!f||p!=f->client)return;assert(!pthread_mutex_lock(&f->lock));f->detached=true;signal_fixture(f);assert(!pthread_mutex_unlock(&f->lock));}
static void send_from_cb(struct fixture*f){struct pmic_glink_hdr h={.owner=7,.type=1,.opcode=1};assert(pmic_glink_write(f->client,&h,sizeof(h))==0);}
static int msg_cb(void*priv,void*data,size_t len){struct fixture*f=priv;(void)data;assert(len>=12);
 assert(!pthread_mutex_lock(&f->lock));f->msg_calls++;f->entered=true;f->rx_done=true;signal_fixture(f);while(f->block_msg&&!f->allow)assert(!pthread_cond_wait(&f->cv,&f->lock));assert(!pthread_mutex_unlock(&f->lock));
 if(f->do_write)send_from_cb(f);
 if(f->try_unregister)f->callback_unregister_rc=pmic_glink_unregister_client_sync(f->target?f->target:f->client);
 return 0;
}
static void state_cb(void*priv,enum pmic_glink_state state){struct fixture*f=priv;(void)state;
 assert(!pthread_mutex_lock(&f->lock));f->state_calls++;f->state_active++;if(f->state_active>f->state_max)f->state_max=f->state_active;f->entered=true;signal_fixture(f);while(f->block_state&&!f->allow)assert(!pthread_cond_wait(&f->cv,&f->lock));assert(!pthread_mutex_unlock(&f->lock));
 if(f->do_write)send_from_cb(f);
 if(f->try_unregister)f->callback_unregister_rc=pmic_glink_unregister_client_sync(f->target?f->target:f->client);
 if(f->state_wait_rx)wait_flag(f,&f->rx_done);
 if(f->add_client&&!f->added){struct pmic_glink_client_data d={.name="added",.id=100,.priv=f,.msg_cb=msg_cb,.state_cb=state_cb};f->added=pmic_glink_register_client(&f->child,&d);assert(!IS_ERR(f->added));}
 assert(!pthread_mutex_lock(&f->lock));f->state_active--;assert(!pthread_mutex_unlock(&f->lock));
}
static void setup(struct fixture*f,unsigned id,bool state){memset(f,0,sizeof(*f));assert(!pthread_mutex_init(&f->lock,NULL));assert(!pthread_cond_init(&f->cv,NULL));
 f->child.parent=&f->parent;f->pg.dev=&f->parent;f->rp.ept=f;f->pg.rpdev=&f->rp;mutex_init(&f->pg.client_lock);mutex_init(&f->pg.state_notify_lock);init_rwsem(&f->pg.rpdev_sem);idr_init(&f->pg.client_idr);INIT_LIST_HEAD(&f->pg.client_dev_list);atomic_set(&f->pg.state,1);list_add(&f->pg.dev_list,&pmic_glink_dev_list);
 struct pmic_glink_client_data d={.name="test",.id=id,.priv=f,.msg_cb=msg_cb,.state_cb=state?state_cb:NULL};f->client=pmic_glink_register_client(&f->child,&d);assert(!IS_ERR(f->client));}
static void teardown(struct fixture*f){if(f->client){assert(pmic_glink_unregister_client(f->client)==0);f->client=NULL;}if(f->added){assert(pmic_glink_unregister_client(f->added)==0);f->added=NULL;}list_del(&f->pg.dev_list);assert(list_empty(&f->pg.client_dev_list));assert(list_empty(&pmic_glink_callback_contexts));}
static void *rx_thread(void*arg){struct fixture*f=arg;struct pmic_glink_buf*p=calloc(1,sizeof(*p)+sizeof(struct pmic_glink_hdr));p->len=sizeof(struct pmic_glink_hdr);struct pmic_glink_hdr h={.owner=7,.type=1,.opcode=1};memcpy(p->buf,&h,sizeof(h));pmic_glink_rx_callback(&f->pg,p);free(p);return NULL;}
static void *state_thread(void*arg){struct fixture*f=arg;pmic_glink_notify_clients(&f->pg,PMIC_GLINK_STATE_DOWN);return NULL;}
static void *unreg_thread(void*arg){struct fixture*f=arg;int rc=pmic_glink_unregister_client_sync(f->client);assert(!pthread_mutex_lock(&f->lock));f->unregister_rc=rc;f->unreg_done=true;signal_fixture(f);assert(!pthread_mutex_unlock(&f->lock));return NULL;}
static void overlap(bool state){struct fixture f;setup(&f,7,true);f.block_msg=!state;f.block_state=state;f.do_write=true;wait_fixture=&f;wait_hook=wait_cb;idr_remove_hook=detached_cb;pthread_t cb,unreg;
 assert(!pthread_create(&cb,NULL,state?state_thread:rx_thread,&f));wait_flag(&f,&f.entered);assert(!pthread_create(&unreg,NULL,unreg_thread,&f));wait_flag(&f,&f.waiting);wait_flag(&f,&f.detached);
 assert(!pthread_mutex_lock(&f.lock));assert(!f.unreg_done);assert(!pthread_mutex_unlock(&f.lock));assert(!pthread_mutex_trylock(&f.pg.client_lock.lock));assert(!idr_find(&f.pg.client_idr,7));assert(!pthread_mutex_unlock(&f.pg.client_lock.lock));
 assert(!pthread_mutex_lock(&f.lock));f.allow=true;signal_fixture(&f);assert(!pthread_mutex_unlock(&f.lock));assert(!pthread_join(cb,NULL));assert(!pthread_join(unreg,NULL));assert(f.unregister_rc==0);f.client=NULL;
 unsigned before=f.msg_calls;rx_thread(&f);assert(f.msg_calls==before);unsigned states=f.state_calls;pmic_glink_notify_clients(&f.pg,PMIC_GLINK_STATE_UP);assert(f.state_calls==states);wait_hook=NULL;idr_remove_hook=NULL;wait_fixture=NULL;teardown(&f);groups++;
}
static void callback_unregister(bool state,bool cross){struct fixture f,g;setup(&f,7,state);if(cross){setup(&g,9,false);f.target=g.client;}f.try_unregister=true;f.do_write=true;if(state)state_thread(&f);else rx_thread(&f);assert(f.callback_unregister_rc==-EDEADLK);assert(idr_find(&f.pg.client_idr,7)==f.client);if(cross){assert(idr_find(&g.pg.client_idr,9)==g.client);teardown(&g);}f.try_unregister=false;teardown(&f);groups++;}
static void state_waits_rx(void){struct fixture f;setup(&f,7,true);f.state_wait_rx=true;f.do_write=true;pthread_t t;assert(!pthread_create(&t,NULL,state_thread,&f));wait_flag(&f,&f.entered);rx_thread(&f);assert(!pthread_join(t,NULL));assert(f.state_calls==1&&f.msg_calls==1);teardown(&f);groups++;}
static struct fixture *serial_fixture;
static void notify_lock_attempt(struct mutex*m){struct fixture*f=serial_fixture;if(f&&m==&f->pg.state_notify_lock){assert(!pthread_mutex_lock(&f->lock));f->notify_attempts++;signal_fixture(f);assert(!pthread_mutex_unlock(&f->lock));}}
static void state_serial(void){struct fixture f;setup(&f,7,true);f.block_state=true;serial_fixture=&f;mutex_hook=notify_lock_attempt;pthread_t a,b;assert(!pthread_create(&a,NULL,state_thread,&f));wait_flag(&f,&f.entered);assert(!pthread_create(&b,NULL,state_thread,&f));assert(!pthread_mutex_lock(&f.lock));while(f.notify_attempts<2)assert(!pthread_cond_wait(&f.cv,&f.lock));assert(f.state_calls==1&&f.state_active==1);f.allow=true;signal_fixture(&f);assert(!pthread_mutex_unlock(&f.lock));assert(!pthread_join(a,NULL));assert(!pthread_join(b,NULL));mutex_hook=NULL;serial_fixture=NULL;assert(f.state_calls==2&&f.state_max==1);teardown(&f);groups++;}
static void state_registration_bound(void){struct fixture f;setup(&f,7,true);f.add_client=true;state_thread(&f);assert(f.added&&f.state_calls==1);f.add_client=false;teardown(&f);groups++;}
static void id_boundary(void){struct fixture f;setup(&f,7,true);mutex_lock(&f.pg.client_lock);idr_remove(&f.pg.client_idr,7);f.client->id=INT_MAX;f.pg.client_idr.p[0]=f.client;f.pg.client_idr.id[0]=INT_MAX;mutex_unlock(&f.pg.client_lock);state_thread(&f);assert(f.state_calls==1);teardown(&f);groups++;}
static void registration_failure(void){struct fixture f;setup(&f,7,true);struct pmic_glink_client_data d={.name="duplicate",.id=7,.msg_cb=msg_cb,.priv=&f};struct pmic_glink_client *x=pmic_glink_register_client(&f.child,&d);assert(IS_ERR(x)&&PTR_ERR(x)==-ENOSPC);assert(idr_find(&f.pg.client_idr,7)==f.client);atomic_set(&f.pg.state,0);d.id=8;x=pmic_glink_register_client(&f.child,&d);assert(IS_ERR(x)&&PTR_ERR(x)==-EPROBE_DEFER);teardown(&f);groups++;}
int main(void){for(unsigned n=0;n<16;n++){overlap(false);overlap(true);}callback_unregister(false,false);callback_unregister(true,false);callback_unregister(false,true);callback_unregister(true,true);state_waits_rx();state_serial();state_registration_bound();id_boundary();registration_failure();assert(list_empty(&pmic_glink_dev_list));printf("{\"status\":\"PASS\",\"groups\":%u,\"actual_production_functions\":true,\"write_calls\":%u}\n",groups,atomic_load(&write_count));return 0;}
