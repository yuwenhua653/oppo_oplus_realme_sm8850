#ifndef R99_READINESS_H
#define R99_READINESS_H
#include <stddef.h>
#include <stdint.h>
#define R99_CHANNELS 3
#define R99_VALUE_MAX 92
#define R99_NONCE_BYTES 16
#define R99_NONCE_CHARS 32
#define R99_REPLY_CHARS 36
#define R99_RESPONSE_BUDGET_MS 400
#define R99_CLIENT_WATCHDOG_MS 750
#define R99_BROKER_WATCHDOG_MS 2000
struct r99_ops {
    void *ctx;
    int (*get)(void *, const char *, char [R99_VALUE_MAX]);
    int (*set)(void *, const char *, const char *);
    int (*random)(void *, unsigned char [R99_NONCE_BYTES]);
    int64_t (*now_ms)(void *);
    int (*sleep_ms)(void *, unsigned);
};
struct r99_broker { char last[R99_CHANNELS][R99_NONCE_CHARS + 1]; };
struct r99_result { int ueventd_running; int coldboot_done; };
enum r99_status { R99_READY = 0, R99_NOT_READY = 1, R99_FAILED = 2 };
int r99_channel(const char *name);
const char *r99_request_name(unsigned channel);
const char *r99_reply_name(unsigned channel);
int r99_nonce_valid(const char *value);
int r99_broker_step(struct r99_broker *, const struct r99_ops *);
int r99_query(unsigned channel, const struct r99_ops *, struct r99_result *);
#endif
