// SPDX-License-Identifier: GPL-2.0
/*
 * charger_partition.c
 *
 * charger partition driver
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

#include <linux/platform_device.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of_device.h>
#include <linux/workqueue.h>
#include <linux/err.h>
#include <linux/blkdev.h>
#include <linux/init.h>
#include <linux/delay.h>
#include <linux/printk.h>
#include <linux/spinlock.h>
#include <linux/reboot.h>
#include <linux/types.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/types.h>
#include <linux/efi.h>
#include <linux/rcupdate.h>
#include <linux/mutex.h>
#include <linux/sizes.h>
#include <linux/sched.h>
#include <linux/overflow.h>
#include <linux/of.h>
#include <scsi/scsi_device.h>
#include <scsi/scsi_cmnd.h>
#include <scsi/scsi_host.h>
#include <linux/completion.h>
#include <mca/common/mca_log.h>
#include <mca/common/mca_sysfs.h>
#include <mca/strategy/strategy_class.h>
#include <mca/common/mca_event.h>
#include <mca/common/mca_hwid.h>
#include "inc/charger_partition.h"
#include <mca/shared_memory/charger_partition_class.h>
#include "hwid.h"
#include "sd.h"

#define MYRON_CHARGER_PART_NUMBER 25
#define MYRON_CHARGER_PART_BYTES SZ_1M

/* Draft gate: the actual header version must come from a read-only device
 * capture. Neither parameter is enabled by this source or its build recipe. */
static int verified_header_version = -1;
module_param(verified_header_version, int, 0444);
static bool allow_verified_writes;
module_param(allow_verified_writes, bool, 0444);

#ifndef MCA_LOG_TAG
#define MCA_LOG_TAG "charger_partition"
#endif

struct ChargerPartition {
	struct device *dev;
	struct scsi_device *sdev;
	struct delayed_work charger_partition_work;

	int part_info_part_number;
	char *part_info_part_name;

	bool is_charger_partition_rdy;
	bool is_eu_model;
	bool not_notify_module;

	charger_partition_info_2 info_2;
};
static struct ChargerPartition *charger_partition;
static void *rw_buf;
static DEFINE_MUTEX(partition_lock);
/* The legacy alloc/read/write/dealloc ABI spans calls. Only the allocating
 * task may use the buffer; partition_lock remains held until dealloc. */
static struct task_struct *rw_owner;
static u8 rw_host, rw_type;
static u32 rw_size;

struct partinfo {
	sector_t part_start;
	sector_t part_size;
};
static struct partinfo part_info = { 0 };

static bool charger_partition_range_valid(u32 lba, u32 blocks)
{
	u64 end = (u64)lba + blocks;

	return blocks && part_info.part_size &&
	       lba >= part_info.part_start &&
	       end <= part_info.part_start + part_info.part_size;
}

static int charger_partition_validate_header(const void *buf)
{
	const charger_partition_header *header = buf;

	if (verified_header_version < 0)
		return -EOPNOTSUPP;
	if (header->magic != CHARGER_PARTITION_MAGIC ||
	    header->version != (u32)verified_header_version ||
	    header->initialized != 1)
		return -EPROTO;
	return 0;
}

static bool charger_partition_transaction_matches(u8 host, u8 type, u32 size)
{
	return READ_ONCE(rw_owner) == current && rw_buf &&
	       host == rw_host && type == rw_type && size == rw_size;
}

static void charger_partition_finish_transaction(void)
{
	kfree(rw_buf);
	rw_buf = NULL;
	WRITE_ONCE(rw_owner, NULL);
	mutex_unlock(&partition_lock);
}


static int charger_scsi_read_partition(struct scsi_device *sdev, void *buf,
				       uint32_t lba, uint32_t blocks)
{
	uint8_t cdb[16];
	int ret = 0;
	struct scsi_sense_hdr sshdr = {};
	const struct scsi_exec_args exec_args = {
		.sshdr = &sshdr,
	};
	unsigned long flags = 0;

	if (!sdev || !buf || !charger_partition_range_valid(lba, blocks))
		return -ERANGE;

	spin_lock_irqsave(sdev->host->host_lock, flags);
	ret = scsi_device_get(sdev);
	if (!ret && !scsi_device_online(sdev)) {
		ret = -ENODEV;
		scsi_device_put(sdev);
		mca_log_err("get device fail\n");
	}
	spin_unlock_irqrestore(sdev->host->host_lock, flags);
	if (ret) {
		mca_log_err("failed to get scsi device\n");
		return ret;
	}
	ret = scsi_autopm_get_device(sdev);
	if (ret) {
		scsi_device_put(sdev);
		return ret;
	}

	// Fill in the CDB with SCSI command structure
	memset(cdb, 0, sizeof(cdb));
	cdb[0] = READ_10; // Command
	cdb[1] = 0;
	cdb[2] = (lba >> 24) & 0xff; // LBA
	cdb[3] = (lba >> 16) & 0xff;
	cdb[4] = (lba >> 8) & 0xff;
	cdb[5] = (lba) & 0xff;
	cdb[6] = 0; // Group Number
	cdb[7] = (blocks >> 8) & 0xff; // Transfer Len
	cdb[8] = (blocks) & 0xff;
	cdb[9] = 0; // Control
	ret = scsi_execute_cmd(sdev, cdb, REQ_OP_DRV_IN, buf,
			       (blocks * PART_BLOCK_SIZE),
			       msecs_to_jiffies(15000), 3, &exec_args);
	if (ret)
		mca_log_err("read error %d\n", ret);

	scsi_autopm_put_device(sdev);
	scsi_device_put(sdev);
	return ret > 0 ? -EIO : ret;
}

