static int injected_result, mock_calls;
static bool check_initialized;
static int fg_mac_read_block(struct bq_fg_chip *bq,u16 cmd,u8 *buf,u8 length)
{
    assert(bq && cmd == FG_MAC_CMD_CHEM_NAME && length == 4 && lock_rank == 0);
    mock_calls++;
    if(check_initialized) for(unsigned i = 0;i < 40;i++) assert(buf[i] == 0);
    /* Deliberately corrupt the callee output even on an error. */
    memset(buf,0xff,length);buf[1] = 'F';return injected_result;
}
/* PRODUCTION_FUNCTIONS */
int main(void)
{
    struct bq_fg_chip chip = {0};const char *out = "sentinel";
#ifdef BEFORE_DEFECT
    injected_result = -EREMOTEIO;
    assert(fg_read_cell_vendor(&chip) == 0 && chip.cell_name == NULL && mock_calls == 1);
    injected_result = 0;
    assert(fg_get_one_batt_cell_info(&chip,&out) == -1 && mock_calls == 1 && strcmp(out,"sentinel") == 0);
    puts("PASS: original swallows metadata errno and never retries from getter");
#else
    check_initialized = true;
    const int faults[] = {-EREMOTEIO,-EAGAIN,-EPROTO,-EBADMSG,-EMSGSIZE,-ENOMEM,-EIO,1,2,INT_MAX};
    for(unsigned i = 0;i < sizeof(faults)/sizeof(faults[0]);i++) {
        injected_result = faults[i];out = "sentinel";
        assert(fg_get_one_batt_cell_info(&chip,&out) == (faults[i] < 0 ? faults[i] : -EIO));
        assert(!chip.cell_name && strcmp(out,"sentinel") == 0);cases++;
    }
    injected_result = 0;
    assert(fg_get_one_batt_cell_info(&chip,&out) == 0 && strcmp(out,"atl") == 0);cases++;
    int calls_before = mock_calls;
    injected_result = -EREMOTEIO;
    assert(fg_get_one_batt_cell_info(&chip,&out) == 0 && mock_calls == calls_before);cases++;
    printf("PASS %u direct-MAC-error/output/cache cases\n",cases);
#endif
    return 0;
}
