#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

typedef uint8_t u8;
#define mca_log_info(...) ((void)0)
static int transport_result, write_count, observed_property;
static size_t observed_length;
static unsigned char observed_value[sizeof(int)];

static int mca_adsp_glink_write_prop(int property, const void *value, size_t len)
{
	write_count++;
	observed_property = property;
	observed_length = len;
	if (len > sizeof(observed_value))
		abort();
	memcpy(observed_value, value, len);
	return transport_result;
}

/* The test runner inserts the unmodified production enum and four functions. */
/* PRODUCTION_FUNCTIONS */

static void require(int condition, const char *message)
{
	if (!condition) {
		fprintf(stderr, "FAIL: %s (transport=%d property=%#x len=%zu)\n",
			message, transport_result, observed_property, observed_length);
		exit(1);
	}
}

int main(void)
{
	const int results[] = {0, -EIO, -ETIMEDOUT, -ENODEV, -EOPNOTSUPP, -EINVAL, 7};
	const int values[] = {0, 1500};
	struct int_case {
		int (*fn)(void *, int);
		int property;
	} cases[] = {
		{qcom_subpmic_set_charge_current, 0x2005},
		{qcom_subpmic_set_term_volt, 0x2007},
		{qcom_subpmic_set_input_current_limit, 0x2008},
	};
	int checks = 0;

	require(sizeof(int) == 4, "host integer must match four-byte wire control");
	for (size_t r = 0; r < sizeof(results) / sizeof(results[0]); r++) {
		transport_result = results[r];
		for (size_t c = 0; c < sizeof(cases) / sizeof(cases[0]); c++) {
			for (size_t v = 0; v < sizeof(values) / sizeof(values[0]); v++) {
				int value = cases[c].property == 0x2007 && values[v] ? 4400 : values[v];
				write_count = 0;
				int ret = cases[c].fn(NULL, value);
				require(ret == transport_result, "setter must return transport result exactly");
				require(write_count == 1, "exactly one transport write");
				require(observed_property == cases[c].property, "unchanged numeric property ID");
				require(observed_length == 4, "integer payload remains four bytes");
				require(memcmp(observed_value, &value, 4) == 0, "integer payload value/units unchanged");
				checks++;
			}
		}
		for (int enable = 0; enable <= 1; enable++) {
			write_count = 0;
			int ret = qcom_subpmic_enable_charging(NULL, enable);
			require(ret == transport_result, "enable must return transport result exactly");
			require(write_count == 1, "enable issues exactly one transport write");
			require(observed_property == 0x2003, "enable numeric property ID unchanged");
			require(observed_length == 1 && observed_value[0] == enable, "enable one-byte payload unchanged");
			checks++;
		}
	}
	printf("PASS setters: %d cases; IDs, fixed lengths, values, success and transport errors\n", checks);
	return 0;
}