static int charger_scsi_write_partition(struct scsi_device *sdev, void *buf,
					uint32_t lba, uint32_t blocks)
{
	uint8_t cdb[16];
	int ret = 0;
	struct scsi_sense_hdr sshdr = {};
	const struct scsi_exec_args exec_args = {
		.sshdr = &sshdr,
	};
	unsigned long flags = 0;

	if (!allow_verified_writes)
		return -EACCES;
	if (!sdev || !buf || !charger_partition_range_valid(lba, blocks))
		return -ERANGE;

	spin_lock_irqsave(sdev->host->host_lock, flags);
	ret = scsi_device_get(sdev);
	if (!ret && !scsi_device_online(sdev)) {
		ret = -ENODEV;
		scsi_device_put(sdev);
		mca_log_err("get device fail\n");
	}
	spin_unlock_irqrestore(sdev->host->host_lock, flags);

	if (ret) {
		mca_log_err("get scsi fail\n");
		return ret;
	}
	ret = scsi_autopm_get_device(sdev);
	if (ret) {
		scsi_device_put(sdev);
		return ret;
	}

	// Fill in the CDB with SCSI command structure
	memset(cdb, 0, sizeof(cdb));
	cdb[0] = WRITE_10; // Command
	cdb[1] = 0;
	cdb[2] = (lba >> 24) & 0xff; // LBA
	cdb[3] = (lba >> 16) & 0xff;
	cdb[4] = (lba >> 8) & 0xff;
	cdb[5] = (lba) & 0xff;
	cdb[6] = 0; // Group Number
	cdb[7] = (blocks >> 8) & 0xff; // Transfer Len
	cdb[8] = (blocks) & 0xff;
	cdb[9] = 0; // Control
	ret = scsi_execute_cmd(sdev, cdb, REQ_OP_DRV_OUT, buf,
			       (blocks * PART_BLOCK_SIZE),
			       msecs_to_jiffies(15000), 3, &exec_args);
	if (ret)
		mca_log_err("write error %d\n", ret);

	scsi_autopm_put_device(sdev);
	scsi_device_put(sdev);
	return ret > 0 ? -EIO : ret;
}


int charger_partition_alloc(u8 host, u8 type, uint32_t size)
{
	charger_partition_header *header;
	int ret;

	if (host >= CHARGER_PARTITION_HOST_LAST ||
	    type <= CHARGER_PARTITION_HEADER || type >= CHARGER_PARTITION_INFO_LAST ||
	    !size || size >= CHARGER_PARTITION_RWSIZE)
		return -EINVAL;
	if (READ_ONCE(rw_owner) == current)
		return -EDEADLK;
	mutex_lock(&partition_lock);
	if (!charger_partition || !READ_ONCE(charger_partition->is_charger_partition_rdy)) {
		ret = -EPROBE_DEFER;
		goto unlock;
	}
	if (!allow_verified_writes) {
		ret = -EACCES;
		goto unlock;
	}
	rw_buf = kzalloc(CHARGER_PARTITION_RWSIZE, GFP_KERNEL);
	if (!rw_buf) {
		ret = -ENOMEM;
		goto unlock;
	}
	ret = charger_scsi_read_partition(charger_partition->sdev, rw_buf,
		part_info.part_start, 1);
	if (ret)
		goto free;
	ret = charger_partition_validate_header(rw_buf);
	if (ret)
		goto free;
	header = rw_buf;
	if (header->avaliable != 1) {
		ret = -EBUSY;
		goto free;
	}
	header->avaliable = 0;
	ret = charger_scsi_write_partition(charger_partition->sdev, rw_buf,
		part_info.part_start, 1);
	if (ret)
		goto free;
	rw_host = host;
	rw_type = type;
	rw_size = size;
	WRITE_ONCE(rw_owner, current);
	return 0;
free:
	kfree(rw_buf);
	rw_buf = NULL;
unlock:
	mutex_unlock(&partition_lock);
	return ret;
}
EXPORT_SYMBOL(charger_partition_alloc);


int charger_partition_dealloc(u8 host, u8 type, uint32_t size)
{
	charger_partition_header *header;
	int ret;

	if (!charger_partition_transaction_matches(host, type, size))
		return -EPERM;
	ret = charger_scsi_read_partition(charger_partition->sdev, rw_buf,
		part_info.part_start, 1);
	if (ret)
		goto out;
	ret = charger_partition_validate_header(rw_buf);
	if (ret)
		goto out;
	header = rw_buf;
	if (header->avaliable != 0) {
		ret = -ESTALE;
		goto out;
	}
	header->avaliable = 1;
	ret = charger_scsi_write_partition(charger_partition->sdev, rw_buf,
		part_info.part_start, 1);
out:
	charger_partition_finish_transaction();
	return ret;
}
EXPORT_SYMBOL(charger_partition_dealloc);


