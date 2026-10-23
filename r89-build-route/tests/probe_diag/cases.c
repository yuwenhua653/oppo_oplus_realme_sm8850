static int mca_quick_charge_parse_dt(struct mca_quick_charge_info *info)
{
    call("parse_dt;");
    info->has_gbl_batt_para=global_flag;
    info->batt_type=0;
    return mca_quick_charge_parse_batt_info(info,0);
}
static void reset(void)
{
    for(int i=0;i<alloc_count;i++)if(!freed[i])free(allocs[i]);
    alloc_count=0;last_info=NULL;trace_len=0;trace[0]=0;
    fg_ready=1;cp_vendor=2;cp_result=cp_master=cp_slave=0;missing_voter=-1;
    cell_error=slave_error=create_error=alloc_error=count_error=temp_error=integer_error=0;
    global_flag=hwid_missing=global_missing=false;hwid.country_version=CountryCN;
    cell_name="atl";device_name="XM88@";pdev.dev.of_node=&local_node;
}
static void snapshot(const char *stage,int result,int dependency)
{
#ifdef DIAG_ENABLED
    char buf[PAGE_SIZE],expected[100];
    int n=retained_ops->get(buf,NULL);
    check(param_permissions==0444,"parameter must remain read-only");
    check(n>0 && n<400,"bounded snapshot");
    snprintf(expected,sizeof(expected),"stage=%s ",stage);check(strstr(buf,expected)!=NULL,expected);
    snprintf(expected,sizeof(expected),"probe_errno=%d ",result);check(strstr(buf,expected)!=NULL,expected);
    snprintf(expected,sizeof(expected),"dependency_errno=%d ",dependency);check(strstr(buf,expected)!=NULL,expected);
    check(strstr(buf,"active=0 ")!=NULL,"probe must be inactive after return");
#else
    (void)stage;(void)result;(void)dependency;
#endif
}
static void run(int id,int expected,const char *stage,int dependency)
{
    scenario=id;
    int actual=mca_quick_charge_probe(&pdev);
    check(actual==expected,"legacy probe return changed");snapshot(stage,expected,dependency);
    printf("%02d return=%d %s\n",id,actual,trace);
}
#ifdef DIAG_ENABLED
static pthread_mutex_t ordering_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t ordering_cond=PTHREAD_COND_INITIALIZER;
static int ordering_state;
static struct mca_quick_charge_info older_info, newer_info;
static void *older_probe(void *unused)
{
    (void)unused;
    mca_quick_charge_diag_begin();
    mca_quick_charge_diag_attach(&older_info);
    pthread_mutex_lock(&ordering_lock);
    ordering_state=1;pthread_cond_broadcast(&ordering_cond);
    while(ordering_state!=2)pthread_cond_wait(&ordering_cond,&ordering_lock);
    pthread_mutex_unlock(&ordering_lock);
    mca_quick_charge_diag_attach(&older_info);
    mca_quick_charge_diag_note(&older_info,"older_probe_failed",-EIO);
    mca_quick_charge_diag_context(&older_info,99,1,1);
    mca_quick_charge_diag_cell(&older_info,"old");
    mca_quick_charge_diag_table(&older_info,"old_table");
    mca_quick_charge_diag_finish("older_probe_failed",-EIO,-EIO);
    return NULL;
}
static void concurrent_owners(void)
{
    pthread_t thread;
    char before[PAGE_SIZE],after[PAGE_SIZE];
    check(!pthread_create(&thread,NULL,older_probe,NULL),"thread create");
    pthread_mutex_lock(&ordering_lock);
    while(ordering_state!=1)pthread_cond_wait(&ordering_cond,&ordering_lock);
    pthread_mutex_unlock(&ordering_lock);
    mca_quick_charge_diag_begin();
    mca_quick_charge_diag_attach(&newer_info);
    mca_quick_charge_diag_context(&newer_info,0,0,0);
    mca_quick_charge_diag_cell(&newer_info,"atl");
    mca_quick_charge_diag_table(&newer_info,"new_table");
    mca_quick_charge_probe_status_get(before,NULL);
    pthread_mutex_lock(&ordering_lock);ordering_state=2;pthread_cond_broadcast(&ordering_cond);pthread_mutex_unlock(&ordering_lock);
    check(!pthread_join(thread,NULL),"thread join");
    mca_quick_charge_probe_status_get(after,NULL);
    check(!strcmp(before,after),"older task must not replace newer attempt snapshot");
    mca_quick_charge_diag_finish("bound",0,0);
    snapshot("bound",0,0);
}
#endif
int main(void)
{
    reset();fg_ready=-EIO;run(1,-EPROBE_DEFER,"fg_ready",-EIO);
    reset();fg_ready=0;run(2,-EPROBE_DEFER,"fg_ready",0);
    reset();alloc_error=1;run(3,-ENOMEM,"allocate",-ENOMEM);
    reset();cp_vendor=0;cp_master=-EAGAIN;run(4,-EPROBE_DEFER,"cp_ready",-EAGAIN);
    for(int i=0;i<5;i++){
        static const char *stages[]={"voter_input_suspend","voter_buck_input","voter_buck_charge_curr","voter_term_volt","voter_flip_charge_curr"};
        reset();missing_voter=i;run(5+i,-EPROBE_DEFER,stages[i],-ENOENT);
    }
    reset();cell_error=-EIO;run(10,-EPROBE_DEFER,"main_cell",-EIO);
    reset();cell_name=NULL;run(11,-EPROBE_DEFER,"main_cell",-ENOENT);
    reset();cell_name="coslight";global_flag=true;hwid.country_version=2;run(12,-1,"battery_table_match",-ENOENT);
    reset();global_flag=true;hwid.country_version=2;global_missing=true;run(13,-1,"battery_node",-ENOENT);
    reset();count_error=-EINVAL;run(14,-1,"battery_count",-EINVAL);
    reset();temp_error=-ENOENT;run(15,-1,"temp_count",-ENOENT);
    reset();integer_error=-ERANGE;run(16,-1,"temp_integer",-ERANGE);
    reset();create_error=-ENOMEM;run(17,-EPROBE_DEFER,"create_voter",-ENOMEM);
    reset();run(18,0,"bound",0);
#ifdef DIAG_ENABLED
    char before[PAGE_SIZE],after[PAGE_SIZE];
    mca_quick_charge_probe_status_get(before,NULL);
    check(strstr(before,"attempt=18 ")!=NULL,"attempt increments across all retries");
    check(strstr(before,"country=0 global_table=0 mode=0 cell=atl table=batt_para_atl")!=NULL,"selected metadata");
    mca_quick_charge_diag_note(last_info,"should_not_replace",-EIO);
    mca_quick_charge_diag_context(last_info,99,1,1);
    mca_quick_charge_diag_cell(last_info,"coslight");
    mca_quick_charge_diag_table(last_info,"other");
    mca_quick_charge_probe_status_get(after,NULL);
    check(!strcmp(before,after),"runtime updates must not change completed probe snapshot");
#endif
    reset();cell_name="coslight";run(19,0,"bound",0);
    reset();global_flag=true;hwid.country_version=2;run(20,0,"bound",0);
    reset();fg_ready=-ENODEV;run(21,-EPROBE_DEFER,"fg_ready",-ENODEV);
#ifdef DIAG_ENABLED
    mca_quick_charge_probe_status_get(after,NULL);
    check(strstr(after,"country=-1 global_table=-1 mode=-1 cell=<unread> table=<unselected>")!=NULL,"retry clears stale context");
#endif
    reset();cp_vendor=0;cp_result=-EIO;cp_master=-EAGAIN;cp_slave=-ENODEV;run(22,-EPROBE_DEFER,"cp_ready",-EIO);
    reset();cp_vendor=0;cp_master=-EAGAIN;cp_slave=-EINVAL;run(23,-EPROBE_DEFER,"cp_ready",-EAGAIN);
    reset();cp_vendor=0;cp_slave=-EINVAL;run(24,-EPROBE_DEFER,"cp_ready",-EINVAL);
#ifdef DIAG_ENABLED
    concurrent_owners();
#endif
    reset();fprintf(stderr,"PASS %u checks, 24 production probe scenarios\n",checks);return 0;
}
