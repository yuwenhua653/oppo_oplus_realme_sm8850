#define _GNU_SOURCE
#include "android_io.h"
#include "watchdog.h"
#include <linux/capability.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/system_properties.h>
#include <time.h>
#include <unistd.h>
int main(int argc, char **argv) {
    (void)argv;
    /* Fixed nobody identity, no supplementary access or Linux capabilities.
     * Do not silently start privileged if init integration is wrong. */
    gid_t groups[2];
    int count = getgroups(2, groups);
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct caps[2] = {{0}};
    if (argc != 1 || getuid() != 9999 || geteuid() != 9999 || getgid() != 9999 || getegid() != 9999 ||
        count < 0 || count > 1 || (count == 1 && groups[0] != 9999) ||
        syscall(SYS_capget, &header, caps) || caps[0].effective || caps[1].effective ||
        caps[0].permitted || caps[1].permitted || caps[0].inheritable || caps[1].inheritable ||
        prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) || r99_watchdog_start(R99_BROKER_WATCHDOG_MS)) return 2;
    struct r99_broker state = {{{0}}};
    for (;;) {
        /* Snapshot before scanning so a request racing the scan cannot become
         * a lost wakeup. Bionic wakes for property changes; the finite idle
         * wait lets the process-local watchdog retain a strict bound. */
        uint32_t serial = __system_property_area_serial(), next_serial;
        (void)r99_broker_step(&state, &r99_android_ops);
        if (r99_watchdog_refresh(R99_BROKER_WATCHDOG_MS)) return 2;
        const struct timespec timeout = {1, 0};
        (void)__system_property_wait(NULL, serial, &next_serial, &timeout);
    }
}
