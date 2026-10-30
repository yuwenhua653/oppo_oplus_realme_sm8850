#define _POSIX_C_SOURCE 200809L
#include "android_io.h"
#include <errno.h>
#include <sys/random.h>
#include <sys/system_properties.h>
#include <time.h>
_Static_assert(PROP_VALUE_MAX == R99_VALUE_MAX, "property ABI bound changed");
static int prop_get(void *ctx, const char *name, char out[R99_VALUE_MAX]) { (void)ctx; return __system_property_get(name, out); }
static int prop_set(void *ctx, const char *name, const char *value) { (void)ctx; return __system_property_set(name, value); }
static int entropy(void *ctx, unsigned char out[R99_NONCE_BYTES]) {
    (void)ctx;
    unsigned used = 0;
    for (unsigned tries = 0; used < R99_NONCE_BYTES && tries < 32; tries++) {
        ssize_t n = getrandom(out + used, R99_NONCE_BYTES - used, GRND_NONBLOCK);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0 || n > (ssize_t)(R99_NONCE_BYTES - used)) return -1;
        used += (unsigned)n;
    }
    return used == R99_NONCE_BYTES ? 0 : -1;
}
static int64_t monotonic_ms(void *ctx) {
    (void)ctx; struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t) || t.tv_sec < 0 || t.tv_sec > INT64_MAX / 1000) return -1;
    return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static int sleep_ms(void *ctx, unsigned ms) {
    (void)ctx; struct timespec t = {(time_t)(ms/1000), (long)(ms%1000)*1000000};
    return nanosleep(&t, NULL); /* Interrupted wait fails closed; no unbounded retry. */
}
const struct r99_ops r99_android_ops = {NULL, prop_get, prop_set, entropy, monotonic_ms, sleep_ms};
