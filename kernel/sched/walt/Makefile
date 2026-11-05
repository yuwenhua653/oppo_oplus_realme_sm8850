# SPDX-License-Identifier: GPL-2.0

# Qualcomm SM8850 platform modules.
# Platform drivers reference private in-tree headers by source-root paths.
ccflags-y += -I$(srctree)
ccflags-y += -I$(srctree)/kernel/sched/walt
obj-$(CONFIG_SCHED_WALT) += sched-walt.o
sched-walt-y := walt.o boost.o sched_avg.o walt_halt.o core_ctl.o trace.o input-boost.o sysctl.o cpufreq_walt.o fixup.o walt_lb.o walt_rt.o walt_cfs.o walt_tp.o walt_config.o voter.o walt_cpufreq_cycle_cntr_driver.o walt_gclk_cycle_counter_driver.o walt_cycles.o debugfs.o pipeline.o smart_freq.o walt_storage_lb.o mvp_locking.o
ifneq ($(filter y m,$(CONFIG_SCHED_WALT_STATS)),)
sched-walt-y += sysctl_walt_stats.o
endif