void *charger_partition_read(u8 host, u8 type, uint32_t size)
{
	int ret;

	if (!charger_partition_transaction_matches(host, type, size))
		return NULL;
	ret = charger_scsi_read_partition(charger_partition->sdev, rw_buf,
		part_info.part_start + type, 1);
	return ret ? NULL : rw_buf;
}
EXPORT_SYMBOL(charger_partition_read);


int charger_partition_write(u8 host, u8 type, void *buf, uint32_t size)
{
	int ret;

	if (!charger_partition_transaction_matches(host, type, size) || !buf)
		return -EPERM;
	/* The callers use private structs. Disallow aliasing our I/O buffer,
	 * which the preserving read below would overwrite. */
	if (buf == rw_buf)
		return -EINVAL;
	ret = charger_scsi_read_partition(charger_partition->sdev, rw_buf,
		part_info.part_start + type, 1);
	if (ret)
		return ret;
	memcpy(rw_buf, buf, size);
	return charger_scsi_write_partition(charger_partition->sdev, rw_buf,
		part_info.part_start + type, 1);
}
EXPORT_SYMBOL(charger_partition_write);


/* Read-modify-write a single record while the legacy transaction mutex is held.
 * This preserves other fields in the same record instead of zeroing them. */
static int charger_partition_read_record(u8 type, void *out, u32 size)
{
	void *buf;
	int ret, cleanup_ret;

	if (!out)
		return -EINVAL;
	ret = charger_partition_alloc(CHARGER_PARTITION_HOST_KERNEL, type, size);
	if (ret)
		return ret;
	buf = charger_partition_read(CHARGER_PARTITION_HOST_KERNEL, type, size);
	if (buf)
		memcpy(out, buf, size);
	else
		ret = -EIO;
	cleanup_ret = charger_partition_dealloc(CHARGER_PARTITION_HOST_KERNEL, type, size);
	return ret ? ret : cleanup_ret;
}

static int charger_partition_update_field(u8 type, u32 record_size, u32 offset,
					 const void *value, u32 length)
{
	u8 record[sizeof(charger_partition_info_2)];
	void *buf;
	int ret, cleanup_ret;

	if (!value || !length || record_size > sizeof(record) ||
	    offset > record_size || length > record_size - offset)
		return -EINVAL;
	ret = charger_partition_alloc(CHARGER_PARTITION_HOST_KERNEL, type, record_size);
	if (ret)
		return ret;
	buf = charger_partition_read(CHARGER_PARTITION_HOST_KERNEL, type, record_size);
	if (!buf) {
		ret = -EIO;
		goto out;
	}
	memcpy(record, buf, record_size);
	memcpy(record + offset, value, length);
	ret = charger_partition_write(CHARGER_PARTITION_HOST_KERNEL, type,
		record, record_size);
out:
	cleanup_ret = charger_partition_dealloc(CHARGER_PARTITION_HOST_KERNEL,
		type, record_size);
	return ret ? ret : cleanup_ret;
}


int charger_partition_get_eu_model(bool *is_eu_model)
{
	charger_partition_info_2 info;
	int ret;

	if (!is_eu_model)
		return -EINVAL;
	ret = charger_partition_read_record(CHARGER_PARTITION_INFO_2, &info, sizeof(info));
	if (ret)
		return ret;
	if (info.eu_mode > 1)
		return -EPROTO;
	*is_eu_model = info.eu_mode;
	return 0;
}
EXPORT_SYMBOL(charger_partition_get_eu_model);


static int charger_partition_read_info_1(charger_partition_info_1 *out)
{
	return charger_partition_read_record(CHARGER_PARTITION_INFO_1, out, sizeof(*out));
}




int charger_partition_read_double85(int *val)
{
	charger_partition_info_1 info_1;
	int ret;

	if (!val)
		return -EINVAL;
	ret = charger_partition_read_info_1(&info_1);
	if (ret)
		return ret;
	*val = info_1.double85;
	return 0;
}
EXPORT_SYMBOL(charger_partition_read_double85);

int charger_partition_write_double85(int val)
{
	u32 value = val;

	return charger_partition_update_field(CHARGER_PARTITION_INFO_1,
		sizeof(charger_partition_info_1), offsetof(charger_partition_info_1, double85),
		&value, sizeof(value));
}
EXPORT_SYMBOL(charger_partition_write_double85);

int charger_partition_write_remove_temp_limit(int val)
{
	u32 value = val;

	return charger_partition_update_field(CHARGER_PARTITION_INFO_1,
		sizeof(charger_partition_info_1), offsetof(charger_partition_info_1, remove_temp_limit),
		&value, sizeof(value));
}
EXPORT_SYMBOL(charger_partition_write_remove_temp_limit);

int charger_partition_read_remove_temp_limit(int *val)
{
	charger_partition_info_1 info_1;
	int ret;

	if (!val)
		return -EINVAL;
	ret = charger_partition_read_info_1(&info_1);
	if (ret)
		return ret;
	*val = info_1.remove_temp_limit;
	return 0;
}

int charger_partition_read_memory_test(int *val)
{
	charger_partition_info_1 info_1;
	int ret;

	if (!val)
		return -EINVAL;
	ret = charger_partition_read_info_1(&info_1);
	if (ret)
		return ret;
	*val = info_1.memory_test;
	return 0;
}
EXPORT_SYMBOL(charger_partition_read_memory_test);

