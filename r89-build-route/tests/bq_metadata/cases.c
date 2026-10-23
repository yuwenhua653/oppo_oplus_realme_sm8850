static struct i2c_client client;
static struct bq_fg_chip chip = {
    .client = &client, .regs = {0x3e},
    .data_lock = {PTHREAD_MUTEX_INITIALIZER, 1},
    .i2c_rw_lock = {PTHREAD_MUTEX_INITIALIZER, 2}
};
static void frame(int payload,u8 cell)
{
    memset(response,0,sizeof(response));
    response[0] = 0x4b; response[2] = 'M'; response[3] = cell;
    response[4] = 'P'; response[5] = 'V';
    response[35] = (u8)(payload + 4);
    response[34] = checksum(response,(u8)(payload + 2));
}
static void reset(void)
{
    assert(lock_rank == 0); WRITE_ONCE(chip.cell_name,NULL); chip.pm_suspend = 0;
    read_result = 2; write_result = 1; reads = writes = 0; frame(4,'F');
}
static void expect_failure(int error)
{
    const char *out = "untouched";
    const char *sentinel = out;
    assert(fg_get_one_batt_cell_info(&chip,&out) == error);
    assert(out == sentinel && !READ_ONCE(chip.cell_name) && lock_rank == 0);
    cases++;
}
static void recovery_and_cache(void)
{
    const char *out = "untouched";
    reset(); read_result = -EREMOTEIO;
    assert(fg_read_cell_vendor(&chip) == -EREMOTEIO && !chip.cell_name);
    /* The actual probe intentionally keeps this optional; callback retries it. */
    read_result = 2;
    assert(fg_get_one_batt_cell_info(&chip,&out) == 0 && strcmp(out,"atl") == 0);
    assert(reads == 2 && writes == 2); cases++;
    read_result = -EIO;
    assert(fg_get_one_batt_cell_info(&chip,&out) == 0 && strcmp(out,"atl") == 0);
    assert(reads == 2 && writes == 2); cases++;
    assert(fg_read_cell_vendor(&chip) == -EIO && strcmp(chip.cell_name,"atl") == 0); cases++;
    reset(); read_result = -ETIMEDOUT;
    for(int i = 0;i < 3;i++) expect_failure(-ETIMEDOUT);
    assert(reads == 3 && writes == 3);
    read_result = 2; frame(4,'J');
    assert(fg_get_one_batt_cell_info(&chip,&out) == 0 && strcmp(out,"coslight") == 0); cases++;
    assert(fg_get_one_batt_cell_info(NULL,&out) == -EINVAL);
    assert(fg_get_one_batt_cell_info(&chip,NULL) == -EINVAL); cases += 2;
}
static void all_mappings(void)
{
    static const struct {u8 byte;const char *name;} table[] = {
        {'A',"samsung"},{'B',"sony"},{'C',"sanyo"},{'D',"lg"},{'E',"panasonic"},
        {'F',"atl"},{'G',"byd"},{'H',"tws"},{'I',"lishen"},{'J',"coslight"},{'L',"lwn"}
    };
    for(unsigned byte = 0;byte <= 255;byte++) {
        const char *expected = "default", *out = NULL;
        for(unsigned i = 0;i < sizeof(table)/sizeof(table[0]);i++)
            if(table[i].byte == byte) expected = table[i].name;
        reset();frame(4,(u8)byte);
        assert(fg_get_one_batt_cell_info(&chip,&out) == 0 && strcmp(out,expected) == 0);
        assert(reads == 1 && writes == 1); cases++;
    }
}
static void invalid_frames(void)
{
    for(int length = 0;length < 4;length++) { reset();frame(length,'F'); expect_failure(-EMSGSIZE); }
    for(int payload = 4;payload <= 32;payload++) {
        const char *out = NULL;reset();frame(payload,'F');
        assert(fg_get_one_batt_cell_info(&chip,&out) == 0 && strcmp(out,"atl") == 0);cases++;
    }
    for(int length = 0;length <= 255;length++) if(length < 4 || length > 36) {
        reset();response[35] = (u8)length;expect_failure(-EPROTO);
    }
    for(int byte = 0;byte < 2;byte++) for(int bit = 0;bit < 8;bit++) {
        reset();response[byte] ^= (u8)(1u << bit);response[34] = checksum(response,6);
        expect_failure(-EPROTO);
    }
    for(int bit = 0;bit < 8;bit++) { reset();response[34] ^= (u8)(1u << bit); expect_failure(-EBADMSG); }
    reset();chip.pm_suspend = 1;expect_failure(-EAGAIN);assert(!reads && !writes);
    const int errors[] = {0,1,3,INT_MAX,-EIO,-ETIMEDOUT,-EREMOTEIO};
    for(unsigned i = 0;i < sizeof(errors)/sizeof(errors[0]);i++) {
        reset();read_result = errors[i];expect_failure(errors[i] < 0 ? errors[i] : -EIO);
    }
    const int write_errors[] = {0,2,INT_MAX,-EIO,-EREMOTEIO};
    for(unsigned i = 0;i < sizeof(write_errors)/sizeof(write_errors[0]);i++) {
        reset();write_result = write_errors[i];expect_failure(write_errors[i] < 0 ? write_errors[i] : -EIO);assert(!reads);
    }
}
static pthread_barrier_t start;
static void *worker(void *arg)
{
    const char **out = arg;
    int ret = pthread_barrier_wait(&start);assert(ret == 0 || ret == PTHREAD_BARRIER_SERIAL_THREAD);
    assert(fg_get_one_batt_cell_info(&chip,out) == 0 && strcmp(*out,"atl") == 0 && lock_rank == 0);
    return NULL;
}
static void concurrent_readers(void)
{
    pthread_t threads[8];const char *names[8] = {0};
    for(int round = 0;round < 32;round++) {
        reset();assert(pthread_barrier_init(&start,NULL,8) == 0);
        for(int i = 0;i < 8;i++) assert(pthread_create(&threads[i],NULL,worker,&names[i]) == 0);
        for(int i = 0;i < 8;i++) assert(pthread_join(threads[i],NULL) == 0);
        assert(pthread_barrier_destroy(&start) == 0);
        assert(reads >= 1 && reads <= 8 && reads == writes && strcmp(chip.cell_name,"atl") == 0);
        cases++;
    }
}
int main(void)
{
    recovery_and_cache();all_mappings();invalid_frames();concurrent_readers();
    printf("PASS %u production-function metadata/MAC/recovery/concurrency cases\n",cases);
    return 0;
}
