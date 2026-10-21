/* The complete production TU above is exercised through its actual worker,
 * transport callback, sysfs getter, power_supply getter and notifier. */
static void transient_reproduction(void)
{
 reset();struct platform_device *p=reporting_new();struct mr_device *m=p->dev.data;
 run_one(m);run_work(&m->notify_work);
 u64 deadline=m->supply.expires_ms;
 const char *names[]={"complete","auxiliary_get_failed","complete_again"};
 for(unsigned n=0;n<3;n++){
  if(n){injected_index=n==1?5:-1;injected_mode=SEND_ERROR;run_one(m);run_work(&m->notify_work);}
  union power_supply_propval online={.intval=-1},status={.intval=-1};
  int error=mr_supply_get(m->psy,POWER_SUPPLY_PROP_ONLINE,&online);
  assert(!mr_supply_get(m->psy,POWER_SUPPLY_PROP_STATUS,&status));
  printf("{\"phase\":\"%s\",\"online_error\":%d,\"online\":%d,\"status\":%d,\"notifications\":%u,\"original_deadline\":%llu,\"supply_deadline\":%llu,\"auxiliary_error\":%d}\n",names[n],error,online.intval,status.intval,psy_changes,(unsigned long long)deadline,(unsigned long long)m->supply.expires_ms,m->cache.samples[5].error);
 }
 destroy(p);
}

static void cache_unchanged(struct mr_device *m,
                            const struct mr_supply_cache *saved)
{
 assert(!memcmp(&m->supply,saved,sizeof(*saved)));
 assert(read_int(m,POWER_SUPPLY_PROP_ONLINE,0)==saved->online);
 assert(read_int(m,POWER_SUPPLY_PROP_STATUS,0)==saved->status);
 assert(read_int(m,POWER_SUPPLY_PROP_VOLTAGE_NOW,0)==saved->voltage_uv);
 assert(read_int(m,POWER_SUPPLY_PROP_CURRENT_NOW,0)==saved->current_ua);
}