int charger_partition_write_memory_test(int val)
{
	u32 value = val;

	return charger_partition_update_field(CHARGER_PARTITION_INFO_1,
		sizeof(charger_partition_info_1), offsetof(charger_partition_info_1, memory_test),
		&value, sizeof(value));
}
EXPORT_SYMBOL(charger_partition_write_memory_test);

int charger_partition_read_soc_limit(int *val)
{
	charger_partition_info_1 info_1;
	int ret;

	if (!val)
		return -EINVAL;
	ret = charger_partition_read_info_1(&info_1);
	if (ret)
		return ret;
	*val = info_1.soc_limit;
	return 0;
}
EXPORT_SYMBOL(charger_partition_read_soc_limit);

int charger_partition_write_soc_limit(int val)
{
	u32 value = val;

	return charger_partition_update_field(CHARGER_PARTITION_INFO_1,
		sizeof(charger_partition_info_1), offsetof(charger_partition_info_1, soc_limit),
		&value, sizeof(value));
}
EXPORT_SYMBOL(charger_partition_write_soc_limit);


int charger_partition_get_mishow(bool *mishow)
{
	charger_partition_info_1 info;
	int ret;

	if (!mishow)
		return -EINVAL;
	ret = charger_partition_read_info_1(&info);
	if (ret)
		return ret;
	*mishow = !!info.mishow;
	return 0;
}
EXPORT_SYMBOL(charger_partition_get_mishow);


int charger_partition_write_eu_model(bool eu_mode)
{
	u32 value = eu_mode;

	return charger_partition_update_field(CHARGER_PARTITION_INFO_2,
		sizeof(charger_partition_info_2), offsetof(charger_partition_info_2, eu_mode),
		&value, sizeof(value));
}
EXPORT_SYMBOL(charger_partition_write_eu_model);

static ssize_t charger_partition_sysfs_show(struct device *dev,
					    struct device_attribute *attr,
					    char *buf);
static ssize_t charger_partition_sysfs_store(struct device *dev,
					     struct device_attribute *attr,
					     const char *buf, size_t count);
static int charger_partition_get_info_2(void);

struct mca_sysfs_attr_info charger_partition_sysfs_field_tbl[] = {
	mca_sysfs_attr_rw(charger_partition_sysfs, 0664,
			  MCA_PROP_CHARGER_PARTITION_MISHOW,
			  charger_partition_mishow),
	mca_sysfs_attr_rw(charger_partition_sysfs, 0664,
			  MCA_PROP_CHARGER_PARTITION_POWEROFFMODE,
			  charger_partition_poweroffmode),
	mca_sysfs_attr_rw(charger_partition_sysfs, 0664,
			  MCA_PROP_CHARGER_PARTITION_PROP_EU_MODE,
			  charger_partition_prop_eu_mode),
};

#define CHARGER_PARTITION_SYSFS_ATTRS_SIZE \
	ARRAY_SIZE(charger_partition_sysfs_field_tbl)

static struct attribute
	*charger_partition_sysfs_attrs[CHARGER_PARTITION_SYSFS_ATTRS_SIZE + 1];

static const struct attribute_group charger_partition_sysfs_attr_group = {
	.attrs = charger_partition_sysfs_attrs,
};

