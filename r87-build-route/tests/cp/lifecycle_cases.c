static unsigned long lifecycle_assertions;
#define CHECK(x) do { lifecycle_assertions++; if (!(x)) { fprintf(stderr,"FAIL lifecycle line %d: %s\n",__LINE__,#x); exit(20); } } while (0)
static int at_trace(const char *name) {
    for (int i = 0; i < trace_n; i++) if (!strcmp(trace[i], name)) return i;
    return -1;
}
static void clean_resources_checked(void) {
    release_resources();
    CHECK(!resource_n && !allocated_chip);
    CHECK(!irq_owned && !irq_wake && !device_wake && !work_queued);
    CHECK(!nlpm_owned && !irq_gpio_owned && nlpm_level == 0);
    int irq = at_trace("free_irq"), cancel = at_trace("cancel_work"), quiet = at_trace("quiesce_charge"), low = at_trace("restore_nlpm"), memory = at_trace("free_memory");
    if (irq >= 0 && cancel >= 0) CHECK(irq < cancel);
    if (cancel >= 0 && quiet >= 0) CHECK(cancel < quiet);
    if (quiet >= 0 && low >= 0) CHECK(quiet < low);
    if (cancel >= 0) CHECK(cancel < memory);
    if (low >= 0) CHECK(low < memory);
    if (at_trace("disable_irq_wake") >= 0 && irq >= 0) CHECK(at_trace("disable_irq_wake") < irq);
}
static void success_and_fault_matrix(void) {
    struct i2c_client client = {.addr = 0x6e};
    reset_fixture(); CHECK(sc8581_probe(&client) == 0);
    int successful_calls = call_n; CHECK(successful_calls >= 18);
    CHECK(published == 1 && log_published == 1 && scheduled == 1);
    CHECK(allocated_chip && allocated_chip->chip_ok && allocated_chip->ovpgate_en && allocated_chip->i2c_is_working);
    CHECK(irq_owned && irq_wake && device_wake && nlpm_level == 1 && work_queued);
    CHECK(at_trace("init_device") < at_trace("request_irq"));
    CHECK(at_trace("provider_register") < at_trace("schedule_work"));
    clean_resources_checked();
    for (int failed = 1; failed <= successful_calls; failed++) {
        reset_fixture(); fail_call = failed; client = (struct i2c_client){.addr = 0x6e};
        int ret = sc8581_probe(&client);
        CHECK(ret == (failed == 1 ? -ENOMEM : -EIO));
        CHECK(call_n == failed);
        CHECK(!published && !log_published && !scheduled && !work_queued);
        if (allocated_chip) CHECK(!allocated_chip->chip_ok && !allocated_chip->i2c_is_working);
        clean_resources_checked();
    }
    reset_fixture(); test_role = SC8581_SLAVE; client = (struct i2c_client){.addr = 0x6e};
    CHECK(sc8581_probe(&client) == 0); CHECK(!nlpm_owned && nlpm_level == 0);
    CHECK(at_trace("nlpm_request") < 0 && at_trace("nlpm_high") < 0);
    CHECK(published == 1 && log_published == 1 && scheduled == 1);
    clean_resources_checked();
}
static void gpio_error_must_stop(void) {
    struct i2c_client client = {.addr = 0x6e}; reset_fixture(); fail_name = "nlpm_request";
    CHECK(sc8581_probe(&client) == -EIO); CHECK(!detect_calls && !init_calls && !published && !scheduled);
    clean_resources_checked();
}
static void registration_error_must_stop(void) {
    struct i2c_client client = {.addr = 0x6e}; reset_fixture(); fail_name = "provider_register";
    CHECK(sc8581_probe(&client) == -EIO); CHECK(!published && !log_published && !scheduled);
    clean_resources_checked();
}
static void init_error_must_release_irq(void) {
    struct i2c_client client = {.addr = 0x6e}; reset_fixture(); fail_name = "init_device";
    CHECK(sc8581_probe(&client) == -EIO); CHECK(!published && !scheduled);
    clean_resources_checked();
}
int main(int argc, char **argv) {
    if (argc > 1) {
        if (!strcmp(argv[1], "gpio")) gpio_error_must_stop();
        else if (!strcmp(argv[1], "provider")) registration_error_must_stop();
        else if (!strcmp(argv[1], "irq-cleanup")) init_error_must_release_irq();
        else return 2;
    } else {
        success_and_fault_matrix(); gpio_error_must_stop(); registration_error_must_stop(); init_error_must_release_irq();
    }
    printf("PASS CP lifecycle assertions=%lu\n", lifecycle_assertions); return 0;
}