static void test_transient_cache(void)
{
 const int faults[]={SEND_ERROR,SILENT,REMOTE_ERROR};
 const int errors[]={-EIO,-ETIMEDOUT,-EREMOTEIO};
 struct platform_device *p;struct mr_device *m;char buf[PAGE_SIZE];
 unsigned checks=0;
 /* Each of the six fixed GETs may fail in each of the three supported ways.
  * Preserve the complete old value and deadline, never partial new values;
  * expose the failed round verbatim and emit no false USB disconnect. */
 for(unsigned f=0;f<ARRAY_SIZE(faults);f++)for(unsigned index=0;index<MR_PROPERTIES;index++){
  reset();p=reporting_new();m=p->dev.data;run_one(m);run_work(&m->notify_work);
  struct mr_supply_cache saved=m->supply;unsigned changes=psy_changes;
  raw_properties[1]+=100000;raw_properties[2]+=100000;
  injected_index=index;injected_mode=faults[f];run_one(m);
  assert(m->cache.samples[index].error==errors[f]);
  cache_unchanged(m,&saved);run_work(&m->notify_work);assert(psy_changes==changes);
  unsigned tx=tx_count;assert(snapshot_show(&p->dev,NULL,buf)>0&&tx_count==tx);
  assert(strstr(buf,"supply_valid=1")&&strstr(buf,"round=2"));
  injected_index=-1;run_one(m);run_work(&m->notify_work);
  assert(m->supply.expires_ms>saved.expires_ms&&psy_changes==changes+1);
  assert(read_int(m,POWER_SUPPLY_PROP_VOLTAGE_NOW,0)==(int)raw_properties[1]);
  destroy(p);checks++;
 }
 /* No first successful snapshot means no state to retain. */
 for(unsigned f=0;f<ARRAY_SIZE(faults);f++)for(unsigned index=0;index<MR_PROPERTIES;index++){
  reset();p=reporting_new();m=p->dev.data;injected_index=index;injected_mode=faults[f];
  run_one(m);supply_unknown(m);assert(!m->supply.valid);destroy(p);checks++;
 }
 /* Any observed unplug immediately withdraws the old online state even
  * when a subsequent GET fails. It never extends charging through unplug. */
 for(unsigned f=0;f<ARRAY_SIZE(faults);f++)for(unsigned index=1;index<MR_PROPERTIES;index++){
  reset();p=reporting_new();m=p->dev.data;run_one(m);run_work(&m->notify_work);
  unsigned changes=psy_changes;raw_properties[0]=0;raw_properties[1]=16000;
  raw_properties[2]=0;raw_properties[4]=7;injected_index=index;injected_mode=faults[f];
  run_one(m);supply_unknown(m);assert(!m->supply.valid);
  run_work(&m->notify_work);assert(psy_changes==changes+1);destroy(p);checks++;
 }
 /* Received status/range contradictions cannot hide behind a later error. */
 for(unsigned bad=0;bad<7;bad++){
  reset();p=reporting_new();m=p->dev.data;run_one(m);
  if(bad==0)raw_properties[0]=2;
  if(bad==1)raw_properties[1]=MR_MAX_BUS_UV+1;
  if(bad==2)raw_properties[2]=MR_MAX_BUS_UA+1;
  if(bad==3)raw_properties[1]=999999;
  if(bad==4)raw_properties[4]=5;
  if(bad==5)raw_properties[4]=9;
  if(bad==6)raw_properties[4]=7;
  injected_index=5;injected_mode=SEND_ERROR;run_one(m);supply_unknown(m);
  assert(!m->supply.valid);destroy(p);checks++;
 }
 /* A successful offline snapshot must not mask a newly observed plug. */
 reset();p=reporting_new();m=p->dev.data;raw_properties[0]=0;raw_properties[1]=16000;
 raw_properties[2]=0;raw_properties[4]=7;run_one(m);assert(m->supply.valid);
 raw_properties[0]=1;raw_properties[1]=5000000;raw_properties[4]=3;
 injected_index=5;injected_mode=SEND_ERROR;run_one(m);supply_unknown(m);
 assert(!m->supply.valid);destroy(p);checks++;
 /* Repeated errors do not slide the old deadline. The independent watchdog
  * withdraws it at the same original BOOTTIME deadline, including suspend. */
 reset();p=reporting_new();m=p->dev.data;run_one(m);run_work(&m->notify_work);
 struct mr_supply_cache saved=m->supply;injected_index=5;injected_mode=SEND_ERROR;
 for(unsigned n=0;n<3;n++){
  atomic_fetch_add(&fake_clock,4000ULL*1000000);run_one(m);cache_unchanged(m,&saved);
 }
 atomic_store(&fake_clock,saved.expires_ms*1000000);supply_unknown(m);
 run_work(&m->notify_work);assert(!m->supply.valid&&psy_changes==2);
 run_one(m);supply_unknown(m);assert(!m->supply.valid);destroy(p);checks++;
 /* Expiry during a failed round, time reversal and malformed timestamps
  * also refuse retention; stopping/finished/epoch guards are independent. */
 for(unsigned bad=0;bad<7;bad++){
  reset();p=reporting_new();m=p->dev.data;run_one(m);
  struct mr_cache failed=m->cache;failed.samples[5].error=-EIO;
  failed.samples[5].response_seen=false;
  u32 generation=m->generation;
  if(bad==0)atomic_store(&fake_clock,m->supply.expires_ms*1000000);
  if(bad==1)atomic_store(&fake_clock,(m->supply.expires_ms-MR_FRESH_MS-1)*1000000);
  if(bad==2)failed.samples[2].end_ms=failed.samples[2].start_ms-1;
  if(bad==3)failed.samples[2].end_ms=m->supply.expires_ms+1;
  if(bad==4)m->stopping=true;
  if(bad==5)m->finished=true;
  if(bad==6)generation--;
  unsigned long flags;spin_lock_irqsave(&m->lock,flags);mr_publish(m,&failed,generation);spin_unlock_irqrestore(&m->lock,flags);
  supply_unknown(m);assert(!m->supply.valid);destroy(p);checks++;
 }
 /* Unsupported failures and inconsistent response/error metadata remain
  * fail closed. Only the three explicitly tested failure classes retain. */
 const int refused[]={-ENOTCONN,-ESHUTDOWN,-EOVERFLOW,-EPROTO,-EINVAL,-EINPROGRESS,-ECANCELED};
 for(unsigned bad=0;bad<ARRAY_SIZE(refused)+3;bad++){
  reset();p=reporting_new();m=p->dev.data;run_one(m);
  struct mr_cache failed=m->cache;struct mr_sample *s=&failed.samples[5];
  s->error=bad<ARRAY_SIZE(refused)?refused[bad]:-EIO;s->response_seen=false;
  if(bad==ARRAY_SIZE(refused))s->response_seen=true;
  if(bad==ARRAY_SIZE(refused)+1){s->error=-EREMOTEIO;s->response_seen=true;s->remote_status=0;}
  if(bad==ARRAY_SIZE(refused)+2){s->error=-EREMOTEIO;s->remote_status=1;}
  unsigned long flags;spin_lock_irqsave(&m->lock,flags);mr_publish(m,&failed,m->generation);spin_unlock_irqrestore(&m->lock,flags);
  supply_unknown(m);assert(!m->supply.valid);destroy(p);checks++;
 }
 /* Callback races during every GET retain the existing epoch fencing. */
 const int links[]={DOWN_THEN_REPLY,REPLY_THEN_DOWN};
 for(unsigned f=0;f<ARRAY_SIZE(links);f++)for(unsigned index=0;index<MR_PROPERTIES;index++){
  reset();p=reporting_new();m=p->dev.data;run_one(m);injected_index=index;injected_mode=links[f];
  run_one(m);supply_unknown(m);assert(!m->supply.valid);destroy(p);checks++;
 }
 for(unsigned epoch=0;epoch<2;epoch++){
  reset();p=reporting_new();m=p->dev.data;run_one(m);
  if(epoch)flip_epoch=true;else mr_state(m,PMIC_GLINK_STATE_UP);
  injected_index=5;injected_mode=SEND_ERROR;run_one(m);supply_unknown(m);
  assert(!m->supply.valid);destroy(p);checks++;
 }
 /* A retained supply cannot advance running extras or arm WAITING extras
  * from partial new PD evidence. A later complete round may arm WAITING. */
 for(unsigned waiting=0;waiting<2;waiting++){
  reset();p=extra_reporting_new();m=p->dev.data;if(waiting)raw_properties[3]=1;
  run_one(m);struct mr_supply_cache old=m->supply;unsigned attempts=m->extra.attempts;
  raw_properties[3]=0xb;injected_index=5;injected_mode=SEND_ERROR;run_one(m);
  cache_unchanged(m,&old);assert(m->extra.attempts==attempts);
  assert(m->extra.state==(waiting?MR_EXTRA_WAITING:MR_EXTRA_STOPPED));
  injected_index=-1;run_one(m);
  assert(m->extra.attempts==attempts+waiting);destroy(p);checks++;
 }
 groups+=checks;printf("{\"transient_cache_groups\":%u,\"each_get_faults\":18,\"original_ttl_unchanged\":true,\"explicit_offline_cases\":15,\"link_callback_cases\":12}\n",checks);
}
