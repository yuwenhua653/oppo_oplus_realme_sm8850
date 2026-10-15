// SPDX-License-Identifier: GPL-2.0-only
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../fts_myron_frame.h"

static const struct fts_myron_geometry geometry = { 0, 0, 119999, 260799, 100 };
static unsigned int checks;

#define CHECK(x) do { checks++; if (!(x)) { \
	fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)

static void point(u8 *b, unsigned int n, unsigned int id, unsigned int flag,
		  unsigned int x, unsigned int y)
{
	u8 *p = b + 4 + n * 8;

	p[0] = (flag << 6) | ((x >> 12) & 15);
	p[1] = x >> 4;
	p[2] = (id << 4) | ((y >> 12) & 15);
	p[3] = y >> 4;
	p[4] = ((x & 15) << 4) | (y & 15);
	p[5] = 23;
	p[6] = 11;
	p[7] = 0;
}

static int reject_unchanged(const u8 *buf, size_t len)
{
	struct fts_myron_frame out, before;
	int ret;

	memset(&out, 0xa5, sizeof(out));
	memcpy(&before, &out, sizeof(out));
	ret = fts_myron_decode(buf, len, &geometry, &out);
	return ret < 0 && !memcmp(&out, &before, sizeof(out));
}

int main(void)
{
	u8 b[FTS_MYRON_REPORT_LEN];
	struct fts_myron_frame out;
	unsigned int i, count;
	u32 rng = 0x3683;

	CHECK(fts_myron_crc((const u8 *)"123456789", 9) == 0x6f91);
	CHECK(fts_myron_crc((const u8 *)"", 0) == 0xffff);
	memset(b, 0xff, sizeof(b));
	b[0] = 0;
	b[1] = 0x21;
	point(b, 0, 7, 0, 17, 33);
	CHECK(!fts_myron_decode(b, sizeof(b), &geometry, &out));
	CHECK(out.count == 1 && out.active == (1U << 7));
	CHECK(out.contacts[0].x == 106 && out.contacts[0].y == 206);
	CHECK(out.contacts[0].major == 23 && out.contacts[0].minor == 11);
	/* Tail is explicitly ignored, including valid-looking ghost records. */
	memset(b + 12, 0, sizeof(b) - 12);
	CHECK(!fts_myron_decode(b, sizeof(b), &geometry, &out));
	CHECK(out.count == 1 && out.active == (1U << 7));
	CHECK(!fts_myron_decode(b, 12, &geometry, &out));
	CHECK(reject_unchanged(b, 11));
	for (count = 1; count <= 10; count++) {
		b[1] = 0x20 | count;
		for (i = 0; i < count; i++)
			point(b, i, i, i % 3, i * 1024, i * 2048);
		CHECK(!fts_myron_decode(b, sizeof(b), &geometry, &out));
		CHECK(out.count == count);
		for (i = 0; i < count; i++)
			CHECK(!!(out.active & (1U << i)) == (i % 3 != 1));
	}
	/* UP events consume a slot record but must never become a press. */
	b[1] = 0x21;
	point(b, 0, 9, 1, 65535, 65535);
	CHECK(!fts_myron_decode(b, sizeof(b), &geometry, &out));
	CHECK(out.count == 1 && out.active == 0);
	point(b, 0, 0, 2, 19199, 41727);
	CHECK(!fts_myron_decode(b, sizeof(b), &geometry, &out));
	CHECK(out.contacts[0].x == 119993 && out.contacts[0].y == 260793);
	point(b, 0, 0, 2, 19200, 41727);
	CHECK(reject_unchanged(b, sizeof(b)));
	point(b, 0, 0, 2, 19199, 41728);
	CHECK(reject_unchanged(b, sizeof(b)));
	point(b, 0, 0, 0, 0, 0);
	CHECK(!fts_myron_decode(b, sizeof(b), &geometry, &out));
	point(b, 0, 10, 0, 0, 0);
	CHECK(reject_unchanged(b, sizeof(b)));
	point(b, 0, 0, 3, 0, 0);
	CHECK(reject_unchanged(b, sizeof(b)));
	b[1] = 0x22;
	point(b, 0, 4, 0, 0, 0);
	point(b, 1, 4, 1, 0, 0);
	CHECK(reject_unchanged(b, sizeof(b)));
	point(b, 1, 9, 3, 0, 0);
	CHECK(reject_unchanged(b, sizeof(b))); /* invalid final record, atomic reject */
	b[1] = 0x20;
	CHECK(reject_unchanged(b, sizeof(b)));
	b[1] = 0x2b;
	CHECK(reject_unchanged(b, sizeof(b)));
	b[1] = 0x01;
	CHECK(reject_unchanged(b, sizeof(b)));
	memset(b, 0xff, sizeof(b));
	CHECK(reject_unchanged(b, sizeof(b)));
	CHECK(reject_unchanged(b, 0));
	/* Deterministic malformed-input exploration; ASan/UBSan observe bounds. */
	for (i = 0; i < 20000; i++) {
		struct fts_myron_frame before;
		size_t len, j;
		int ret;

		rng = rng * 1664525U + 1013904223U;
		len = rng % 90;
		for (j = 0; j < len; j++) {
			rng = rng * 1664525U + 1013904223U;
			b[j] = rng >> 24;
		}
		memset(&out, 0xa5, sizeof(out));
		memcpy(&before, &out, sizeof(out));
		ret = fts_myron_decode(b, len, &geometry, &out);
		if (ret) {
			CHECK(!memcmp(&out, &before, sizeof(out)));
		} else {
			CHECK(out.count >= 1 && out.count <= 10);
			CHECK(!(out.active & ~0x3ffU));
		}
	}
	printf("PASS %u checks: v2 events, strict bounds, atomic rejection, CRC, 20000 malformed frames\n", checks);
	return 0;
}
