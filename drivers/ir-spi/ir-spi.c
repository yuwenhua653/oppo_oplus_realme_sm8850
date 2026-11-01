/*
 * Copyright (c) 2016 Samsung Electronics Co., Ltd.
 * Author: Andi Shyti <andi.shyti@samsung.it>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 *
 * SPI driven IR LED device driver
 */
/* Myron 6.12 adaptation: preserve the raw-SPI userspace ABI, serialize
 * buffer changes, and retain open-file state until the last close. */
#include <linux/compat.h>
#include <linux/err.h>
#include <linux/fs.h>
#include <linux/kref.h>
#include <linux/limits.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/slab.h>
#include <linux/spi/spi.h>
#include <linux/uaccess.h>
#include <uapi/linux/lirc.h>

#define IR_SPI_DRIVER_NAME "ir-spi"
#define IR_SPI_DEFAULT_FREQUENCY 1920000
#define IR_SPI_BIT_PER_WORD 32
#define IR_SPI_DATA_BUFFER 150000

struct ir_spi_data {
    unsigned int nusers;
    size_t buffer_size;
    u8 *buffer;
    struct spi_device *spi;
    struct spi_transfer xfer;
    struct mutex mutex;
    struct kref ref;
    struct miscdevice misc;
};

static void ir_spi_free(struct kref *ref)
{
    struct ir_spi_data *idata = container_of(ref, struct ir_spi_data, ref);
    kfree(idata->buffer);
    mutex_destroy(&idata->mutex);
    kfree(idata);
}

static int ir_spi_resize_locked(struct ir_spi_data *idata, size_t length)
{
    void *new;
    if (length > INT_MAX)
        return -EMSGSIZE;
    if (length <= idata->buffer_size)
        return 0;
    new = krealloc(idata->buffer, length, GFP_KERNEL | GFP_DMA);
    if (!new)
        return -ENOMEM;
    idata->buffer = new;
    idata->buffer_size = length;
    return 0;
}

static ssize_t ir_spi_chardev_write(struct file *file,
        const char __user *buffer, size_t length, loff_t *offset)
{
    struct ir_spi_data *idata = file->private_data;
    struct spi_transfer transfer;
    int ret;
    mutex_lock(&idata->mutex);
    if (!idata->spi) {
        ret = -ENODEV;
        goto out;
    }
    if (length > INT_MAX) {
        ret = -EMSGSIZE;
        goto out;
    }
    if (idata->xfer.len && idata->xfer.len != length) {
        ret = -EINVAL;
        goto out;
    }
    if (!length) {
        ret = 0;
        goto out;
    }
    ret = ir_spi_resize_locked(idata, length);
    if (ret)
        goto out;
    if (copy_from_user(idata->buffer, buffer, length)) {
        ret = -EFAULT;
        goto out;
    }
    transfer = idata->xfer;
    transfer.len = length;
    transfer.tx_buf = idata->buffer;
    ret = spi_sync_transfer(idata->spi, &transfer, 1);
    if (!ret)
        ret = length;
out:
    mutex_unlock(&idata->mutex);
    return ret;
}

static int ir_spi_chardev_open(struct inode *inode, struct file *file)
{
    struct ir_spi_data *idata = container_of(file->private_data,
            struct ir_spi_data, misc);
    int ret = 0;
    /* misc_open holds misc_mtx until this callback returns; deregistration
     * precedes dropping the probe reference in remove. */
    mutex_lock(&idata->mutex);
    if (!idata->spi)
        ret = -ENODEV;
    else if (idata->nusers >= SHRT_MAX)
        ret = -EBUSY;
    else {
        kref_get(&idata->ref);
        idata->nusers++;
        file->private_data = idata;
    }
    mutex_unlock(&idata->mutex);
    return ret;
}

