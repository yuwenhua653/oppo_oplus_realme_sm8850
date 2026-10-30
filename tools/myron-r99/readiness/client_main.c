#include "android_io.h"
#include "watchdog.h"
#include <stdio.h>
#include <sys/prctl.h>
int main(int argc, char **argv) {
    int channel = argc == 2 ? r99_channel(argv[1]) : -1;
    if (channel < 0 || prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) ||
        r99_watchdog_start(R99_CLIENT_WATCHDOG_MS)) return R99_FAILED;
    struct r99_result out;
    int result = r99_query((unsigned)channel, &r99_android_ops, &out);
    if (result != R99_FAILED) {
        /* Fixed tokens only. Callers must also check the exit code. */
        printf("%s %s\n", out.ueventd_running ? "running" : "not_running", out.coldboot_done ? "true" : "not_true");
    }
    return result;
}
