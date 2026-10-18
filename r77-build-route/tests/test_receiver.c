/* Included after the unmodified production translation unit (except includes). */
static unsigned int tests;
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); abort(); } } while (0)
#define PASS(name) do { tests++; printf("PASS %s\n", name); } while (0)

static void make_device(struct platform_device *pdev, struct device_node *node)
{
 memset(pdev, 0, sizeof(*pdev)); memset(node, 0, sizeof(*node));
 node->available = true; node->compatible = true; node->count = MT_CELLS;
 memcpy(node->cells, mt_expected, sizeof(node->cells));
 pdev->dev.of_node = node; pdev->dev.kobj.owner = &pdev->dev;
}
static void free_device(struct platform_device *pdev)
{
 if (pdev->dev.allocation) {
  struct mt_observer *obs = pdev->dev.allocation;
  CHECK(!pthread_mutex_destroy(&obs->lock.value)); free(obs);
 }
 memset(pdev, 0, sizeof(*pdev));
}
static struct device_attribute *input_attr(unsigned int id)
{
 static struct device_attribute *attrs[] = {
  &dev_attr_wired_ctrl_limit, &dev_attr_wired_chg_curr,
  &dev_attr_wired_chg_curr2, &dev_attr_wired_thermal_remove,
 };
 CHECK(id < MT_INPUTS); return attrs[id];
}
static ssize_t put(struct platform_device *pdev, unsigned int id, const char *s)
{
 struct device_attribute *attr = input_attr(id);
 return attr->store(&pdev->dev, attr, s, strlen(s));
}
static void snapshot(struct platform_device *pdev, char *buf)
{
 memset(buf, 0xa5, PAGE_SIZE);
 ssize_t n = dev_attr_snapshot.show(&pdev->dev, &dev_attr_snapshot, buf);
 CHECK(n > 0 && n < PAGE_SIZE && buf[n] == '\0');
 CHECK(strstr(buf, "source_verified=0\n"));
 CHECK(strstr(buf, "eligible_for_control=0\n"));
 CHECK(strstr(buf, "hardware_applied=0\n"));
 CHECK(strstr(buf, "active_mode_selected=0\n"));
 CHECK(strstr(buf, "sensor_freshness=unknown\n"));
 CHECK(strstr(buf, "request_ttl=undefined\n"));
 CHECK(strstr(buf, "timestamp_kind=boottime_receipt\n"));
 CHECK(strstr(buf, "timestamp_semantics=request_receipt_not_sensor_sample\n"));
 CHECK(strstr(buf, "table_scope=probe_snapshot\n"));
 CHECK(strstr(buf, "dt_table_match_at_probe=1\n"));
}
static void rejected(struct platform_device *pdev, unsigned int id, const char *s, size_t n)
{
 char before[PAGE_SIZE], after[PAGE_SIZE]; snapshot(pdev, before);
 struct device_attribute *attr = input_attr(id);
 CHECK(attr->store(&pdev->dev, attr, s, n) < 0);
 snapshot(pdev, after); CHECK(!strcmp(before, after));
}
static void test_disabled(void)
{
 struct platform_device pdev; struct device_node node; make_device(&pdev, &node);
 CHECK(!enable_observer); CHECK(mt_init() == -EPERM); CHECK(mt_probe(&pdev) == -EPERM);
 CHECK(!test_registers && !test_adds && !test_allocations);
 CHECK(!strcmp(test_parameter_name, "enable_observer"));
 CHECK(!strcmp(test_parameter_type, "bool")); CHECK(test_parameter_mode == 0444);
 enable_observer = true; test_register_error = -EBUSY;
 CHECK(mt_init() == -EBUSY); CHECK(test_registers == 1);
 test_register_error = 0; CHECK(mt_init() == 0); CHECK(test_registers == 2);
 mt_exit(); CHECK(test_unregisters == 1); PASS("default-disabled-and-registration-error");
}
static void test_dt(void)
{
 struct platform_device pdev; struct device_node node; make_device(&pdev, &node);
 CHECK(mt_check_table(NULL) == -ENODEV);
 node.available = false; CHECK(mt_probe(&pdev) == -ENODEV); node.available = true;
 node.compatible = false; CHECK(mt_probe(&pdev) == -ENODEV); node.compatible = true;
 int counts[] = {-EINVAL, -ENODATA, -ENOENT, 0, 1, 149, 151, 600};
 for (size_t i = 0; i < sizeof(counts)/sizeof(counts[0]); i++) {
  node.count = counts[i]; CHECK(mt_probe(&pdev) == -EINVAL);
 }
 node.count = MT_CELLS; node.read_error = -EIO; CHECK(mt_probe(&pdev) == -EIO);
 node.read_error = 0;
 for (unsigned int i = 0; i < MT_CELLS; i++) {
  node.cells[i]++; CHECK(mt_probe(&pdev) == -EINVAL); node.cells[i]--;
 }
 CHECK(!test_adds && !test_allocations); CHECK(mt_check_table(&node) == 0);
 PASS("DT-domain-length-read-errors-and-all-150-cell-mutations");
}
static void test_probe_failures(void)
{
 struct platform_device pdev; struct device_node node; make_device(&pdev, &node);
 test_alloc_fail = true; CHECK(mt_probe(&pdev) == -ENOMEM); CHECK(!pdev.dev.data);
 test_alloc_fail = false; test_add_error = -EEXIST;
 CHECK(mt_probe(&pdev) == -EEXIST); CHECK(!pdev.dev.data && !test_published_group);
 test_add_error = 0; free_device(&pdev); PASS("allocation-and-sysfs-publication-failure");
}
static void test_initial_and_permissions(void)
{
 struct platform_device pdev; struct device_node node; char buf[PAGE_SIZE];
 make_device(&pdev, &node); CHECK(mt_probe(&pdev) == 0);
 CHECK(test_published_group == &mt_group); CHECK(!strcmp(mt_group.name, "myron_buck_thermal"));
 CHECK(!strcmp(mt_driver.driver.name, "myron_buck_thermal"));
 CHECK(!strcmp(mt_of_match[0].compatible, "mca_charger_thermal"));
 for (unsigned int i = 0; i < MT_INPUTS; i++) {
  struct device_attribute *attr = input_attr(i);
  CHECK(mt_group.attrs[i] == &attr->attr); CHECK(attr->attr.mode == 0600);
  CHECK(!strcmp(attr->attr.name, mt_names[i])); CHECK(attr->show(&pdev.dev, attr, buf) == -ENODATA);
 }
 CHECK(mt_group.attrs[4] == &dev_attr_snapshot.attr && !mt_group.attrs[5]);
 CHECK(dev_attr_snapshot.attr.mode == 0444 && !dev_attr_snapshot.store);
 snapshot(&pdev, buf); CHECK(strstr(buf, "accepted_sequence=0\n"));
 for (unsigned int i = 0; i < MT_INPUTS; i++) {
  char key[100]; snprintf(key, sizeof(key), "%s.raw=unknown\n", mt_names[i]); CHECK(strstr(buf, key));
  snprintf(key, sizeof(key), "%s.seen=0\n", mt_names[i]); CHECK(strstr(buf, key));
 }
 CHECK(strstr(buf, "table_observed_row_index=none\n"));
 mt_remove(&pdev); free_device(&pdev); PASS("unknown-startup-exact-group-and-modes");
}
static void test_input_semantics(void)
{
 struct platform_device pdev; struct device_node node; char buf[PAGE_SIZE];
 make_device(&pdev, &node); CHECK(mt_probe(&pdev) == 0); atomic_store(&test_clock, 1000);
 CHECK(put(&pdev, MT_LEVEL, "0\n") == 2); snapshot(&pdev, buf);
 CHECK(strstr(buf, "wired_ctrl_limit.meaning=no_table_selection\n"));
 CHECK(strstr(buf, "table_observed_row_index=none\n"));
 CHECK(put(&pdev, MT_LEVEL, "1") == 1); snapshot(&pdev, buf);
 CHECK(strstr(buf, "table_observed_row_index=0\n"));
 CHECK(strstr(buf, "table_observed_row_cells_mA=1900,1500,1900,3000,13500,13500,13500,13500,13500,13500\n"));
 CHECK(put(&pdev, MT_LEVEL, "15\n") == 3); snapshot(&pdev, buf);
 CHECK(strstr(buf, "table_observed_row_index=14\n"));
 CHECK(strstr(buf, "table_observed_row_cells_mA=1100,600,500,500,500,500,500,500,500,500\n"));
 rejected(&pdev, MT_LEVEL, "16", 2);
 CHECK(put(&pdev, MT_CURRENT, "0") == 1); snapshot(&pdev, buf);
 CHECK(strstr(buf, "wired_chg_curr.meaning=raw_zero_observed\n"));
 CHECK(put(&pdev, MT_CURRENT, "2147483647\n") == 11);
 CHECK(put(&pdev, MT_CURRENT2, "1\n") == 2);
 struct mt_observer *obs = pdev.dev.data;
 CHECK(obs->input[MT_CURRENT].raw == INT_MAX && obs->input[MT_CURRENT2].raw == 1);
 CHECK(obs->input[MT_LEVEL].raw == 15); CHECK(obs->accepted_sequence == 6);
 CHECK(obs->input[MT_CURRENT].sequence == 5 && obs->input[MT_CURRENT].boottime_ns == 1005);
 CHECK(obs->input[MT_CURRENT2].sequence == 6 && obs->input[MT_CURRENT2].boottime_ns == 1006);
 for (unsigned int i = MT_CURRENT; i <= MT_CURRENT2; i++) {
  rejected(&pdev, i, "2147483648", 10); rejected(&pdev, i, "4294967295", 10);
 }
 CHECK(put(&pdev, MT_REMOVE, "1") == 1); snapshot(&pdev, buf);
 CHECK(strstr(buf, "wired_thermal_remove.meaning=removal_requested\n"));
 CHECK(obs->input[MT_LEVEL].raw == 15 && obs->input[MT_CURRENT].raw == INT_MAX);
 CHECK(put(&pdev, MT_REMOVE, "0") == 1); rejected(&pdev, MT_REMOVE, "2", 1);
 CHECK(put(&pdev, MT_CURRENT2, "1\n") == 2);
 CHECK(obs->input[MT_CURRENT2].sequence == 9 && obs->input[MT_CURRENT2].boottime_ns == 1009);
 CHECK(dev_attr_wired_chg_curr.show(&pdev.dev, &dev_attr_wired_chg_curr, buf) == 11);
 CHECK(!strcmp(buf, "2147483647\n"));
 /* Matching is at probe; later DT fixture mutation must not be claimed live. */
 node.cells[0]++; snapshot(&pdev, buf); CHECK(strstr(buf, "table_scope=probe_snapshot\n"));
 mt_remove(&pdev); free_device(&pdev); PASS("level-row-current-channel-zero-removal-and-receipt-semantics");
}
static void test_rejection_preserves_state(void)
{
 struct platform_device pdev; struct device_node node; make_device(&pdev, &node); CHECK(mt_probe(&pdev) == 0);
 const char *bad[] = {"", "\n", "-1", "-0", "+1", " 1", "1 ", "1\n\n", "1\r\n", "1x", "0x1", "1.0", "1\n2", "4294967296", "9999999999999999999999999999"};
 for (unsigned int id = 0; id < MT_INPUTS; id++) {
  CHECK(put(&pdev, id, "1") == 1);
  for (size_t j = 0; j < sizeof(bad)/sizeof(bad[0]); j++) rejected(&pdev, id, bad[j], strlen(bad[j]));
  const char nul[] = {'1', '\0', '2'}; rejected(&pdev, id, nul, sizeof(nul));
 }
 struct mt_observer *obs = pdev.dev.data; obs->accepted_sequence = U64_MAX;
 for (unsigned int i = 0; i < MT_INPUTS; i++) {
  char before[PAGE_SIZE], after[PAGE_SIZE]; snapshot(&pdev, before);
  CHECK(put(&pdev, i, "0") == -EOVERFLOW); snapshot(&pdev, after); CHECK(!strcmp(before, after));
 }
 mt_remove(&pdev); free_device(&pdev); PASS("strict-syntax-domain-overflow-and-error-immutability");
}

