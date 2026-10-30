/* Fixed readiness protocol. No filesystem access, arbitrary property names,
 * commands, policy changes, cached readiness bits, or hardware operations. */
#include "readiness.h"
#include <string.h>

static const char *const channels[R99_CHANNELS] = {"tfa", "adsp", "cdsp"};
static const char *const requests[R99_CHANNELS] = {
    "vendor.r99.readiness.request.tfa", "vendor.r99.readiness.request.adsp",
    "vendor.r99.readiness.request.cdsp"};
static const char *const replies[R99_CHANNELS] = {
    "sys.r99.readiness.reply.tfa", "sys.r99.readiness.reply.adsp",
    "sys.r99.readiness.reply.cdsp"};

int r99_channel(const char *name) {
    if (!name) return -1;
    for (unsigned i = 0; i < R99_CHANNELS; i++) if (!strcmp(name, channels[i])) return (int)i;
    return -1;
}
const char *r99_request_name(unsigned c) { return c < R99_CHANNELS ? requests[c] : NULL; }
const char *r99_reply_name(unsigned c) { return c < R99_CHANNELS ? replies[c] : NULL; }
int r99_nonce_valid(const char *p) {
    if (!p || strnlen(p, R99_VALUE_MAX) != R99_NONCE_CHARS) return 0;
    for (unsigned i = 0; i < R99_NONCE_CHARS; i++)
        if (!((p[i] >= '0' && p[i] <= '9') || (p[i] >= 'a' && p[i] <= 'f'))) return 0;
    return 1;
}
static int get(const struct r99_ops *ops, const char *name, char out[R99_VALUE_MAX]) {
    memset(out, 0, R99_VALUE_MAX);
    int n = ops->get(ops->ctx, name, out);
    if (n < 0 || n >= R99_VALUE_MAX || (size_t)n != strnlen(out, R99_VALUE_MAX)) return -1;
    return n;
}
int r99_broker_step(struct r99_broker *state, const struct r99_ops *ops) {
    int count = 0;
    for (unsigned i = 0; i < R99_CHANNELS; i++) {
        char request[R99_VALUE_MAX], check[R99_VALUE_MAX];
        char ueventd[R99_VALUE_MAX], coldboot[R99_VALUE_MAX], reply[R99_REPLY_CHARS + 1];
        if (get(ops, requests[i], request) != R99_NONCE_CHARS || !r99_nonce_valid(request) ||
            !strcmp(request, state->last[i])) continue;
        /* Missing, failed, or unfamiliar values never establish readiness.
         * TFA needs only running; DSP needs running and exact coldboot=true. */
        int u = get(ops, "init.svc.ueventd", ueventd) == 7 && !strcmp(ueventd, "running");
        int c = get(ops, "ro.cold_boot_done", coldboot) == 4 && !strcmp(coldboot, "true");
        /* If the owner replaced its request while we sampled, publish nothing. */
        if (get(ops, requests[i], check) != R99_NONCE_CHARS || strcmp(check, request)) continue;
        memcpy(reply, request, R99_NONCE_CHARS);
        reply[32] = ':'; reply[33] = u ? '1' : '0'; reply[34] = ':'; reply[35] = c ? '1' : '0'; reply[36] = 0;
        if (ops->set(ops->ctx, replies[i], reply)) continue;
        memcpy(state->last[i], request, R99_NONCE_CHARS + 1);
        count++;
    }
    return count;
}
static int reply_result(const char *reply, const char *nonce, struct r99_result *out) {
    if (strnlen(reply, R99_VALUE_MAX) != R99_REPLY_CHARS || memcmp(reply, nonce, 32)) return 0;
    if (reply[32] != ':' || reply[34] != ':' ||
        (reply[33] != '0' && reply[33] != '1') || (reply[35] != '0' && reply[35] != '1')) return -1;
    out->ueventd_running = reply[33] == '1'; out->coldboot_done = reply[35] == '1';
    return 1;
}
int r99_query(unsigned channel, const struct r99_ops *ops, struct r99_result *out) {
    if (out) memset(out, 0, sizeof(*out));
    if (channel >= R99_CHANNELS || !out) return R99_FAILED;
    int64_t start = ops->now_ms(ops->ctx);
    if (start < 0 || start > INT64_MAX - R99_RESPONSE_BUDGET_MS) return R99_FAILED;
    int64_t deadline = start + R99_RESPONSE_BUDGET_MS;
    unsigned char bytes[R99_NONCE_BYTES]; char nonce[33], prior[R99_VALUE_MAX], reply[R99_VALUE_MAX];
    static const char hex[] = "0123456789abcdef";
    if (ops->random(ops->ctx, bytes)) return R99_FAILED;
    for (unsigned i = 0; i < R99_NONCE_BYTES; i++) { nonce[i*2] = hex[bytes[i] >> 4]; nonce[i*2+1] = hex[bytes[i] & 15]; }
    nonce[32] = 0;
    /* Detect immediate nonce reuse even if the entropy provider is broken.
     * Genuine kernel random nonces make historical reuse negligible. */
    int n = get(ops, requests[channel], prior);
    if (n < 0 || (n >= 32 && !memcmp(prior, nonce, 32))) return R99_FAILED;
    n = get(ops, replies[channel], prior);
    if (n < 0 || (n >= 32 && !memcmp(prior, nonce, 32))) return R99_FAILED;
    if (ops->set(ops->ctx, requests[channel], nonce)) return R99_FAILED;
    for (unsigned tries = 0; tries < 81; tries++) {
        int64_t now = ops->now_ms(ops->ctx);
        if (now < start || now >= deadline) return R99_FAILED;
        n = get(ops, replies[channel], reply);
        if (n < 0) return R99_FAILED;
        struct r99_result sample = {0};
        int match = reply_result(reply, nonce, &sample);
        if (match < 0) return R99_FAILED;
        if (match == 1) {
            /* One writer per fixed channel is required. Concurrent reuse of a
             * channel cannot accept a reply after its request was replaced. */
            if (get(ops, requests[channel], prior) != 32 || strcmp(prior, nonce)) return R99_FAILED;
            now = ops->now_ms(ops->ctx);
            if (now < start || now >= deadline) return R99_FAILED;
            *out = sample;
            return sample.ueventd_running && (!channel || sample.coldboot_done) ? R99_READY : R99_NOT_READY;
        }
        if (ops->sleep_ms(ops->ctx, 5)) return R99_FAILED;
    }
    return R99_FAILED;
}
