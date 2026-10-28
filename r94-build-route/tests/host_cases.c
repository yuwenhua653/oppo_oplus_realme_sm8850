/* Real driver functions are generated above this file by run_tests.py. */
static struct device_node flash_node, owner_node;
static struct device flash_device, owner_device;
static struct power_supply battery;
static struct qcom_flash_data flash;
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { \
    fprintf(stderr,"check failed at line %d: %s\n",__LINE__,#x); abort(); } } while (0)

static void reset(bool pmh, bool mca, bool smb)
{
    memset(&mock, 0, sizeof(mock));
    memset(&flash, 0, sizeof(flash));
    flash_node.compatible = pmh ? "qcom,pmh0101-flash-led" : "qcom,spmi-flash-led";
    owner_node.compatible = mca ? "mca,business_battery" : "qcom,battery-charger";
    flash_device = (struct device){ .of_node = &flash_node };
    owner_device = (struct device){ .of_node = &owner_node };
    battery = (struct power_supply){ .dev.parent = &owner_device };
    flash.dev = &flash_device;
    flash.use_smb_battery_interface = smb;
    flash.hw_type = QCOM_MVFLASH_3CH;
    mock.registered = &battery;
    mock.resistance = 100000;
    mock.voltage = 4000000;
    mock.current = -500000;
}
static int budget(void)
{
    int out = -12345;
    int rc = __qcom_flash_led_get_max_avail_current(&flash, &out);
    CHECK(rc == 0);
    CHECK(out >= 0 && out <= 2000);
    return out;
}
static void expect_error(int err)
{
    int out = -12345;
    CHECK(__qcom_flash_led_get_max_avail_current(&flash, &out) == err);
    CHECK(out == -12345);
    CHECK(!flash.debug_board_present);
}
static void selection_and_errors(void)
{
    reset(true, true, false);
    mock.qti_rc = -ENODEV;
    CHECK(budget() > 0);
    CHECK(mock.model_logs == 1 && mock.qti_calls == 0 && mock.rbatt_calls == 0);
    CHECK(mock.ocv_calls == 1 && mock.current_calls == 1);
    CHECK(!flash.debug_board_present);
    /* Neither a successful QTI value nor QTI's failure may define MCA model. */
    reset(true, true, false); mock.resistance = 0;
    CHECK(budget() > 0 && !flash.debug_board_present && mock.qti_calls == 0);

    for (int pmh = 0; pmh <= 1; pmh++) {
        for (int mca = 0; mca <= 1; mca++) {
            if (pmh && mca) continue;
            reset(pmh, mca, false); mock.qti_rc = -ENODEV;
            expect_error(-ENODEV);
            CHECK(mock.qti_calls == 1 && mock.model_logs == 0);
            CHECK(mock.ocv_calls == 0 && mock.current_calls == 0);
        }
    }
    /* Every missing identity component fails the match, even with PMH present. */
    for (int variant = 0; variant < 5; variant++) {
        reset(true, true, false); mock.qti_rc = -ENODEV;
        switch (variant) {
        case 0: flash.dev = NULL; break;
        case 1: flash_device.of_node = NULL; break;
        case 2: battery.dev.parent = NULL; break;
        case 3: owner_device.of_node = NULL; break;
        case 4: owner_node.compatible = "mca,business_charger"; break;
        }
        expect_error(-ENODEV);
        CHECK(mock.qti_calls == 1 && mock.model_logs == 0);
    }
    reset(true, true, true); mock.qti_rc = -ENODEV;
    CHECK(budget() > 0);
    CHECK(mock.model_logs == 0 && mock.qti_calls == 0);
    CHECK(mock.rbatt_calls == 1 && mock.ocv_calls == 1 && mock.current_calls == 1);

    int errors[] = {-EIO, -ENODEV, -EAGAIN, -ETIMEDOUT};
    for (unsigned i = 0; i < sizeof(errors)/sizeof(errors[0]); i++) {
        reset(true, true, true); mock.rbatt_rc = errors[i];
        expect_error(errors[i]);
        CHECK(mock.rbatt_calls == 1 && mock.ocv_calls == 0 && mock.current_calls == 0);
        CHECK(mock.qti_calls == 0 && mock.model_logs == 0);
        for (int smb = 0; smb <= 1; smb++) {
            reset(true, true, smb); mock.ocv_rc = errors[i];
            expect_error(errors[i]);
            CHECK(mock.current_calls == 0);
            reset(true, true, smb); mock.current_rc = errors[i];
            expect_error(errors[i]);
            CHECK(mock.ocv_calls == 1 && mock.current_calls == 1);
        }
    }
    reset(true, true, false); mock.registered = NULL;
    expect_error(-ENODEV);
    CHECK(mock.lookup_calls == 1 && mock.ocv_calls == 0 && mock.qti_calls == 0);
    mock.registered = &battery;
    CHECK(budget() > 0);
    CHECK(mock.lookup_calls == 2 && mock.model_logs == 1);
    /* Cached supply is reused: no additional lookup is introduced. */
    CHECK(budget() > 0 && mock.lookup_calls == 2);

    reset(false, false, false); mock.registered = NULL;
    CHECK(budget() == 2000); /* Legacy unrelated hardware behavior unchanged. */
    reset(false, false, false); mock.resistance = 0;
    CHECK(budget() == 2000 && flash.debug_board_present); /* Legacy debug board. */
}
static void numerical_and_differential(void)
{
    int volts[] = {2500000, 2799999, 2800000, 2849999, 2850000, 2850001,
                   3000000, 3299999, 3300000, 3300001, 3700000, 4000000,
                   4350000, 4445000, 4600000};
    int currents[] = {-10000000, -6000000, -4500001, -4500000, -4499999,
                      -2000000, -500000, -1, 0, 1, 500000, 2000000, 4500000};
    unsigned comparisons = 0;
    for (unsigned vi=0; vi<sizeof(volts)/sizeof(volts[0]); vi++) {
        for (unsigned ci=0; ci<sizeof(currents)/sizeof(currents[0]); ci++) {
            for (int hw=0; hw<3; hw++) {
                int model, qti, iio, old;
                reset(true, true, false);
                mock.voltage=volts[vi]; mock.current=currents[ci];
                flash.hw_type=hw; flash.total_ma=1250;
                mock.qti_rc=-ENODEV;
                model=budget();
                CHECK(!flash.debug_board_present && mock.qti_calls==0);
                reset(false, false, false);
                mock.voltage=volts[vi]; mock.current=currents[ci];
                flash.hw_type=hw; flash.total_ma=1250;
                qti=budget();
                CHECK(model==qti);
                CHECK(original_get_max(&flash, &old)==0);
                CHECK(qti==(old<0?0:old));
                reset(true, true, true);
                mock.voltage=volts[vi]; mock.current=currents[ci];
                flash.hw_type=hw; flash.total_ma=1250;
                iio=budget();
                CHECK(iio==model);
                CHECK(original_get_max(&flash, &old)==0);
                CHECK(iio==(old<0?0:old));
                comparisons++;
            }
        }
    }
    /* Independently derived physical budget examples (not preimage-only oracle). */
    struct { int voltage, current, expected; } examples[] = {
        {2900000, 0, 329}, {3000000, 0, 987},
        {3200000, -3000000, 329}, {2700000, -1000000, 0},
        {4400000, -4500000, 0}
    };
    for (unsigned i=0; i<sizeof(examples)/sizeof(examples[0]); i++) {
        reset(true,true,false);
        mock.voltage=examples[i].voltage; mock.current=examples[i].current;
        CHECK(budget()==examples[i].expected);
    }
    /* Explicitly force the preimage's unsafe negative budget. */
    reset(true, true, false); mock.voltage=2800000; mock.current=0;
    CHECK(budget()==0);
    int original=-12345;
    CHECK(original_get_max(&flash,&original)==0 && original<0);
    reset(true, true, false); mock.voltage=4000000; mock.current=-6000000;
    CHECK(budget()==0);
    CHECK(original_get_max(&flash,&original)==0 && original<0);
    /* Reduced voltage / greater discharge reduce the model budget. */
    reset(true,true,false); mock.voltage=3000000; mock.current=0;
    int low=budget();
    mock.voltage=3200000; int high=budget();
    CHECK(low<high);
    mock.current=-2000000;
    CHECK(budget()<high);
    printf("grid_comparisons=%u\n",comparisons);
}
int main(void)
{
    selection_and_errors();
    numerical_and_differential();
    printf("assertions=%u\nstatus=PASS\n",checks);
    return 0;
}
