#!/usr/bin/env python3
"""Exercise the actual driver PM functions against mocked SPI/PM/resources.

This checks ordering and error unwind, not hardware or power consumption.
The full CI build separately compiles the complete driver against Linux.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def function(source, name):
    start = source.index('static int ' + name + '(')
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


HARNESS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
struct device { struct { int usage_count; } power; } dev;
struct spi_controller { bool suspended; } controller;
struct spi_geni_master {
    bool system_suspend_managed, is_xfer_in_progress, is_le_vm, is_la_vm;
    bool gsi_mode, shared_ee, shared_se;
    struct { int clk; } spi_rsc;
    int m_ahb_clk, s_ahb_clk, irq, spi_kpi, ipc_log_kpi, ipc;
    struct device *dev;
} master;
static char events[128];
static int stop_error, restart_error, force_resume_error, fault;
static int irq_depth, pm_depth;
static bool runtime_suspended;
static void event(char c) { size_t n = strlen(events); events[n] = c; events[n+1] = 0; }
#define get_spi_master(d) ((void)(d), &controller)
#define spi_controller_get_devdata(s) ((void)(s), &master)
#define atomic_read(p) (*(p))
#define SPI_LOG_DBG(...) ((void)0)
#define dev_err(...) ((void)0)
#define geni_capture_start_time(...) (0ULL)
#define geni_capture_stop_time(...) ((void)start_time)
#define geni_se_common_clks_off(...) event('x')
#define geni_se_resources_off(...) (event('p'), fault == 2 ? -EIO : 0)
#define geni_se_resources_on(...) (event('P'), 0)
#define geni_icc_disable(...) (event('c'), fault == 3 ? -EIO : 0)
#define geni_icc_enable(...) (event('C'), 0)
#define spi_geni_levm_suspend_proc(...) (event('L'), 0)
static void disable_irq(int irq) { (void)irq; event('i'); ++irq_depth; }
static void enable_irq(int irq) { (void)irq; event('I'); --irq_depth; }
static int spi_geni_gpi_pause_resume(struct spi_geni_master *m, bool suspend)
{
    (void)m; event(suspend ? 'd' : 'D');
    return suspend && fault == 1 ? -EIO : 0;
}
static int spi_controller_suspend(struct spi_controller *s)
{
    event('Q'); s->suspended = true; return stop_error;
}
static int spi_controller_resume(struct spi_controller *s)
{
    event('q'); s->suspended = false; return restart_error;
}
static int spi_geni_runtime_suspend(struct device *dev);
static int pm_runtime_force_suspend(struct device *d)
{
    int ret;
    event('F'); ++pm_depth;
    if (runtime_suspended) return 0;
    ret = spi_geni_runtime_suspend(d);
    if (ret) --pm_depth;
    else runtime_suspended = true;
    return ret;
}
static int pm_runtime_force_resume(struct device *d)
{
    (void)d; event('R'); --pm_depth;
    /* Idle devices may remain runtime suspended until the next transfer. */
    return force_resume_error;
}

/* DRIVER_FUNCTIONS */

static void reset(void)
{
    memset(&dev, 0, sizeof(dev)); memset(&master, 0, sizeof(master));
    memset(&controller, 0, sizeof(controller)); memset(events, 0, sizeof(events));
    master.system_suspend_managed = master.is_la_vm = master.gsi_mode = true;
    master.dev = &dev; dev.power.usage_count = 1;
    stop_error = restart_error = force_resume_error = fault = irq_depth = pm_depth = 0;
    runtime_suspended = false;
}
static int tests;
static void passed(const char *name) { ++tests; puts(name); }
int main(void)
{
    reset();
    assert(!spi_geni_managed_suspend(&dev));
    assert(!strcmp(events, "QFidpc"));
    assert(controller.suspended && runtime_suspended && pm_depth == 1 && irq_depth == 1);
    assert(!spi_geni_resume(&dev));
    assert(!strcmp(events, "QFidpcRq") && !controller.suspended && pm_depth == 0);
    passed("pending autosuspend: drain, power down, pair resume before queue restart");

    reset(); runtime_suspended = true; irq_depth = 1;
    assert(!spi_geni_managed_suspend(&dev)); assert(!spi_geni_resume(&dev));
    assert(!strcmp(events, "QFRq") && irq_depth == 1 && pm_depth == 0);
    passed("already suspended: no duplicate power-down or IRQ disable");

    reset(); master.is_xfer_in_progress = true;
    assert(spi_geni_managed_suspend(&dev) == -EBUSY);
    assert(!strcmp(events, "Qq") && !controller.suspended && pm_depth == 0);
    passed("active transfer: refuse power-down and reopen queue");

    reset(); dev.power.usage_count = 2;
    assert(spi_geni_managed_suspend(&dev) == -EBUSY);
    assert(!strcmp(events, "Qq") && dev.power.usage_count == 2);
    passed("external client vote: refuse without dropping the client's reference");

    reset(); stop_error = -EBUSY;
    assert(spi_geni_managed_suspend(&dev) == -EBUSY);
    assert(!strcmp(events, "Qq") && !controller.suspended);
    passed("queue-stop failure: clear SPI core suspended flag");

    reset(); stop_error = -EBUSY; restart_error = -EINVAL;
    assert(spi_geni_managed_suspend(&dev) == -EBUSY);
    assert(!strcmp(events, "Qq"));
    passed("cleanup error: preserve original suspend error");

    const char *unwinds[] = {"", "QFidIq", "QFidpDIq", "QFidpcCPDIq"};
    for (int i = 1; i <= 3; ++i) {
        reset(); fault = i;
        assert(spi_geni_managed_suspend(&dev) == -EIO);
        assert(!strcmp(events, unwinds[i]));
        assert(!controller.suspended && !runtime_suspended && pm_depth == 0 && irq_depth == 0);
        passed(i == 1 ? "DMA pause failure: restore IRQ and queue" :
               i == 2 ? "resource-off failure: retain error, restore DMA/IRQ/queue" :
                        "ICC-off failure: restore ICC/resources/DMA/IRQ/queue");
    }

    reset(); assert(!spi_geni_managed_suspend(&dev)); force_resume_error = -EIO;
    assert(spi_geni_resume(&dev) == -EIO);
    assert(!strcmp(events, "QFidpcR") && controller.suspended && pm_depth == 0);
    passed("resume failure: do not reopen unpowered transfer queue");

    reset(); master.system_suspend_managed = false;
    assert(!spi_geni_resume(&dev)); assert(!events[0] && pm_depth == 0);
    passed("non-opted-in resume: preserve existing behavior");

    reset(); master.gsi_mode = false;
    assert(!spi_geni_managed_suspend(&dev)); assert(!spi_geni_resume(&dev));
    assert(!strcmp(events, "QFipcRq"));
    passed("FIFO mode: same PM order without DMA operations");
    assert(tests == 12);
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cc', default='cc')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    source = args.kernel / 'drivers/spi/spi-msm-geni.c'
    text = source.read_text()
    functions = '\n\n'.join(function(text, name) for name in (
        'spi_geni_runtime_suspend', 'spi_geni_resume', 'spi_geni_managed_suspend'))
    cfile = args.out / 'spi-pm-test.c'
    binary = args.out / 'spi-pm-test'
    cfile.write_text(HARNESS.replace('/* DRIVER_FUNCTIONS */', functions))
    subprocess.run([args.cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                    str(cfile), '-o', str(binary)], check=True)
    result = subprocess.run([str(binary.resolve())], text=True, capture_output=True, check=True)
    report = {'success': True, 'scope': 'production PM functions with mocked kernel APIs',
              'hardware_tested': False, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'tests': result.stdout.splitlines()}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
