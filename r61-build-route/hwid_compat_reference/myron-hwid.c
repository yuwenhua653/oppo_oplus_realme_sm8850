/*
 * Copyright (C) 2021 XiaoMi, Inc.
 *               2022 The LineageOS Project
 *
 * SPDX-License-Identifier: GPL-2.0
 */

#include <linux/module.h>
#include <soc/qcom/socinfo.h>

#include "hwid.h"

#define HW_MAJOR_VERSION_SHIFT      16
#define HW_MINOR_VERSION_SHIFT      0
#define HW_COUNTRY_VERSION_SHIFT    20
#define HW_BUILD_VERSION_SHIFT      16
#define HW_MAJOR_VERSION_MASK       0xFFFF0000
#define HW_MINOR_VERSION_MASK       0x0000FFFF
#define HW_COUNTRY_VERSION_MASK     0xFFF00000
#define HW_BUILD_VERSION_MASK       0x000F0000

static uint project;
module_param(project, uint, 0444);
MODULE_PARM_DESC(project, "xiaomi project serial num predefine");

static uint hwid_value;
module_param(hwid_value, uint, 0444);
MODULE_PARM_DESC(hwid_value, "xiaomi hwid value correspondingly different build");

static uint build_adc;
module_param(build_adc, uint, 0444);
MODULE_PARM_DESC(build_adc, "xiaomi adc value of build resistance");

static uint project_adc;
module_param(project_adc, uint, 0444);
MODULE_PARM_DESC(project_adc, "xiaomi adc value of project resistance");

/*
 * SoC/project pairs verified from the captured Myron stock hwid module.
 * Project numbers are local to a SoC family. Never interpret project 4 on
 * another SoC as Myron, or default missing boot arguments to this device.
 */
const char *product_name_get(void)
{
	if (socinfo_get_id() != HWID_SOC_ID_660)
		return "unknown";

	switch (project) {
	case HARDWARE_PROJECT_660_POPSICLE:
		return "popsicle";
	case HARDWARE_PROJECT_660_PUDDING:
		return "pudding";
	case HARDWARE_PROJECT_660_PANDORA:
		return "pandora";
	case HARDWARE_PROJECT_660_MYRON:
		return "myron";
	case HARDWARE_PROJECT_660_NEZHA:
		return "nezha";
	case HARDWARE_PROJECT_660_PECAN:
		return "pecan";
	case HARDWARE_PROJECT_660_PIXIU:
		return "pixiu";
	default:
		return "unknown";
	}
}
EXPORT_SYMBOL(product_name_get);

uint32_t get_hw_version_platform(void)
{
	return project;
}
EXPORT_SYMBOL(get_hw_version_platform);

uint32_t get_hw_project_adc(void)
{
	return project_adc;
}
EXPORT_SYMBOL(get_hw_project_adc);

uint32_t get_hw_build_adc(void)
{
	return build_adc;
}
EXPORT_SYMBOL(get_hw_build_adc);

uint32_t get_hw_id_value(void)
{
	return hwid_value;
}
EXPORT_SYMBOL(get_hw_id_value);

uint32_t get_hw_country_version(void)
{
	return (hwid_value & HW_COUNTRY_VERSION_MASK) >> HW_COUNTRY_VERSION_SHIFT;
}
EXPORT_SYMBOL(get_hw_country_version);

uint32_t get_hw_version_major(void)
{
	return (hwid_value & HW_MAJOR_VERSION_MASK) >> HW_MAJOR_VERSION_SHIFT;
}
EXPORT_SYMBOL(get_hw_version_major);

uint32_t get_hw_version_minor(void)
{
	return (hwid_value & HW_MINOR_VERSION_MASK) >> HW_MINOR_VERSION_SHIFT;
}
EXPORT_SYMBOL(get_hw_version_minor);

uint32_t get_hw_version_build(void)
{
	return (hwid_value & HW_BUILD_VERSION_MASK) >> HW_BUILD_VERSION_SHIFT;
}
EXPORT_SYMBOL(get_hw_version_build);

MODULE_AUTHOR("weixiaotian1@xiaomi.com");
MODULE_LICENSE("GPL v2");