static ssize_t charger_partition_sysfs_show(struct device *dev,
					    struct device_attribute *attr,
					    char *buf)
{
	struct mca_sysfs_attr_info *attr_info;
	ssize_t count = 0;
	int val = 0, ret = 0;
	charger_partition_info_1 *info_1 = NULL;
	charger_partition_info_2 *info_2 = NULL;

	attr_info = mca_sysfs_lookup_attr(attr->attr.name,
					  charger_partition_sysfs_field_tbl,
					  CHARGER_PARTITION_SYSFS_ATTRS_SIZE);
	if (!attr_info)
		return -1;

	switch (attr_info->sysfs_attr_name) {
	case MCA_PROP_CHARGER_PARTITION_MISHOW:
		ret = charger_partition_alloc(CHARGER_PARTITION_HOST_KERNEL,
					      CHARGER_PARTITION_INFO_1,
					      sizeof(charger_partition_info_1));
		if (ret < 0) {
			mca_log_err("failed to alloc\n");
			return -1;
		}

		info_1 = (charger_partition_info_1 *)charger_partition_read(
			CHARGER_PARTITION_HOST_KERNEL, CHARGER_PARTITION_INFO_1,
			sizeof(charger_partition_info_1));
		if (!info_1) {
			mca_log_err("failed to read\n");
			ret = charger_partition_dealloc(
				CHARGER_PARTITION_HOST_KERNEL,
				CHARGER_PARTITION_INFO_1,
				sizeof(charger_partition_info_1));
			if (ret < 0) {
				mca_log_err("failed to dealloc\n");
				return -1;
			}
			return -1;
		}
		val = info_1->mishow;

		ret = charger_partition_dealloc(
			CHARGER_PARTITION_HOST_KERNEL, CHARGER_PARTITION_INFO_1,
			sizeof(charger_partition_info_1));
		if (ret < 0) {
			mca_log_err("failed to dealloc\n");
			return -1;
		}
		count = scnprintf(buf, PAGE_SIZE, "%d\n", val);
		break;
	case MCA_PROP_CHARGER_PARTITION_POWEROFFMODE:
		ret = charger_partition_alloc(CHARGER_PARTITION_HOST_KERNEL,
					      CHARGER_PARTITION_INFO_1,
					      sizeof(charger_partition_info_1));
		if (ret < 0) {
			mca_log_err("failed to alloc\n");
			return -1;
		}

		info_1 = (charger_partition_info_1 *)charger_partition_read(
			CHARGER_PARTITION_HOST_KERNEL, CHARGER_PARTITION_INFO_1,
			sizeof(charger_partition_info_1));
		if (!info_1) {
			mca_log_err("failed to read\n");
			ret = charger_partition_dealloc(
				CHARGER_PARTITION_HOST_KERNEL,
				CHARGER_PARTITION_INFO_1,
				sizeof(charger_partition_info_1));
			if (ret < 0) {
				mca_log_err("failed to dealloc\n");
				return -1;
			}
			return -1;
		}
		val = info_1->power_off_mode;

		ret = charger_partition_dealloc(
			CHARGER_PARTITION_HOST_KERNEL, CHARGER_PARTITION_INFO_1,
			sizeof(charger_partition_info_1));
		if (ret < 0) {
			mca_log_err("failed to dealloc\n");
			return -1;
		}
		count = scnprintf(buf, PAGE_SIZE, "%d\n", val);
		break;
	case MCA_PROP_CHARGER_PARTITION_PROP_EU_MODE:
		ret = charger_partition_alloc(CHARGER_PARTITION_HOST_KERNEL,
					      CHARGER_PARTITION_INFO_2,
					      sizeof(charger_partition_info_2));
		if (ret < 0) {
			mca_log_err("failed to alloc\n");
			return -1;
		}

		info_2 = (charger_partition_info_2 *)charger_partition_read(
			CHARGER_PARTITION_HOST_KERNEL, CHARGER_PARTITION_INFO_2,
			sizeof(charger_partition_info_2));
		if (!info_2) {
			mca_log_err("failed to read\n");
			ret = charger_partition_dealloc(
				CHARGER_PARTITION_HOST_KERNEL,
				CHARGER_PARTITION_INFO_2,
				sizeof(charger_partition_info_2));
			if (ret < 0) {
				mca_log_err(
					"[ChgPartition] failed to dealloc\n");
				return -1;
			}
			return -1;
		}
		val = info_2->eu_mode;

		ret = charger_partition_dealloc(
			CHARGER_PARTITION_HOST_KERNEL, CHARGER_PARTITION_INFO_2,
			sizeof(charger_partition_info_2));
		if (ret < 0) {
			mca_log_err("[ChgPartition] failed to dealloc\n");
			return -1;
		}
		count = scnprintf(buf, PAGE_SIZE, "%d\n", val);
		break;
	default:
		break;
	}

	return count;
}


static ssize_t charger_partition_sysfs_store(struct device *dev,
					     struct device_attribute *attr,
					     const char *buf, size_t count)
{
	struct mca_sysfs_attr_info *attr_info;
	int val, ret;
	u32 value, type, offset;

	attr_info = mca_sysfs_lookup_attr(attr->attr.name,
		charger_partition_sysfs_field_tbl, CHARGER_PARTITION_SYSFS_ATTRS_SIZE);
	if (!attr_info || kstrtoint(buf, 0, &val))
		return -EINVAL;
	value = val;
	type = CHARGER_PARTITION_INFO_1;
	switch (attr_info->sysfs_attr_name) {
	case MCA_PROP_CHARGER_PARTITION_MISHOW:
		offset = offsetof(charger_partition_info_1, mishow);
		break;
	case MCA_PROP_CHARGER_PARTITION_POWEROFFMODE:
		offset = offsetof(charger_partition_info_1, power_off_mode);
		break;
	case MCA_PROP_CHARGER_PARTITION_PROP_EU_MODE:
		if (value > 1)
			return -EINVAL;
		type = CHARGER_PARTITION_INFO_2;
		offset = offsetof(charger_partition_info_2, eu_mode);
		break;
	default:
		return -EINVAL;
	}
	BUILD_BUG_ON(sizeof(charger_partition_info_1) != sizeof(charger_partition_info_2));
	ret = charger_partition_update_field(type, sizeof(charger_partition_info_1),
		offset, &value, sizeof(value));
	return ret ? ret : count;
}

static int charger_partition_sysfs_create_group(struct device *dev)
{
	mca_sysfs_init_attrs(charger_partition_sysfs_attrs,
			     charger_partition_sysfs_field_tbl,
			     CHARGER_PARTITION_SYSFS_ATTRS_SIZE);
	return mca_sysfs_create_link_group("charger", "charger_partition", dev,
					   &charger_partition_sysfs_attr_group);
}

static void charger_partition_sysfs_remove_group(struct device *dev)
{
	mca_sysfs_remove_link_group("charger", "charger_partition", dev,
				    &charger_partition_sysfs_attr_group);
}


static bool look_up_scsi_device(int lun)
{
	struct Scsi_Host *shost;
	struct scsi_device *sdev;

	if (charger_partition->sdev) {
		scsi_device_put(charger_partition->sdev);
		charger_partition->sdev = NULL;
	}
	shost = scsi_host_lookup(0);
	if (!shost)
		return false;
	sdev = scsi_device_lookup(shost, 0, 0, lun);
	scsi_host_put(shost);
	charger_partition->sdev = sdev;
	return sdev != NULL;
}

