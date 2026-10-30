#define _POSIX_C_SOURCE 200809L
#include "watchdog.h"
#include <signal.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
static timer_t timer;
static int started;
static void expired(int sig) { (void)sig; _exit(124); }
int r99_watchdog_refresh(unsigned ms) {
    if (!started || !ms || ms > 5000) return -1;
    struct itimerspec it = {{0,0}, {(time_t)(ms / 1000), (long)(ms % 1000) * 1000000}};
    return timer_settime(timer, 0, &it, NULL);
}
int r99_watchdog_start(unsigned ms) {
    if (started) return -1;
    struct sigaction sa; memset(&sa, 0, sizeof(sa));
    sa.sa_handler = expired; sigemptyset(&sa.sa_mask);
    if (sigaction(SIGALRM, &sa, NULL)) return -1;
    sigset_t alarms; sigemptyset(&alarms); sigaddset(&alarms, SIGALRM);
    if (sigprocmask(SIG_UNBLOCK, &alarms, NULL)) return -1;
    struct sigevent ev; memset(&ev, 0, sizeof(ev)); ev.sigev_notify = SIGEV_SIGNAL; ev.sigev_signo = SIGALRM;
    if (timer_create(CLOCK_MONOTONIC, &ev, &timer)) return -1;
    started = 1;
    return r99_watchdog_refresh(ms);
}
