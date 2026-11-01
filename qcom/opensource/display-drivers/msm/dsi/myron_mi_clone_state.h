/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef MYRON_MI_CLONE_STATE_H
#define MYRON_MI_CLONE_STATE_H

struct dsi_display;
int myron_mi_clone_attach(struct dsi_display *display);
void myron_mi_clone_detach(struct dsi_display *display);

/* MiCode popsicle-w-oss 6def61b29a39710078287416afd3b62f43729c37:
 * mi_disp_parser.c default and include/uapi/display/drm/mi_disp.h ABI.
 * Logical clone values are NOT physical panel DBV values.
 */
#define MYRON_CLONE_DEFAULT 16383U
#define MYRON_CLONE_EVENT 5U
#define MYRON_CLONE_QUEUE 256U
struct myron_clone_event {
	int disp_id;
	unsigned int type;
	unsigned int length;
	unsigned int value;
};
struct myron_clone_queue {
	struct myron_clone_event events[MYRON_CLONE_QUEUE];
	unsigned int head;
	unsigned int count;
};
static inline unsigned int myron_clone_bound(unsigned int value,
		unsigned int maximum)
{
	return value > maximum ? maximum : value;
}
static inline int myron_clone_max_valid(unsigned int maximum)
{
	return maximum && maximum <= 0x7fffffffU;
}
static inline int myron_clone_push(struct myron_clone_queue *q,
		unsigned int value)
{
	struct myron_clone_event *event;

	if (q->count == MYRON_CLONE_QUEUE)
		return 0;
	event = &q->events[(q->head + q->count) % MYRON_CLONE_QUEUE];
	event->disp_id = 0;
	event->type = MYRON_CLONE_EVENT;
	event->length = sizeof(*event);
	event->value = value;
	q->count++;
	return 1;
}
#endif
