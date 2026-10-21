/* Included after the shared production-function host fixtures. */
static struct platform_device *extra_reporting_new(void)
{
 enable_extra_diagnostics=true;
 struct platform_device *p=reporting_new();
 raw_properties[3]=0x0b;
 for(unsigned i=0;i<MR_EXTRA_PROPERTIES;i++)extra_raw_properties[i]=0x81000000U+i;
 return p;
}

static void extra_read_only(struct platform_device *p)
{
 char buf[PAGE_SIZE];unsigned before=tx_count;
 assert(diagnostics_show(&p->dev,NULL,buf)>0);
 assert(tx_count==before);
 assert(snapshot_show(&p->dev,NULL,buf)>0);
 assert(tx_count==before);
}

static void extra_core_still_reports(struct mr_device *m)
{
 assert(!m->finished&&m->work.queued&&!m->consecutive_timeouts);
 assert(read_int(m,POWER_SUPPLY_PROP_ONLINE,0)==1);
 assert(read_int(m,POWER_SUPPLY_PROP_VOLTAGE_NOW,0)==4966000);
 assert(read_int(m,POWER_SUPPLY_PROP_CURRENT_NOW,0)==494000);
 assert(read_int(m,POWER_SUPPLY_PROP_STATUS,0)==POWER_SUPPLY_STATUS_CHARGING);
}

