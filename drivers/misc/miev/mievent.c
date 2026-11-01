// SPDX-License-Identifier: GPL-2.0
/* Xiaomi MiSight event transport; derived from the pinned Onyx implementation.
 * Myron integration: bounded per-event formatting, no global sizing state.
 * Event objects are owned by the caller and must not be mutated concurrently.
 */
#define pr_fmt(fmt) "miev: " fmt

#include <miev/mievent.h>
#include <linux/errno.h>
#include <linux/ktime.h>
#include <linux/slab.h>
#include <linux/string.h>

#define EVENT_MAX_SIZE 4096

struct misight_mievent *cdev_tevent_alloc(unsigned int eventid)
{
	struct misight_mievent *event = kzalloc(sizeof(*event), GFP_KERNEL);

	if (!event)
		return NULL;
	event->head = kzalloc(sizeof(*event->head), GFP_KERNEL);
	if (!event->head) {
		kfree(event);
		return NULL;
	}
	event->eventid = eventid;
	event->time = ktime_get_real_seconds();
	return event;
}
EXPORT_SYMBOL_GPL(cdev_tevent_alloc);

static int add_payload(struct misight_mievent *event, const char *key,
		       const char *value, int type)
{
	struct mievent_payload *payload;
	size_t key_len, value_len;

	if (!event || !event->head || !key || !value)
		return -EINVAL;
	key_len = strnlen(key, EVENT_MAX_SIZE + 1);
	value_len = strnlen(value, EVENT_MAX_SIZE + 1);
	if (key_len > EVENT_MAX_SIZE || value_len > EVENT_MAX_SIZE)
		return -E2BIG;
	payload = kmalloc(sizeof(*payload) + key_len + value_len + 2, GFP_KERNEL);
	if (!payload)
		return -ENOMEM;
	payload->key = (char *)(payload + 1);
	payload->value = payload->key + key_len + 1;
	memcpy(payload->key, key, key_len + 1);
	memcpy(payload->value, value, value_len + 1);
	payload->type = type;
	payload->next = event->head->next;
	event->head->next = payload;
	return 0;
}

int cdev_tevent_add_int(struct misight_mievent *event, const char *key, long value)
{
	char text[32];

	scnprintf(text, sizeof(text), "%ld", value);
	return add_payload(event, key, text, INT_T);
}
EXPORT_SYMBOL_GPL(cdev_tevent_add_int);

int cdev_tevent_add_str(struct misight_mievent *event, const char *key,
			const char *value)
{
	return add_payload(event, key, value, STR_T);
}
EXPORT_SYMBOL_GPL(cdev_tevent_add_str);

static int append_char(char *buffer, size_t *used, char value)
{
	if (*used >= EVENT_MAX_SIZE)
		return -E2BIG;
	buffer[(*used)++] = value;
	buffer[*used] = '\0';
	return 0;
}

static int append_text(char *buffer, size_t *used, const char *text, bool quoted)
{
	static const char hex[] = "0123456789abcdef";
	const unsigned char *p = (const unsigned char *)text;
	int i;

	if (quoted && append_char(buffer, used, '"'))
		return -E2BIG;
	for (; *p; p++) {
		if (quoted && (*p == '"' || *p == '\\')) {
			if (append_char(buffer, used, '\\'))
				return -E2BIG;
		} else if (quoted && *p < 0x20) {
			const char escape[] = {'\\', 'u', '0', '0',
				hex[*p >> 4], hex[*p & 15], '\0'};

			for (i = 0; i < 6; i++)
				if (append_char(buffer, used, escape[i]))
					return -E2BIG;
			continue;
		}
		if (append_char(buffer, used, *p))
			return -E2BIG;
	}
	return quoted ? append_char(buffer, used, '"') : 0;
}

static void free_payloads(struct mievent_payload *head)
{
	struct mievent_payload *p = head->next;

	while (p) {
		struct mievent_payload *next = p->next;

		kfree(p);
		p = next;
	}
	head->next = NULL;
}

int cdev_tevent_write(struct misight_mievent *event)
{
	struct mievent_payload *p;
	char *buffer;
	size_t used;
	int ret;

	if (!event || !event->head)
		return -EINVAL;
	buffer = kmalloc(EVENT_MAX_SIZE + 1, GFP_KERNEL);
	if (!buffer)
		return -ENOMEM;
	used = scnprintf(buffer, EVENT_MAX_SIZE + 1,
			 "EventId %u -t %lld -paraList {", event->eventid, event->time);
	ret = 0;
	for (p = event->head->next; p; p = p->next) {
		if (p != event->head->next && append_char(buffer, &used, ',')) {
			ret = -E2BIG;
			goto out;
		}
		ret = append_text(buffer, &used, p->key, true);
		if (!ret)
			ret = append_char(buffer, &used, ':');
		if (!ret)
			ret = append_text(buffer, &used, p->value, p->type == STR_T);
		if (ret)
			goto out;
	}
	ret = append_char(buffer, &used, '}');
	if (ret)
		goto out;
	ret = write_kbuf(buffer, used);
	if (ret == (int)used) {
		free_payloads(event->head);
		ret = 0;
	} else if (ret >= 0) {
		ret = -EIO;
	}
out:
	kfree(buffer);
	return ret;
}
EXPORT_SYMBOL_GPL(cdev_tevent_write);

void cdev_tevent_destroy(struct misight_mievent *event)
{
	if (!event)
		return;
	if (event->head) {
		free_payloads(event->head);
		kfree(event->head);
	}
	kfree(event);
}
EXPORT_SYMBOL_GPL(cdev_tevent_destroy);