static bool check_device_is_correct(void)
{
	if (strncmp(charger_partition->sdev->host->hostt->proc_name, UFSHCD,
		    strlen(UFSHCD))) {
		/*check if the device is ufs. If not, just return directly.*/
		mca_log_err("proc name is not ufshcd, name: %s\n",
			    charger_partition->sdev->host->hostt->proc_name);
		return false;
	}

	return true;
}

static bool get_charger_partition_info(void)
{
	struct scsi_disk *sdkp = NULL;
	struct scsi_device *sdev = charger_partition->sdev;
	int part_number = charger_partition->part_info_part_number;
	struct block_device *part;

	if (!sdev->sdev_gendev.driver_data) {
		mca_log_err("scsi disk is null\n");
		return false;
	}

	sdkp = (struct scsi_disk *)sdev->sdev_gendev.driver_data;
	if (!sdkp->disk) {
		mca_log_err("gendisk is null\n");
		return false;
	}

	charger_partition->part_info_part_name = sdkp->disk->disk_name;
	mca_log_err("partion: %s part_number:%d\n",
		    charger_partition->part_info_part_name, part_number);

	part = xa_load(&sdkp->disk->part_tbl, part_number);
	if (!part) {
		mca_log_err("device is null\n");
		return false;
	}

	if (!part->bd_meta_info) {
		mca_log_err("part_num %d has no meta_info, skip\n",
			    part_number);
		return false;
	}

	if (strncmp(part->bd_meta_info->volname, "charger",
		    sizeof("charger"))) {
		mca_log_err("[charger] this is not lun0\n");
		return false;
	}

	if (bdev_logical_block_size(part) != PART_BLOCK_SIZE ||
	    bdev_nr_bytes(part) != MYRON_CHARGER_PART_BYTES ||
	    part->bd_start_sect % (PART_BLOCK_SIZE / PART_SECTOR_SIZE) ||
	    bdev_nr_sectors(part) % (PART_BLOCK_SIZE / PART_SECTOR_SIZE) ||
	    part->bd_start_sect / (PART_BLOCK_SIZE / PART_SECTOR_SIZE) > U32_MAX ||
	    (part->bd_start_sect + bdev_nr_sectors(part)) /
		(PART_BLOCK_SIZE / PART_SECTOR_SIZE) > U32_MAX) {
		mca_log_err("charger geometry is not the verified Myron layout\n");
		return false;
	}

	part_info.part_start =
		part->bd_start_sect * PART_SECTOR_SIZE / PART_BLOCK_SIZE;
	part_info.part_size =
		bdev_nr_sectors(part) * PART_SECTOR_SIZE / PART_BLOCK_SIZE;

	mca_log_err("partion: %s start %llu(block) size %llu(block)\n",
		    charger_partition->part_info_part_name,
		    part_info.part_start, part_info.part_size);
	return true;
}


int check_charger_partition_header(void)
{
	charger_partition_header *header;
	int ret;

	header = kzalloc(CHARGER_PARTITION_RWSIZE, GFP_KERNEL);
	if (!header)
		return -ENOMEM;
	ret = charger_scsi_read_partition(charger_partition->sdev, header,
		part_info.part_start, 1);
	if (!ret) {
		mca_log_info("charger header magic=0x%x version=%u initialized=%u available=%u\n",
			header->magic, header->version, header->initialized,
			header->avaliable);
		ret = charger_partition_validate_header(header);
	}
	if (!ret && header->avaliable != 1)
		ret = -EBUSY;
	/* Never initialize, repair magic, reset ownership, or erase an unknown
	 * partition. Default gates deliberately leave this provider unavailable. */
	if (!ret && !allow_verified_writes)
		ret = -EACCES;
	kfree(header);
	return ret;
}


static int charger_partition_get_info_2(void)
{
	bool eu_mode;
	int ret = charger_partition_get_eu_model(&eu_mode);

	if (ret)
		return ret;
	/* No storage lock is held while calling consumer callbacks. */
	if (eu_mode) {
		mca_strategy_func_process(STRATEGY_FUNC_TYPE_FG, MCA_EVENT_IS_EU_MODEL, 1);
		mca_strategy_func_process(STRATEGY_FUNC_TYPE_BUCK_CHARGE, MCA_EVENT_IS_EU_MODEL, 1);
		mca_strategy_func_process(STRATEGY_FUNC_TYPE_QUICK_CHARGE, MCA_EVENT_IS_EU_MODEL, 1);
	}
	return 0;
}




int charger_partition_read_ocd_count(u32 *first, u32 *second)
{
	charger_partition_info_2 info;
	int ret;

	if (!first || !second)
		return -EINVAL;
	ret = charger_partition_read_record(CHARGER_PARTITION_INFO_2, &info, sizeof(info));
	if (ret)
		return ret;
	*first = info.ocd_count[0];
	*second = info.ocd_count[1];
	return 0;
}
EXPORT_SYMBOL(charger_partition_read_ocd_count);

