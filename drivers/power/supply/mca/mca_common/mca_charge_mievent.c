// SPDX-License-Identifier: GPL-2.0
/*
 * mca_charge_mievent->c
 *
 * mca charger mievent driver
 *
 * Copyright (c) 2024-2024 Xiaomi Technologies Co., Ltd.
 *
 * This software is licensed under the terms of the GNU General Public
 * License version 2, as published by the Free Software Foundation, and
 * may be copied, distributed, and modified under those terms.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 */

#include <mca/common/mca_charge_mievent.h>
#include <mca/common/mca_log.h>
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/string.h>
#include <mca/common/mca_event.h>

#include <miev/mievent.h>
#include <linux/mutex.h>
#include <linux/ktime.h>

#ifndef MCA_LOG_TAG
#define MCA_LOG_TAG "mca_charge_mievent"
#endif

/* Positional event ABI decoded from Myron stock; all 61 records retained. */
static const struct charge_mievent_info g_charge_mievent_info[] = {
 { /* ID 0 */
  .event_code = 909001004,
  .event_type = "chgErrInfo",
  .event_describe = "PdAuthFail",
  .upload_type = 0,
  .type_index = 0,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "adapterId" },
 },
 { /* ID 1 */
  .event_code = 909001005,
  .event_type = "chgErrInfo",
  .event_describe = "CpEnFail",
  .upload_type = 0,
  .type_index = 1,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "cpId" },
 },
 { /* ID 2 */
  .event_code = 909002001,
  .event_type = "chgErrInfo",
  .event_describe = "NoneStandartChg",
  .upload_type = 0,
  .type_index = 2,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 3 */
  .event_code = 909002002,
  .event_type = "chgErrInfo",
  .event_describe = "CorrosionDischarge",
  .upload_type = 0,
  .type_index = 3,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 4 */
  .event_code = 909002003,
  .event_type = "chgErrInfo",
  .event_describe = "LpdDetected",
  .upload_type = 0,
  .type_index = 4,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "lpdFlag" },
 },
 { /* ID 5 */
  .event_code = 909002004,
  .event_type = "chgErrInfo",
  .event_describe = "CpVbusOvp",
  .upload_type = 0,
  .type_index = 5,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 6 */
  .event_code = 909002005,
  .event_type = "chgErrInfo",
  .event_describe = "CpIbusOcp",
  .upload_type = 0,
  .type_index = 6,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 7 */
  .event_code = 909002006,
  .event_type = "chgErrInfo",
  .event_describe = "CpVbatOvp",
  .upload_type = 0,
  .type_index = 7,
  .data_type = 0,
  .data_count = 2,
  .para_name = { "vbat", "vbatMax" },
 },
 { /* ID 8 */
  .event_code = 909002007,
  .event_type = "chgErrInfo",
  .event_describe = "CpIbatOcp",
  .upload_type = 0,
  .type_index = 8,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 9 */
  .event_code = 909002008,
  .event_type = "chgErrInfo",
  .event_describe = "CpVacOvp",
  .upload_type = 0,
  .type_index = 9,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 10 */
  .event_code = 909002012,
  .event_type = "chgStatInfo",
  .event_describe = "AntiBurnTirg",
  .upload_type = 0,
  .type_index = 10,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "tconn" },
 },
 { /* ID 11 */
  .event_code = 909002013,
  .event_type = "chgErrInfo",
  .event_describe = "ChgBroken",
  .upload_type = 0,
  .type_index = 11,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 12 */
  .event_code = 909003002,
  .event_type = "chgErrInfo",
  .event_describe = "SocNotFull",
  .upload_type = 0,
  .type_index = 12,
  .data_type = 0,
  .data_count = 3,
  .para_name = { "vbat", "soc", "rsoc" },
 },
 { /* ID 13 */
  .event_code = 909003004,
  .event_type = "chgStatInfo",
  .event_describe = "SmartEnduraTrig",
  .upload_type = 0,
  .type_index = 13,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "soc" },
 },
 { /* ID 14 */
  .event_code = 909003006,
  .event_type = "chgStatInfo",
  .event_describe = "SmartNaviTrig",
  .upload_type = 0,
  .type_index = 14,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "soc" },
 },
 { /* ID 15 */
  .event_code = 909003007,
  .event_type = "chgStatInfo",
  .event_describe = "IspLevelOne",
  .upload_type = 0,
  .type_index = 15,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "ispLevel" },
 },
 { /* ID 16 */
  .event_code = 909003008,
  .event_type = "chgStatInfo",
  .event_describe = "IspLevelTwo",
  .upload_type = 0,
  .type_index = 16,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "ispLevel" },
 },
 { /* ID 17 */
  .event_code = 909003009,
  .event_type = "chgErrInfo",
  .event_describe = "IspLevelThree",
  .upload_type = 0,
  .type_index = 17,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "ispLevel" },
 },
 { /* ID 18 */
  .event_code = 909003010,
  .event_type = "chgErrInfo",
  .event_describe = "csdFlag",
  .upload_type = 0,
  .type_index = 18,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "csdFlag" },
 },
 { /* ID 19 */
  .event_code = 909003011,
  .event_type = "chgStatInfo",
  .event_describe = "VbatOvSecureCurr",
  .upload_type = 0,
  .type_index = 19,
  .data_type = 2,
  .data_count = 1,
  .para_name = { "cycleCount" },
 },
 { /* ID 20 */
  .event_code = 909004001,
  .event_type = "chgErrInfo",
  .event_describe = "socJump",
  .upload_type = 0,
  .type_index = 20,
  .data_type = 0,
  .data_count = 10,
  .para_name = { "preUIsoc", "preRsoc", "uisoc", "rsoc", "temp", "vbat", "online", "current", "fcc", "qmax" },
 },
 { /* ID 21 */
  .event_code = 909004002,
  .event_type = "chgStatInfo",
  .event_describe = "vbatMeanShutdown",
  .upload_type = 0,
  .type_index = 21,
  .data_type = 0,
  .data_count = 3,
  .para_name = { "vbat_mean", "current", "temp" },
 },
 { /* ID 22 */
  .event_code = 909005003,
  .event_type = "chgErrInfo",
  .event_describe = "BattLinkerAbsent",
  .upload_type = 0,
  .type_index = 22,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 23 */
  .event_code = 909005004,
  .event_type = "chgStatInfo",
  .event_describe = "CpTdieHot",
  .upload_type = 0,
  .type_index = 23,
  .data_type = 0,
  .data_count = 2,
  .para_name = { "masterTdie", "slaveTdie" },
 },
 { /* ID 24 */
  .event_code = 909005005,
  .event_type = "chgErrInfo",
  .event_describe = "VbusUvlo",
  .upload_type = 0,
  .type_index = 24,
  .data_type = 0,
  .data_count = 3,
  .para_name = { "vbat", "vbus", "aicl" },
 },
 { /* ID 25 */
  .event_code = 909005007,
  .event_type = "chgErrInfo",
  .event_describe = "NotChgInLowTemp",
  .upload_type = 0,
  .type_index = 25,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "tbat" },
 },
 { /* ID 26 */
  .event_code = 909005008,
  .event_type = "chgErrInfo",
  .event_describe = "NotChgInHighTemp",
  .upload_type = 0,
  .type_index = 26,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "tbat" },
 },
 { /* ID 27 */
  .event_code = 909005009,
  .event_type = "chgErrInfo",
  .event_describe = "DualBattLinkerAbsent",
  .upload_type = 0,
  .type_index = 27,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "status" },
 },
 { /* ID 28 */
  .event_code = 909006010,
  .event_type = "chgErrInfo",
  .event_describe = "SmartEnduraSocErr",
  .upload_type = 0,
  .type_index = 28,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "soc" },
 },
 { /* ID 29 */
  .event_code = 909006011,
  .event_type = "chgErrInfo",
  .event_describe = "SmartNaviSocErr",
  .upload_type = 0,
  .type_index = 29,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "soc" },
 },
 { /* ID 30 */
  .event_code = 909007001,
  .event_type = "chgErrInfo",
  .event_describe = "BattAuthFail",
  .upload_type = 0,
  .type_index = 30,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 31 */
  .event_code = 909007002,
  .event_type = "chgErrInfo",
  .event_describe = "ChgBattAuthFail",
  .upload_type = 0,
  .type_index = 31,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "status" },
 },
 { /* ID 32 */
  .event_code = 909009003,
  .event_type = "chgErrInfo",
  .event_describe = "AntiFail",
  .upload_type = 0,
  .type_index = 32,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 33 */
  .event_code = 909010001,
  .event_type = "chgStatInfo",
  .event_describe = "SoftCidTrigger",
  .upload_type = 0,
  .type_index = 33,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 34 */
  .event_code = 909011001,
  .event_type = "chgErrInfo",
  .event_describe = "WlsFastChgFail",
  .upload_type = 0,
  .type_index = 34,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 35 */
  .event_code = 909011002,
  .event_type = "chgErrInfo",
  .event_describe = "WlsQLow",
  .upload_type = 0,
  .type_index = 35,
  .data_type = 0,
  .data_count = 2,
  .para_name = { "chgQbase", "chgQreal" },
 },
 { /* ID 36 */
  .event_code = 909012001,
  .event_type = "chgErrInfo",
  .event_describe = "WlsRxOTP",
  .upload_type = 0,
  .type_index = 36,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "chgRxtemp" },
 },
 { /* ID 37 */
  .event_code = 909012002,
  .event_type = "chgErrInfo",
  .event_describe = "WlsRxOVP",
  .upload_type = 0,
  .type_index = 37,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 38 */
  .event_code = 909012003,
  .event_type = "chgErrInfo",
  .event_describe = "WlsRxOCP",
  .upload_type = 0,
  .type_index = 38,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 39 */
  .event_code = 909012004,
  .event_type = "chgErrInfo",
  .event_describe = "WlsTrxFod",
  .upload_type = 0,
  .type_index = 39,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 40 */
  .event_code = 909012005,
  .event_type = "chgErrInfo",
  .event_describe = "WlsTrxOCP",
  .upload_type = 0,
  .type_index = 40,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 41 */
  .event_code = 909012006,
  .event_type = "chgErrInfo",
  .event_describe = "WlsTrxUVLO",
  .upload_type = 0,
  .type_index = 41,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 42 */
  .event_code = 909013001,
  .event_type = "chgErrInfo",
  .event_describe = "WlsTrxI2cErr",
  .upload_type = 0,
  .type_index = 42,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 43 */
  .event_code = 909013004,
  .event_type = "chgErrInfo",
  .event_describe = "WlsRxI2cErr",
  .upload_type = 0,
  .type_index = 43,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 44 */
  .event_code = 909007003,
  .event_type = "chgErrInfo",
  .event_describe = "LoadSwitchI2cErr",
  .upload_type = 0,
  .type_index = 44,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
 { /* ID 45 */
  .event_code = 909013002,
  .event_type = "chgErrInfo",
  .event_describe = "WlsFwUpgradeErr",
  .upload_type = 0,
  .type_index = 45,
  .data_type = 1,
  .data_count = 1,
  .para_name = { "errReason" },
 },
 { /* ID 46 */
  .event_code = 909001006,
  .event_type = "chgStatInfo",
  .event_describe = "ChargeSlowly",
  .upload_type = 0,
  .type_index = 46,
  .data_type = 0,
  .data_count = 5,
  .para_name = { "maxPower", "initialRm", "endRm", "initialSoc", "endSoc" },
 },
 { /* ID 47 */
  .event_code = 909001007,
  .event_type = "chgStatInfo",
  .event_describe = "NonStandardCharger",
  .upload_type = 0,
  .type_index = 47,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "chgType" },
 },
 { /* ID 48 */
  .event_code = 909014003,
  .event_type = "chgErrInfo",
  .event_describe = "BatteryOcd",
  .upload_type = 0,
  .type_index = 48,
  .data_type = 0,
  .data_count = 13,
  .para_name = { "ocdCount", "ocdLastCycle", "hocdCount", "hocdLastCycle", "uiSoc", "voltage", "temp", "LastOcdVoltage", "LastOcdCurrent", "LastOcdTemp", "LastHocdVoltage", "LastHocdCurrent", "LastHocdTemp" },
 },
 { /* ID 49 */
  .event_code = 909014004,
  .event_type = "chgErrInfo",
  .event_describe = "BatteryCuv",
  .upload_type = 0,
  .type_index = 49,
  .data_type = 0,
  .data_count = 13,
  .para_name = { "cuvCount", "cuvLastCycle", "hcuvCount", "hcuvLastCycle", "uiSoc", "voltage", "temp", "LastCuvVoltage", "LastCuvCurrent", "LastCuvTemp", "LastHcuvVoltage", "LastHcuvCurrent", "LastHcuvTemp" },
 },
 { /* ID 50 */
  .event_code = 909014005,
  .event_type = "chgErrInfo",
  .event_describe = "BatteryScd",
  .upload_type = 0,
  .type_index = 50,
  .data_type = 0,
  .data_count = 5,
  .para_name = { "hscdCount", "hscdLastCycle", "LastHscdVoltage", "LastHscdCurrent", "LastHscdTemp" },
 },
 { /* ID 51 */
  .event_code = 909014006,
  .event_type = "chgErrInfo",
  .event_describe = "BatteryCov",
  .upload_type = 0,
  .type_index = 51,
  .data_type = 0,
  .data_count = 8,
  .para_name = { "covCount", "covLastCycle", "hcovCount", "hcovLastCycle", "uiSoc", "voltage", "current", "temp" },
 },
 { /* ID 52 */
  .event_code = 909014007,
  .event_type = "chgErrInfo",
  .event_describe = "BatteryOcc",
  .upload_type = 0,
  .type_index = 52,
  .data_type = 0,
  .data_count = 8,
  .para_name = { "occCount", "occLastCycle", "hoccCount", "hoccLastCycle", "uiSoc", "voltage", "current", "temp" },
 },
 { /* ID 53 */
  .event_code = 909003001,
  .event_type = "chgStatInfo",
  .event_describe = "chgBattCycle",
  .upload_type = 1,
  .type_index = 0,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "cycleCnt" },
 },
 { /* ID 54 */
  .event_code = 909005001,
  .event_type = "chgErrInfo",
  .event_describe = "FgI2cErr",
  .upload_type = 1,
  .type_index = 1,
  .data_type = 0,
  .data_count = 1,
  .para_name = { "soc" },
 },
 { /* ID 55 */
  .event_code = 909005002,
  .event_type = "chgErrInfo",
  .event_describe = "CpI2cErr",
  .upload_type = 1,
  .type_index = 2,
  .data_type = 0,
  .data_count = 2,
  .para_name = { "masterOk", "slaveOk" },
 },
 { /* ID 56 */
  .event_code = 909006001,
  .event_type = "chgErrInfo",
  .event_describe = "VbatSocNotMatch",
  .upload_type = 1,
  .type_index = 3,
  .data_type = 0,
  .data_count = 3,
  .para_name = { "vbat", "soc", "cycleCnt" },
 },
 { /* ID 57 */
  .event_code = 909009001,
  .event_type = "chgStatInfo",
  .event_describe = "TbatHot",
  .upload_type = 1,
  .type_index = 4,
  .data_type = 0,
  .data_count = 4,
  .para_name = { "tbat", "tbatMax", "isCharging", "tboard" },
 },
 { /* ID 58 */
  .event_code = 909009002,
  .event_type = "chgStatInfo",
  .event_describe = "TbatCold",
  .upload_type = 1,
  .type_index = 5,
  .data_type = 0,
  .data_count = 4,
  .para_name = { "tbat", "tbatMin", "isCharging", "tboard" },
 },
 { /* ID 59 */
  .event_code = 909014002,
  .event_type = "chgErrInfo",
  .event_describe = "DualVbatDiff",
  .upload_type = 1,
  .type_index = 6,
  .data_type = 0,
  .data_count = 2,
  .para_name = { "chgBaseBattVol", "chgFlipBattVol" },
 },
 { /* ID 60 */
  .event_code = 909011003,
  .event_type = "chgStatInfo",
  .event_describe = "WlsMagCaseAttach",
  .upload_type = 1,
  .type_index = 7,
  .data_type = 2,
  .data_count = 0,
  .para_name = {  },
 },
};
static struct mievent_upload_type_plug g_upload_type_plug_info[PLUG_TYPE_MAX_NUM] = {
 { 1, 0 },
 { 3, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 3, 0 },
 { 3, 0 },
 { 3, 0 },
 { 3, 0 },
 { 3, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 3, 0 },
 { 3, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 3, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 5, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
 { 1, 0 },
};
static struct mievent_upload_type_time g_upload_type_time_info[TIME_TYPE_MAX_NUM] = {
 { 0, 604800, 0 },
 { 0, 600, 0 },
 { 0, 600, 0 },
 { 0, 300, 0 },
 { 0, 300, 0 },
 { 0, 300, 0 },
 { 0, 300, 0 },
 { 0, 604800, 0 },
};

static DEFINE_MUTEX(mca_mievent_lock);

/* Only the rate-limit state is locked. Transport and event notifications can
 * sleep or call consumers, and must run after releasing the lock. Saturated
 * counts cannot wrap back into an unlimited-report state.
 */
static bool mca_mievent_reserve(const struct charge_mievent_info *info)
{
 bool report = false;
 time64_t now;
 int i = info->type_index;
 mutex_lock(&mca_mievent_lock);
 if (info->upload_type == MIEVENT_UPLOAD_TYPE_PLUG &&
     i >= 0 && i < PLUG_TYPE_MAX_NUM) {
  if (g_upload_type_plug_info[i].count < g_upload_type_plug_info[i].max_count) {
   g_upload_type_plug_info[i].count++;
   report = true;
  }
 } else if (info->upload_type == MIEVENT_UPLOAD_TYPE_TIME &&
            i >= 0 && i < TIME_TYPE_MAX_NUM) {
  now = ktime_get_boottime_seconds();
  if (!g_upload_type_time_info[i].count ||
      now - g_upload_type_time_info[i].time_last >=
                g_upload_type_time_info[i].time_interval) {
   g_upload_type_time_info[i].time_last = now;
   g_upload_type_time_info[i].count = 1;
   report = true;
  }
 }
 mutex_unlock(&mca_mievent_lock);
 return report;
}

void mca_charge_mievent_report(int event_index, void *data, int size)
{
 const struct charge_mievent_info *info;
 struct misight_mievent *event;
 struct mca_event_notify_data notice = { "MCA_LOG_FULL_EVENT", 18 };
 int *values = data;
 char **strings = data;
 int i, ret;

 if (event_index < 0 || event_index >= ARRAY_SIZE(g_charge_mievent_info))
  return;
 info = &g_charge_mievent_info[event_index];
 if (size != info->data_count || (size && !data))
  return;
 if (info->data_type == MIEVENT_DATA_TYPE_STRING) {
  for (i = 0; i < size; i++)
   if (!strings[i] || strnlen(strings[i], MIEVENT_STRING_MAX_LEN) >=
                                      MIEVENT_STRING_MAX_LEN)
    return;
 }
 if (!mca_mievent_reserve(info))
  return;
 mca_event_report_uevent(&notice);
 event = cdev_tevent_alloc(info->event_code);
 if (!event) {
  mca_log_err("cdev_tevent_alloc failed\n");
  return;
 }
 ret = cdev_tevent_add_str(event, info->event_type, info->event_describe);
 for (i = 0; !ret && i < size; i++) {
  if (info->data_type == MIEVENT_DATA_TYPE_INT)
   ret = cdev_tevent_add_int(event, info->para_name[i], values[i]);
  else if (info->data_type == MIEVENT_DATA_TYPE_STRING)
   ret = cdev_tevent_add_str(event, info->para_name[i], strings[i]);
 }
 if (!ret)
  cdev_tevent_write(event);
 cdev_tevent_destroy(event);
}
EXPORT_SYMBOL_GPL(mca_charge_mievent_report);

void mca_charge_mievent_set_state(enum charge_mievent_state_ele state, int value)
{
 const struct charge_mievent_info *info;
 int i;
 mutex_lock(&mca_mievent_lock);
 if (state == MIEVENT_STATE_PLUG && !value) {
  for (i = 0; i < PLUG_TYPE_MAX_NUM; i++)
   g_upload_type_plug_info[i].count = 0;
 } else if (state == MIEVENT_STATE_END && value >= 0 &&
            value < ARRAY_SIZE(g_charge_mievent_info)) {
  info = &g_charge_mievent_info[value];
  i = info->type_index;
  if (info->upload_type == MIEVENT_UPLOAD_TYPE_PLUG && i < PLUG_TYPE_MAX_NUM)
   g_upload_type_plug_info[i].count = 0;
  else if (info->upload_type == MIEVENT_UPLOAD_TYPE_TIME && i < TIME_TYPE_MAX_NUM) {
   g_upload_type_time_info[i].time_last = 0;
   g_upload_type_time_info[i].count = 0;
  }
 }
 mutex_unlock(&mca_mievent_lock);
}
EXPORT_SYMBOL_GPL(mca_charge_mievent_set_state);
MODULE_DESCRIPTION("mca charge mievent");
MODULE_AUTHOR("lvxiaofeng@xiaomi.com");
MODULE_LICENSE("GPL v2");
