static void helper_error(int op, int error)
{
    struct mca_quick_charge_info info;reset(&info);failing_op=op;failure=error;
    int result=mca_qc_quick_charge_update_ibus(&info);
    CHECK(result == error);CHECK(info.proc_data.ibus==777);
    CHECK(trace[trace_count-1].op==op);CHECK(calls[ADC]==1);
    CHECK(calls[CURRENT]==(op==CURRENT));CHECK(!calls[ADAPTER]);
    CHECK(info.proc_data.error_num[0]==(op==CURRENT));
}
static void tune_error(int op, int at, int error)
{
    struct mca_quick_charge_info info;reset(&info);failing_op=op;failing_at=at;failure=error;
    int status=123,result=mca_quick_charge_tune_vbus(&info,&status);
    CHECK(result == error);CHECK(status==123);CHECK(trace[trace_count-1].op==op);
    CHECK(calls[op]==at);CHECK(calls[ENABLE]==0);CHECK(calls[CURRENT]==0);
    CHECK(calls[ADAPTER]==at-(op==ADAPTER?0:1));
    CHECK(calls[SLEEP]==at-1);
    CHECK(info.proc_data.cur_adp_volt==9000+40*calls[ADAPTER]);
    if(op==VOLTAGE)CHECK(calls[ERRORHL]==at-1);
}
static void retry_error(int op, int at, int error)
{
    struct mca_quick_charge_info info;reset(&info);failing_op=op;failing_at=at;failure=error;
    int result=mca_qc_retry_to_enable_cp(&info);
    CHECK(result == error);CHECK(trace[trace_count-1].op==op);CHECK(calls[op]==at);
    CHECK(calls[ENABLE]==1);CHECK(!calls[VOLTAGE]);
    CHECK(calls[ADAPTER]==(op==ENABLE?0:at-(op==ADAPTER?0:1)));
    CHECK(info.proc_data.cur_adp_volt==9000+20*calls[ADAPTER]);
    if(op==ENABLE)CHECK(calls[SLEEP]==0 && calls[ADC]==0 && calls[CURRENT]==0);
    if(op==ADC)CHECK(calls[CURRENT]==at-1);
    if(op==CURRENT)CHECK(info.proc_data.error_num[0]==1);
}
static void qc_errorhl_error(int error)
{
    static int tag=1;
    struct mca_quick_charge_info info;reset(&info);voltage[0]=9000+tag++;
    failing_op=ERRORHL;failure=error;
    enum VBUS_TUNE_STAT status=XM_VBUS_TUNE_FAIL;
    int result=mca_get_qc_vbus_tune_status(&info,&status);
    CHECK(result == error);CHECK(status==XM_VBUS_TUNE_INIT);
    CHECK(trace_count==2 && trace[1].op==ERRORHL);
    CHECK(!calls[ENABLE] && !calls[ADAPTER] && !calls[QC_RESET]);
    reset(&info);voltage[0]=9000+tag++;failing_op=ERRORHL;failure=error;
    int final_status=123;
    result=actual_qc_open_loop(&info,&final_status);
    CHECK(result == error);CHECK(final_status==XM_VBUS_TUNE_INIT);
    CHECK(trace_count==2 && trace[1].op==ERRORHL);
    CHECK(!calls[ENABLE] && !calls[ADAPTER] && !calls[SLEEP] && !calls[QC_RESET]);
}
static void dump_trace(const char *label, struct mca_quick_charge_info *info,int status)
{
    printf("SUCCESS %s type=%d target=%d ibus=%d status=%d trace=",label,
        info->proc_data.adp_type,info->proc_data.cur_adp_volt,info->proc_data.ibus,status);
    for(int i=0;i<trace_count;i++)printf("%d:%d:%d:%d;",trace[i].op,trace[i].a,trace[i].b,trace[i].c);
    puts("");
}
static void success_matrix(void)
{
    for(int type=0;type<2;type++)for(int mode=0;mode<4;mode++){
        struct mca_quick_charge_info info;reset(&info);info.proc_data.adp_type=type?7:12;
        int step=type?200:40,status=123;
        if(mode==0)voltage[0]=9000;
        if(mode==1){voltage[0]=8800;voltage[1]=9000;voltage_n=2;}
        if(mode==2){voltage[0]=9400;voltage[1]=9000;voltage_n=2;}
        CHECK(mca_quick_charge_tune_vbus(&info,&status)==0);
        CHECK(status==(mode==3?XM_VBUS_TUNE_FAIL:XM_VBUS_TUNE_OK));
        CHECK(calls[ADAPTER]==(mode==0?0:mode==3?15:1));
        CHECK(info.proc_data.cur_adp_volt==9000+(mode==0?0:mode==2?-step:step*calls[ADAPTER]));
        dump_trace("tune",&info,status);
    }
    for(int type=0;type<2;type++)for(int mode=0;mode<3;mode++){
        struct mca_quick_charge_info info;reset(&info);info.proc_data.adp_type=type?7:12;
        if(mode==0)current[0]=250;
        if(mode==1){current[0]=100;current[1]=100;current[2]=250;current_n=3;}
        CHECK(mca_qc_retry_to_enable_cp(&info)==0);
        CHECK(calls[ENABLE]==1);CHECK(calls[ADAPTER]==(mode==0?0:mode==1?2:5));
        CHECK(calls[ADC]==calls[ADAPTER]+1 && calls[CURRENT]==calls[ADC]);
        CHECK(calls[SLEEP]==calls[ADC]);
        CHECK(info.proc_data.cur_adp_volt==9000+calls[ADAPTER]*(type?200:20));
        dump_trace("retry",&info,0);
    }
    const int qc_voltage[]={9011,2000,5012,12013};
    const enum VBUS_TUNE_STAT qc_status[]={XM_VBUS_TUNE_OK,XM_VBUS_TUNE_VBUS_LOW,XM_VBUS_TUNE_READY_UP,XM_VBUS_TUNE_READY_DOWN};
    for(int i=0;i<4;i++){
        struct mca_quick_charge_info info;reset(&info);voltage[0]=qc_voltage[i];
        enum VBUS_TUNE_STAT status=XM_VBUS_TUNE_INIT;
        CHECK(mca_get_qc_vbus_tune_status(&info,&status)==0);
        CHECK(status==qc_status[i]);CHECK(calls[VOLTAGE]==1);
        CHECK(calls[ERRORHL]==(i==1?0:1));
        CHECK(!calls[ENABLE] && !calls[ADAPTER] && !calls[QC_RESET]);
        dump_trace("qc-status",&info,status);
    }
}
int main(int argc,char **argv)
{
    if(argc>1){test_name=argv[1];
        if(!strcmp(test_name,"success")){success_matrix();return 0;}
        if(!strcmp(test_name,"adc_error")){helper_error(ADC,-ETIMEDOUT);return 0;}
        if(!strcmp(test_name,"current_error")){helper_error(CURRENT,-ETIMEDOUT);return 0;}
        if(!strcmp(test_name,"vbus_error")){tune_error(VOLTAGE,1,-ETIMEDOUT);return 0;}
        if(!strcmp(test_name,"tune_request_error")){tune_error(ADAPTER,1,-ETIMEDOUT);return 0;}
        if(!strcmp(test_name,"retry_enable_error")){retry_error(ENABLE,1,-ETIMEDOUT);return 0;}
        if(!strcmp(test_name,"retry_current_error")){retry_error(CURRENT,1,-ETIMEDOUT);return 0;}
        if(!strcmp(test_name,"retry_request_error")){retry_error(ADAPTER,1,-ETIMEDOUT);return 0;}
        if(!strcmp(test_name,"qc_errorhl_error")){qc_errorhl_error(-ETIMEDOUT);return 0;}
        return 2;
    }
    const int errors[]={-EIO,-ETIMEDOUT,-EREMOTEIO,2};
    for(unsigned e=0;e<sizeof(errors)/sizeof(errors[0]);e++){
        helper_error(ADC,errors[e]);helper_error(CURRENT,errors[e]);
        for(int at=1;at<=2;at++){
            tune_error(VOLTAGE,at,errors[e]);tune_error(ERRORHL,at,errors[e]);tune_error(ADAPTER,at,errors[e]);
            retry_error(ADC,at,errors[e]);retry_error(CURRENT,at,errors[e]);retry_error(ADAPTER,at,errors[e]);
        }
        retry_error(ENABLE,1,errors[e]);
        qc_errorhl_error(errors[e]);
    }
    success_matrix();
    printf("PASS actual quickchg CP error assertions=%lu\n",assertions);return 0;
}