int charger_partition_write_ocd_count(u32 first, u32 second)
{
	u32 value[2] = { first, second };

	return charger_partition_update_field(CHARGER_PARTITION_INFO_2,
		sizeof(charger_partition_info_2), offsetof(charger_partition_info_2, ocd_count),
		&value, sizeof(value));
}
EXPORT_SYMBOL(charger_partition_write_ocd_count);

int charger_partition_read_cuv_count(u32 *first, u32 *second)
{
	charger_partition_info_2 info;
	int ret;

	if (!first || !second)
		return -EINVAL;
	ret = charger_partition_read_record(CHARGER_PARTITION_INFO_2, &info, sizeof(info));
	if (ret)
		return ret;
	*first = info.cuv_count[0];
	*second = info.cuv_count[1];
	return 0;
}
EXPORT_SYMBOL(charger_partition_read_cuv_count);

int charger_partition_write_cuv_count(u32 first, u32 second)
{
	u32 value[2] = { first, second };

	return charger_partition_update_field(CHARGER_PARTITION_INFO_2,
		sizeof(charger_partition_info_2), offsetof(charger_partition_info_2, cuv_count),
		&value, sizeof(value));
}
EXPORT_SYMBOL(charger_partition_write_cuv_count);

int charger_partition_read_hscd_count(u32 *first)
{
	charger_partition_info_2 info;
	int ret;

	if (!first)
		return -EINVAL;
	ret = charger_partition_read_record(CHARGER_PARTITION_INFO_2, &info, sizeof(info));
	if (ret)
		return ret;
	*first = info.hscd_count;
	return 0;
}
EXPORT_SYMBOL(charger_partition_read_hscd_count);

int charger_partition_write_hcsd_count(u32 first)
{
	u32 value = first;

	return charger_partition_update_field(CHARGER_PARTITION_INFO_2,
		sizeof(charger_partition_info_2), offsetof(charger_partition_info_2, hscd_count),
		&value, sizeof(value));
}
EXPORT_SYMBOL(charger_partition_write_hcsd_count);

static int charger_partition_get_info_1(void)
{
	int ret = 0;
	charger_partition_info_1 *info_1 = NULL;

	ret = charger_partition_alloc(CHARGER_PARTITION_HOST_KERNEL,
				      CHARGER_PARTITION_INFO_1,
				      sizeof(charger_partition_info_1));
	if (ret < 0) {
		mca_log_err("failed to alloc\n");
		return -1;
	}

	info_1 = (charger_partition_info_1 *)charger_partition_read(
		CHARGER_PARTITION_HOST_KERNEL, CHARGER_PARTITION_INFO_1,
		sizeof(charger_partition_info_1));
	if (!info_1) {
		mca_log_err("failed to read\n");
		ret = charger_partition_dealloc(
			CHARGER_PARTITION_HOST_KERNEL, CHARGER_PARTITION_INFO_1,
			sizeof(charger_partition_info_1));
		if (ret < 0) {
			mca_log_err("failed to dealloc\n");
			return -1;
		}
		return -1;
	}
	mca_log_err(
		"ret: %d, mishow: 0x%0x, zero_speed_mode: %u, power_off_mode: %u, double85: %u, remove_temp_limit: %u, memory_test: %u, soc_limit: %d\n",
		ret, info_1->mishow, info_1->zero_speed_mode,
		info_1->power_off_mode, info_1->double85,
		info_1->remove_temp_limit, info_1->memory_test,
		info_1->soc_limit);

	ret = charger_partition_dealloc(CHARGER_PARTITION_HOST_KERNEL,
					CHARGER_PARTITION_INFO_1,
					sizeof(charger_partition_info_1));
	if (ret < 0) {
		mca_log_err("failed to dealloc\n");
		return -1;
	}
	return 0;
}

static int charger_partition_set_info_1(void)
{
	int ret = 0;
	charger_partition_info_1 info_1 = { .power_off_mode = 2,
					    .zero_speed_mode = 2,
					    .mishow = 0x23456789,
					    .reserved = 0 };

	ret = charger_partition_alloc(CHARGER_PARTITION_HOST_KERNEL,
				      CHARGER_PARTITION_INFO_1,
				      sizeof(charger_partition_info_1));
	if (ret < 0) {
		mca_log_err("failed to alloc\n");
		return -1;
	}

	ret = charger_partition_write(CHARGER_PARTITION_HOST_KERNEL,
				      CHARGER_PARTITION_INFO_1, (void *)&info_1,
				      sizeof(charger_partition_info_1));
	if (ret < 0) {
		mca_log_err("failed to write\n");
		ret = charger_partition_dealloc(
			CHARGER_PARTITION_HOST_KERNEL, CHARGER_PARTITION_INFO_1,
			sizeof(charger_partition_info_1));
		if (ret < 0) {
			mca_log_err("failed to dealloc\n");
			return -1;
		}
		return -1;
	}

	ret = charger_partition_dealloc(CHARGER_PARTITION_HOST_KERNEL,
					CHARGER_PARTITION_INFO_1,
					sizeof(charger_partition_info_1));
	if (ret < 0) {
		mca_log_err("failed to dealloc\n");
		return -1;
	}
	return 0;
}