struct concurrency { struct platform_device *pdev; atomic_uint done; };
struct writer { struct concurrency *shared; unsigned int id; };
static void *write_worker(void *arg)
{
 struct writer *writer = arg;
 for (unsigned int n = 1; n <= 2000; n++) {
  char text[32]; unsigned int value = writer->id == MT_LEVEL ? n % 16 : writer->id == MT_REMOVE ? n % 2 : n;
  int len = snprintf(text, sizeof(text), "%u", value);
  CHECK(put(writer->shared->pdev, writer->id, text) == len);
 }
 atomic_fetch_add(&writer->shared->done, 1); return NULL;
}
static u64 get_num(const char *text, const char *key)
{
 const char *at = strstr(text, key); CHECK(at); at += strlen(key);
 char *end; unsigned long long n = strtoull(at, &end, 10); CHECK(end != at && *end == '\n'); return n;
}
static void test_concurrency(void)
{
 struct platform_device pdev; struct device_node node; make_device(&pdev, &node); CHECK(mt_probe(&pdev) == 0);
 atomic_store(&test_clock, 10000); struct concurrency shared = {.pdev = &pdev};
 pthread_t threads[MT_INPUTS]; struct writer args[MT_INPUTS];
 for (unsigned int i = 0; i < MT_INPUTS; i++) {
  args[i].shared = &shared; args[i].id = i; CHECK(!pthread_create(&threads[i], NULL, write_worker, &args[i]));
 }
 unsigned int snapshots = 0;
 do {
  char buf[PAGE_SIZE], key[96]; snapshot(&pdev, buf); u64 latest = get_num(buf, "accepted_sequence=");
  for (unsigned int i = 0; i < MT_INPUTS; i++) {
   snprintf(key, sizeof(key), "%s.seen=", mt_names[i]); u64 seen = get_num(buf, key);
   snprintf(key, sizeof(key), "%s.sequence=", mt_names[i]); u64 seq = get_num(buf, key);
   snprintf(key, sizeof(key), "%s.boottime_ns=", mt_names[i]); u64 stamp = get_num(buf, key);
   CHECK(seq <= latest); CHECK(seen ? stamp == seq + 10000 : seq == 0 && stamp == 0);
   if (seen && i == MT_LEVEL) {
    u64 level = get_num(buf, "wired_ctrl_limit.raw=");
    if (!level) CHECK(strstr(buf, "table_observed_row_index=none\n"));
    else CHECK(get_num(buf, "table_observed_row_index=") == level - 1);
   }
  }
  snapshots++;
 } while (atomic_load(&shared.done) != MT_INPUTS);
 for (unsigned int i = 0; i < MT_INPUTS; i++) CHECK(!pthread_join(threads[i], NULL));
 CHECK(((struct mt_observer *)pdev.dev.data)->accepted_sequence == 8000); CHECK(snapshots > 0);
 mt_remove(&pdev); free_device(&pdev); PASS("four-writers-and-whole-snapshot-mutex-coherence-8000-writes");
}
static void during_remove(struct device *dev)
{
 struct mt_observer *obs = dev->data; CHECK(obs);
 CHECK(!pthread_mutex_trylock(&obs->lock.value)); CHECK(!pthread_mutex_unlock(&obs->lock.value));
 char buf[PAGE_SIZE]; CHECK(snapshot_show(dev, &dev_attr_snapshot, buf) > 0);
 CHECK(wired_ctrl_limit_store(dev, &dev_attr_wired_ctrl_limit, "15", 2) == 2);
}
static void test_remove_order(void)
{
 struct platform_device pdev; struct device_node node; char buf[PAGE_SIZE]; make_device(&pdev, &node); CHECK(mt_probe(&pdev) == 0);
 test_drain_callback = during_remove; mt_remove(&pdev); test_drain_callback = NULL;
 CHECK(!pdev.dev.data && !test_published_group);
 CHECK(snapshot_show(&pdev.dev, &dev_attr_snapshot, buf) == -ENODEV);
 for (unsigned int i = 0; i < MT_INPUTS; i++) {
  struct device_attribute *attr = input_attr(i);
  CHECK(attr->show(&pdev.dev, attr, buf) == -ENODEV);
  CHECK(attr->store(&pdev.dev, attr, "1", 1) == -ENODEV);
 }
 free_device(&pdev); PASS("remove-group-drain-before-drvdata-clear-no-lock-held-model");
}
int main(void)
{
 test_disabled(); test_dt(); test_probe_failures(); test_initial_and_permissions();
 test_input_semantics(); test_rejection_preserves_state(); test_concurrency(); test_remove_order();
 printf("PASS all %u production-function groups\n", tests); return 0;
}
