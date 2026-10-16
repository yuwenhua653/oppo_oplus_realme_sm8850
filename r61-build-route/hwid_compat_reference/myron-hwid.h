/*
 * Copyright (C) 2021 XiaoMi, Inc.
 *               2022 The LineageOS Project
 *
 * SPDX-License-Identifier: GPL-2.0
 */

#ifndef __HWID_H__
#define __HWID_H__

#include <linux/types.h>

/* Verified stock mapping for SoC ID 660; do not reuse on other SoCs. */
#define HWID_SOC_ID_660                 660U
#define HARDWARE_PROJECT_UNKNOWN         0U
#define HARDWARE_PROJECT_660_POPSICLE    1U
#define HARDWARE_PROJECT_660_PUDDING     2U
#define HARDWARE_PROJECT_660_PANDORA     3U
#define HARDWARE_PROJECT_660_MYRON       4U
#define HARDWARE_PROJECT_660_NEZHA       5U
#define HARDWARE_PROJECT_660_PECAN       6U
#define HARDWARE_PROJECT_660_PIXIU       7U

typedef enum {
	CountryCN = 0x00,
	CountryGlobal = 0x01,
	CountryIndia = 0x02,
	CountryJapan = 0x03,
	INVALID = 0x04,
	CountryIDMax = 0x7FFFFFFF
} CountryType;

const char *product_name_get(void);
uint32_t get_hw_version_platform(void);
uint32_t get_hw_id_value(void);
uint32_t get_hw_country_version(void);
uint32_t get_hw_version_major(void);
uint32_t get_hw_version_minor(void);
uint32_t get_hw_version_build(void);
uint32_t get_hw_project_adc(void);
uint32_t get_hw_build_adc(void);

#endif /* __HWID_H__ */