static void test_extra_diagnostics(void)
{
 struct platform_device *p;struct mr_device *m;unsigned before;

 /* A fresh core must not conceal that the previous diagnostic context
  * expired while the independent watchdog had not yet been scheduled. */
 for(unsigned expired_during_core=0;expired_during_core<2;expired_during_core++){
  reset();p=extra_reporting_new();m=p->dev.data;run_one(m);run_work(&m->notify_work);
  assert(m->extra.state==MR_EXTRA_RUNNING&&m->extra.attempts==1);
  u64 old_deadline=m->supply.expires_ms;
  if(expired_during_core)atomic_store(&fake_clock,(old_deadline-5)*1000000);
  else {atomic_fetch_add(&fake_clock,20000ULL*1000000);supply_unknown(m);}
  before=tx_count;run_one(m); /* Core runs before the watchdog in both cases. */
  assert(atomic_load(&fake_clock)/1000000>=old_deadline);
  assert(tx_count==before+6&&m->requests_sent==12);
  assert(m->extra.state==MR_EXTRA_STOPPED&&m->extra.stop_error==-ENODATA);
  assert(m->extra.attempts==1&&m->extra.next==1);
  extra_core_still_reports(m);before=tx_count;run_one(m);
  assert(tx_count==before+6&&m->extra.attempts==1);
  extra_core_still_reports(m);destroy(p);groups++;
 }

 /* Opt-in remains independent, and requires the original read-only and
  * reporting opt-ins. A rejected combination cannot register or send. */
 for(unsigned missing=0;missing<2;missing++){
  reset();enable_extra_diagnostics=true;
  enable_readonly=missing!=0;enable_power_supply=missing==0;
  unsigned registrations=platform_registrations;
  struct platform_device denied={.dev={.parent=&parent,.of_node=&node}};
  assert(mr_init()==-EPERM&&platform_registrations==registrations);
  assert(mr_probe(&denied)==-EPERM&&!denied.dev.data&&!registered&&!registered_psy&&!tx_count);
  groups++;
 }
 reset();p=reporting_new();m=p->dev.data;raw_properties[3]=0x0b;
 for(unsigned i=0;i<6;i++)run_one(m);
 assert(!m->extra_enabled&&tx_count==36&&m->requests_sent==36&&!m->extra.attempts);
 extra_read_only(p);destroy(p);groups++;

 /* Only a fresh coherent online PD (the exact Xiaomi enum 0x0b) arms.
  * Unknown, USB, neighboring and sentinel types stay completely idle. */
 const u32 non_pd[]={0,1,0x0a,0x0c,0xffffffffU};
 for(unsigned n=0;n<ARRAY_SIZE(non_pd);n++){
  reset();p=extra_reporting_new();m=p->dev.data;raw_properties[3]=non_pd[n];
  run_one(m);assert(m->extra_enabled&&m->extra.state==MR_EXTRA_WAITING);
  assert(!m->extra.next&&!m->extra.attempts&&tx_count==6&&m->requests_sent==6);
  extra_read_only(p);extra_core_still_reports(m);destroy(p);groups++;
 }
 reset();p=extra_reporting_new();m=p->dev.data;raw_properties[0]=0;raw_properties[1]=16000;raw_properties[2]=0;raw_properties[4]=7;
 run_one(m);assert(m->extra.state==MR_EXTRA_WAITING&&!m->extra.attempts&&tx_count==6);
 assert(read_int(m,POWER_SUPPLY_PROP_ONLINE,0)==0);
 raw_properties[0]=1;raw_properties[1]=4966000;raw_properties[2]=494000;raw_properties[4]=3;
 run_one(m);assert(m->extra.state==MR_EXTRA_RUNNING&&m->extra.attempts==1&&tx_count==13);
 destroy(p);groups++;
 for(unsigned incoherent=0;incoherent<3;incoherent++){
  reset();p=extra_reporting_new();m=p->dev.data;
  if(incoherent==0)mode=REMOTE_ERROR;
  if(incoherent==1)flip_epoch=true;
  if(incoherent==2)raw_properties[1]=999999;
  run_one(m);assert(m->extra.state==MR_EXTRA_WAITING&&!m->extra.attempts&&tx_count==6);
  supply_unknown(m);mode=OK;flip_epoch=false;raw_properties[1]=4966000;
  run_one(m);assert(m->extra.state==MR_EXTRA_RUNNING&&m->extra.attempts==1&&tx_count==13);
  destroy(p);groups++;
 }

 /* One diagnostic GET follows each complete core round. Its sequence is
  * shared with the core, while its accounting and raw cache stay separate. */
 reset();p=extra_reporting_new();m=p->dev.data;extra_mode=MISMATCH_THEN_OK;
 extra_read_only(p);assert(!tx_count);
 u32 previous_seq=m->next_seq;
 for(unsigned round=0;round<MR_EXTRA_PROPERTIES;round++){
  before=tx_count;run_one(m);
  assert(tx_count==before+MR_PROPERTIES+1);
  assert(m->requests_sent==(round+1)*MR_PROPERTIES&&m->cache.round==round+1);
  assert(m->extra.attempts==round+1&&m->extra.next==round+1&&!m->extra.active);
  assert(m->extra.state==(round+1==MR_EXTRA_PROPERTIES?MR_EXTRA_COMPLETE:MR_EXTRA_RUNNING));
  for(unsigned i=0;i<MR_PROPERTIES;i++){
   assert(wire_properties[before+i]==mr_properties[i]);
   assert(m->cache.samples[i].property==mr_properties[i]);
   assert(wire_seqs[before+i]==previous_seq+1);previous_seq=wire_seqs[before+i];
  }
  assert(wire_properties[before+MR_PROPERTIES]==mr_extra_properties[round]);
  assert(wire_seqs[before+MR_PROPERTIES]==previous_seq+1);previous_seq=wire_seqs[before+MR_PROPERTIES];
  const struct mr_extra_sample *extra=&m->extra.samples[round];
  assert(extra->sample.property==mr_extra_properties[round]);
  assert(extra->sample.attempted&&extra->sample.response_seen&&!extra->sample.error);
  assert(extra->sample.raw==extra_raw_properties[round]&&extra->sample.seq==previous_seq);
  assert(extra->core_round==round+1&&extra->generation==m->generation);
  extra_read_only(p);extra_core_still_reports(m);
 }
 assert(tx_count==35&&m->requests_sent==30);
 for(unsigned i=0;i<3;i++)run_one(m);
 assert(tx_count==53&&m->extra.attempts==5&&m->extra.next==5);
 raw_properties[3]=1;run_one(m);raw_properties[3]=0x0b;
 mr_state(m,PMIC_GLINK_STATE_DOWN);mr_state(m,PMIC_GLINK_STATE_UP);
 before=tx_count;run_one(m);assert(tx_count==before+6&&m->extra.attempts==5&&m->extra.next==5);
 destroy(p);groups++;

 /* The first optional failure ends diagnostics for this instance. A
  * firmware rejection, send error or missing reply must not poison the
  * normal power-supply cache or its consecutive-timeout accounting. */
 const int extra_errors[]={REMOTE_ERROR,SEND_ERROR,SILENT};
 const int wanted_errors[]={-EREMOTEIO,-EIO,-ETIMEDOUT};
 for(unsigned failure=0;failure<ARRAY_SIZE(extra_errors);failure++){
  reset();p=extra_reporting_new();m=p->dev.data;extra_mode=extra_errors[failure];
  run_one(m);assert(tx_count==7&&m->requests_sent==6&&m->extra.attempts==1&&m->extra.next==1);
  assert(m->extra.state==MR_EXTRA_STOPPED&&m->extra.stop_error==wanted_errors[failure]);
  assert_invalid(&m->extra.samples[0].sample,wanted_errors[failure]);
  extra_read_only(p);extra_core_still_reports(m);
  extra_mode=OK;before=tx_count;run_one(m);
  assert(tx_count==before+6&&m->requests_sent==12&&m->extra.attempts==1&&m->extra.next==1);
  assert(m->extra.state==MR_EXTRA_STOPPED);extra_core_still_reports(m);
  destroy(p);groups++;
 }

 /* Losing PD or the required core coherence after arming consumes no new
  * diagnostic request and never rearms when the input becomes good again. */
 for(unsigned loss=0;loss<5;loss++){
  reset();p=extra_reporting_new();m=p->dev.data;run_one(m);assert(m->extra.attempts==1);
  if(loss==0)raw_properties[3]=1;
  if(loss==1){raw_properties[0]=0;raw_properties[1]=16000;raw_properties[2]=0;raw_properties[4]=7;}
  if(loss==2)mode=REMOTE_ERROR;
  if(loss==3)raw_properties[1]=999999;
  if(loss==4)flip_epoch=true;
  before=tx_count;run_one(m);assert(tx_count==before+6);
  assert(m->extra.state==MR_EXTRA_STOPPED&&m->extra.attempts==1&&m->extra.next==1);
  mode=OK;flip_epoch=false;raw_properties[0]=1;raw_properties[1]=4966000;raw_properties[2]=494000;raw_properties[3]=0x0b;raw_properties[4]=3;
  before=tx_count;run_one(m);assert(tx_count==before+6&&m->extra.state==MR_EXTRA_STOPPED&&m->extra.attempts==1);
  extra_core_still_reports(m);destroy(p);groups++;
 }
 /* A link epoch change between otherwise good rounds is still terminal. */
 reset();p=extra_reporting_new();m=p->dev.data;run_one(m);
 mr_state(m,PMIC_GLINK_STATE_DOWN);mr_state(m,PMIC_GLINK_STATE_UP);
 before=tx_count;run_one(m);assert(tx_count==before+6&&m->extra.state==MR_EXTRA_STOPPED&&m->extra.attempts==1);
 extra_core_still_reports(m);destroy(p);groups++;

 /* Suspend-length gaps expire the context even without a link callback.
  * The notification worker stops the optional run while withdrawing the
  * normal stale supply; the next good core round cannot rearm extras. */
 reset();p=extra_reporting_new();m=p->dev.data;run_one(m);
 before=tx_count;atomic_fetch_add(&fake_clock,20000ULL*1000000);
 run_work(&m->notify_work);
 assert(tx_count==before&&m->extra.state==MR_EXTRA_STOPPED&&m->extra.attempts==1);
 supply_unknown(m);run_one(m);
 assert(tx_count==before+6&&m->extra.attempts==1);extra_core_still_reports(m);
 destroy(p);groups++;

 /* A subsequent core timeout retains the core accounting semantics. */
 reset();p=extra_reporting_new();m=p->dev.data;run_one(m);mode=SILENT;
 before=tx_count;run_one(m);
 assert(tx_count==before+1&&m->consecutive_timeouts==1&&!m->finished);
 assert(m->extra.state==MR_EXTRA_STOPPED&&m->extra.attempts==1);
 mode=OK;run_one(m);extra_core_still_reports(m);
 assert(m->extra.attempts==1);destroy(p);groups++;

 /* Sequence exhaustion between a good six-GET core round and its optional
  * request must not wrap or reuse a wire sequence. The unsent optional
  * slot is terminal; the next core round stops on the global exhaustion. */
 reset();p=extra_reporting_new();m=p->dev.data;m->next_seq=U32_MAX-MR_PROPERTIES;
 run_one(m);
 assert(tx_count==6&&m->requests_sent==6&&m->next_seq==U32_MAX);
 assert(m->extra.state==MR_EXTRA_STOPPED&&m->extra.next==1&&!m->extra.attempts);
 assert_invalid(&m->extra.samples[0].sample,-EOVERFLOW);
 assert(!m->extra.samples[0].sample.attempted);
 run_one(m);assert(tx_count==6&&m->finished&&m->stop_reason==4);
 destroy(p);groups++;

 /* The original getter never inherits the extra allowlist. The extra
  * path also cannot be used without its independent opt-in and context. */
 reset();p=reporting_new();m=p->dev.data;run_one(m);
 struct mr_sample rejected;before=tx_count;
 mr_get(m,mr_extra_properties[0],&rejected);
 assert_invalid(&rejected,-EINVAL);assert(!rejected.attempted&&tx_count==before);
 mr_get_value(m,mr_extra_properties[0],&rejected,true,m->generation,m->cache.round);
 assert(rejected.error&&!rejected.attempted&&tx_count==before&&!m->extra.attempts);
 mr_get_value(m,0xdeadbeefU,&rejected,true,m->generation,m->cache.round);
 assert_invalid(&rejected,-EINVAL);assert(!rejected.attempted&&tx_count==before);
 destroy(p);groups++;

 /* A callback changing the epoch during the optional response invalidates
  * that response and prevents an optional follow-up on the new epoch. */
 reset();p=extra_reporting_new();m=p->dev.data;extra_flip_epoch=true;
 run_one(m);assert(tx_count==7&&m->extra.state==MR_EXTRA_STOPPED&&m->extra.attempts==1);
 assert(m->extra.stop_error&&m->extra.samples[0].sample.error);
 supply_unknown(m);extra_flip_epoch=false;before=tx_count;run_one(m);
 assert(tx_count==before+6&&m->extra.attempts==1);extra_core_still_reports(m);
 destroy(p);groups++;

 /* Late optional responses cannot resurrect a timed-out cache or satisfy
  * a subsequent core request: both property and shared sequence must match. */
 reset();p=extra_reporting_new();m=p->dev.data;extra_mode=SILENT;
 run_one(m);prior_request=last_request;assert(mr_extra_property_allowed(prior_request.property));
 struct mr_response late=reply(&prior_request);deliver(registered,&late,sizeof(late),false);
 assert(!m->pending&&m->extra.state==MR_EXTRA_STOPPED);
 assert_invalid(&m->extra.samples[0].sample,-ETIMEDOUT);
 extra_mode=OK;mode=OLD_THEN_OK;before=tx_count;run_one(m);
 assert(tx_count==before+6&&m->extra.attempts==1);extra_core_still_reports(m);
 destroy(p);groups++;

 /* Expiry also remains effective while the optional send is blocked. Its
  * completion after expiry cannot publish a successful diagnostic value. */
 reset();p=extra_reporting_new();m=p->dev.data;extra_mode=BLOCK_SEND;
 pthread_t expires_work;
 assert(!pthread_create(&expires_work,NULL,work_thread,m));wait_flag(&send_entered);
 assert(tx_count==7&&m->extra.active);atomic_fetch_add(&fake_clock,20000ULL*1000000);
 run_work(&m->notify_work);assert(m->extra.state==MR_EXTRA_STOPPED);
 supply_unknown(m);release_flag(&release_send);assert(!pthread_join(expires_work,NULL));
 assert(m->extra.samples[0].sample.error&&!m->extra.samples[0].sample.raw&&!m->extra.active);
 assert(m->extra.attempts==1&&!m->consecutive_timeouts&&!m->finished);
 extra_mode=OK;before=tx_count;run_one(m);
 assert(tx_count==before+6&&m->extra.attempts==1);extra_core_still_reports(m);
 destroy(p);groups++;

 /* Unload while an optional transport call is blocked must keep the
  * instance/client alive until that worker returns, exactly like the core. */
 reset();p=extra_reporting_new();m=p->dev.data;extra_mode=BLOCK_SEND;
 pthread_t work,remove;unsigned freed=frees,unregistered=unregisters;
 assert(!pthread_create(&work,NULL,work_thread,m));wait_flag(&send_entered);
 assert(tx_count==7&&m->extra.active&&m->requests_sent==6);
 assert(!pthread_create(&remove,NULL,remove_thread,p));
 for(;;){unsigned long flags;spin_lock_irqsave(&m->lock,flags);bool stopped=m->stopping;spin_unlock_irqrestore(&m->lock,flags);if(stopped)break;}
 assert(frees==freed&&unregisters==unregistered);
 release_flag(&release_send);assert(!pthread_join(work,NULL));assert(!pthread_join(remove,NULL));
 assert(frees==freed+1&&unregisters==unregistered+1&&!p->dev.data);free(p);groups++;
}