static int ir_spi_chardev_close(struct inode *inode, struct file *file)
{
    struct ir_spi_data *idata = file->private_data;
    mutex_lock(&idata->mutex);
    if (!--idata->nusers) {
        idata->xfer.len = 0;
        idata->xfer.speed_hz = IR_SPI_DEFAULT_FREQUENCY;
    }
    mutex_unlock(&idata->mutex);
    file->private_data = NULL;
    kref_put(&idata->ref, ir_spi_free);
    return 0;
}

static long ir_spi_chardev_ioctl(struct file *file, unsigned int cmd,
        unsigned long arg)
{
    struct ir_spi_data *idata = file->private_data;
    __u32 p;
    int ret;
    if (cmd != LIRC_SET_SEND_MODE)
        return -EINVAL;
    if (get_user(p, (__u32 __user *)arg))
        return -EFAULT;
    mutex_lock(&idata->mutex);
    if (!idata->spi)
        ret = -ENODEV;
    else if (idata->xfer.len == p)
        ret = 0;
    else if (idata->nusers > 1)
        ret = -EPERM;
    else {
        ret = ir_spi_resize_locked(idata, p);
        if (!ret)
            idata->xfer.len = p;
    }
    mutex_unlock(&idata->mutex);
    return ret;
}

static const struct file_operations ir_spi_fops = {
    .owner = THIS_MODULE,
    .write = ir_spi_chardev_write,
    .open = ir_spi_chardev_open,
    .release = ir_spi_chardev_close,
    .llseek = noop_llseek,
    .unlocked_ioctl = ir_spi_chardev_ioctl,
#ifdef CONFIG_COMPAT
    .compat_ioctl = compat_ptr_ioctl,
#endif
};

static int ir_spi_probe(struct spi_device *spi)
{
    struct ir_spi_data *idata;
    int ret;
    idata = kzalloc(sizeof(*idata), GFP_KERNEL);
    if (!idata)
        return -ENOMEM;
    mutex_init(&idata->mutex);
    kref_init(&idata->ref);
    idata->spi = spi;
    idata->xfer.bits_per_word = IR_SPI_BIT_PER_WORD;
    idata->xfer.speed_hz = IR_SPI_DEFAULT_FREQUENCY;
    ret = ir_spi_resize_locked(idata, IR_SPI_DATA_BUFFER);
    if (ret)
        goto fail;
    idata->misc.minor = MISC_DYNAMIC_MINOR;
    idata->misc.name = "ir_spi";
    idata->misc.nodename = "ir_spi";
    idata->misc.mode = 0666;
    idata->misc.fops = &ir_spi_fops;
    idata->misc.parent = &spi->dev;
    spi_set_drvdata(spi, idata);
    ret = misc_register(&idata->misc);
    if (ret) {
        spi_set_drvdata(spi, NULL);
        goto fail;
    }
    return 0;
fail:
    kref_put(&idata->ref, ir_spi_free);
    return ret;
}

static void ir_spi_remove(struct spi_device *spi)
{
    struct ir_spi_data *idata = spi_get_drvdata(spi);
    misc_deregister(&idata->misc);
    mutex_lock(&idata->mutex);
    idata->spi = NULL;
    mutex_unlock(&idata->mutex);
    spi_set_drvdata(spi, NULL);
    kref_put(&idata->ref, ir_spi_free);
}

static const struct of_device_id ir_spi_of_match[] = {
    { .compatible = "ir-spi" },
    {},
};
MODULE_DEVICE_TABLE(of, ir_spi_of_match);
static struct spi_driver ir_spi_driver = {
    .probe = ir_spi_probe,
    .remove = ir_spi_remove,
    .driver = {
        .name = IR_SPI_DRIVER_NAME,
        .of_match_table = ir_spi_of_match,
    },
};
module_spi_driver(ir_spi_driver);
MODULE_AUTHOR("Andi Shyti <andi.shyti@samsung.com>");
MODULE_DESCRIPTION("SPI IR LED");
MODULE_LICENSE("GPL v2");