static int charger_partition_prepare(void)
{
	charger_partition_info_1 info;
	int ret;

	ret = charger_partition_get_info_1();
	if (ret)
		return ret;
	/* Original policy reset retained for review, not enabled by this draft. */
	ret = charger_partition_set_info_1();
	if (ret)
		return ret;
	ret = charger_partition_read_info_1(&info);
	if (ret)
		return ret;
	if (info.double85)
		mca_event_block_notify(MCA_EVENT_TYPE_SUBPMIC_INFO, MCA_EVENT_DEBUG_CTRL_DOUBLE85, &info.double85);
	if (info.remove_temp_limit)
		mca_event_block_notify(MCA_EVENT_TYPE_SUBPMIC_INFO, MCA_EVENT_DEBUG_CTRL_REMOVE_TEMP_LIMIT, &info.remove_temp_limit);
	if (info.memory_test)
		mca_event_block_notify(MCA_EVENT_TYPE_SUBPMIC_INFO, MCA_EVENT_DEBUG_CTRL_MEMORY_TEST, &info.memory_test);
	if (info.soc_limit)
		mca_event_block_notify(MCA_EVENT_TYPE_SUBPMIC_INFO, MCA_EVENT_DEBUG_CTRL_SOC_LIMIT, &info.soc_limit);
	return charger_partition_get_info_2();
}



static void charger_partition_work(struct work_struct *work)
{
	struct ChargerPartition *part = container_of(to_delayed_work(work),
		struct ChargerPartition, charger_partition_work);
	static int retry;
	int lun, ret = -ENODEV;
	bool retry_needed;

	/* A retry must not replace the SCSI device during an exported transaction. */
	mutex_lock(&partition_lock);
	part->part_info_part_number = MYRON_CHARGER_PART_NUMBER;
	for (lun = 0; lun < 6; lun++) {
		if (!look_up_scsi_device(lun) || !check_device_is_correct() ||
		    !get_charger_partition_info())
			continue;
		ret = check_charger_partition_header();
		break;
	}
	WRITE_ONCE(part->is_charger_partition_rdy, !ret);
	mutex_unlock(&partition_lock);
	if (!ret) {
		if (part->not_notify_module) {
			ret = charger_partition_get_info_2();
			if (!ret)
				part->not_notify_module = false;
			mutex_lock(&partition_lock);
			WRITE_ONCE(part->is_charger_partition_rdy, false);
			mutex_unlock(&partition_lock);
		} else {
			ret = charger_partition_prepare();
			if (ret) {
				mutex_lock(&partition_lock);
				WRITE_ONCE(part->is_charger_partition_rdy, false);
				mutex_unlock(&partition_lock);
			}
		}
	}
	retry_needed = !READ_ONCE(part->is_charger_partition_rdy);
	if (retry_needed && retry++ < CHARGER_PARTITION_RETRY_TIMES)
		schedule_delayed_work(&part->charger_partition_work,
			msecs_to_jiffies(CHARGER_WORK_DELAY_MS));
	if (ret)
		mca_log_err("charger storage unavailable: %d\n", ret);
}


static int charger_partition_probe(struct platform_device *pdev)
{
	struct ChargerPartition *part;
	int ret;

	part = devm_kzalloc(&pdev->dev, sizeof(*part), GFP_KERNEL);
	if (!part)
		return -ENOMEM;
	part->dev = &pdev->dev;
	part->not_notify_module = true;
	INIT_DELAYED_WORK(&part->charger_partition_work, charger_partition_work);
	platform_set_drvdata(pdev, part);
	mutex_lock(&partition_lock);
	if (charger_partition) {
		mutex_unlock(&partition_lock);
		return -EBUSY;
	}
	charger_partition = part;
	mutex_unlock(&partition_lock);
	ret = charger_partition_sysfs_create_group(part->dev);
	if (ret) {
		mutex_lock(&partition_lock);
		charger_partition = NULL;
		mutex_unlock(&partition_lock);
		return ret;
	}
	schedule_delayed_work(&part->charger_partition_work, 0);
	mca_log_info("probe ok; storage still requires verification\n");
	return 0;
}


static void charger_partition_remove(struct platform_device *pdev)
{
	struct ChargerPartition *part = platform_get_drvdata(pdev);

	cancel_delayed_work_sync(&part->charger_partition_work);
	charger_partition_sysfs_remove_group(&pdev->dev);
	mutex_lock(&partition_lock);
	part->is_charger_partition_rdy = false;
	charger_partition = NULL;
	if (part->sdev) {
		scsi_device_put(part->sdev);
		part->sdev = NULL;
	}
	mutex_unlock(&partition_lock);
}

static const struct of_device_id match_table[] = {
	{ .compatible = "xiaomi,charger_partition" },
	{},
};

static struct platform_driver charger_partition_driver = {
	.driver = {
		.owner = THIS_MODULE,
		.name = "charger_partition",
		.of_match_table = match_table,
	},
	.probe = charger_partition_probe,
	.remove = charger_partition_remove,
};

static int __init charger_partition_init(void)
{
	return platform_driver_register(&charger_partition_driver);
}
module_init(charger_partition_init);

static void __exit charger_partition_exit(void)
{
	platform_driver_unregister(&charger_partition_driver);
}
module_exit(charger_partition_exit);

MODULE_DESCRIPTION("smart charge driver");
MODULE_AUTHOR("liluting@xiaomi.com");
MODULE_LICENSE("GPL v2");
