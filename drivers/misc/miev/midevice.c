// SPDX-License-Identifier: GPL-2.0
/* Xiaomi MiSight transport, from the pinned Onyx source.
 * Myron integration fixes record bounds and initializes state before cdev_add.
 */
#define pr_fmt(fmt) "miev: " fmt

#include "midevice.h"
#include <linux/device.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/poll.h>

#define FIFO_SIZE (64 * 1024)
#define BUF_MAX_SIZE 4096
static char *record_buffer;

/* The mutex protects the length-prefixed FIFO and the shared scratch buffer. */
static int record_size_locked(void)
{
	int size;

	if (kfifo_out_peek(&miev_dev->fifo, &size, sizeof(size)) != sizeof(size) ||
	    size < 0 || size > BUF_MAX_SIZE ||
	    kfifo_len(&miev_dev->fifo) < sizeof(size) + size) {
		kfifo_reset(&miev_dev->fifo);
		return -EIO;
	}
	return size;
}

static int enqueue_locked(const char *buffer, int size)
{
	int drop;
	unsigned int record_size;

	while (kfifo_avail(&miev_dev->fifo) < sizeof(size) + size) {
		drop = record_size_locked();
		if (drop < 0)
			return drop;
		record_size = sizeof(drop) + drop;
		if (kfifo_out(&miev_dev->fifo, record_buffer, record_size) != record_size)
			return -EIO;
	}
	if (kfifo_in(&miev_dev->fifo, &size, sizeof(size)) != sizeof(size) ||
	    kfifo_in(&miev_dev->fifo, buffer, size) != size) {
		kfifo_reset(&miev_dev->fifo);
		return -EIO;
	}
	return size;
}

int write_kbuf(char __kernel *buffer, int size)
{
	int ret;

	if (!buffer || size < 0)
		return -EINVAL;
	if (size > BUF_MAX_SIZE)
		return -EMSGSIZE;
	if (!size)
		return 0;
	mutex_lock(&miev_dev->lock);
	ret = enqueue_locked(buffer, size);
	mutex_unlock(&miev_dev->lock);
	if (ret >= 0)
		wake_up_interruptible(&miev_dev->wait_queue);
	return ret;
}

static long miev_ioctl(struct file *filp, unsigned int cmd, unsigned long arg)
{
	if (_IOC_TYPE(cmd) != MIEV_IOC_MAGIC || _IOC_NR(cmd) > MIEV_IOC_MAXNR)
		return -EINVAL;
	if (!access_ok((void __user *)arg, _IOC_SIZE(cmd)))
		return -EFAULT;
	switch (cmd) {
	case MIEV_IOC_WRITE:
	case MIEV_IOC_READ:
	case MIEV_IOC_NONE:
		return 0;
	default:
		return -ENOTTY;
	}
}

static __poll_t miev_poll(struct file *filp, poll_table *wait)
{
	__poll_t mask = 0;

	poll_wait(filp, &miev_dev->wait_queue, wait);
	mutex_lock(&miev_dev->lock);
	if (!kfifo_is_empty(&miev_dev->fifo))
		mask |= EPOLLIN | EPOLLRDNORM;
	mutex_unlock(&miev_dev->lock);
	return mask;
}

static ssize_t miev_read(struct file *filp, char __user *ubuf, size_t size,
			 loff_t *offset)
{
	int ret = 0, payload_size;
	unsigned int total;

	if (!size)
		return 0;
	mutex_lock(&miev_dev->lock);
	if (kfifo_is_empty(&miev_dev->fifo))
		goto out;
	payload_size = record_size_locked();
	if (payload_size < 0) {
		ret = payload_size;
		goto out;
	}
	if (size < payload_size) {
		ret = -EMSGSIZE;
		goto out;
	}
	total = sizeof(payload_size) + payload_size;
	if (kfifo_out_peek(&miev_dev->fifo, record_buffer, total) != total) {
		ret = -EIO;
		goto out;
	}
	if (copy_to_user(ubuf, record_buffer + sizeof(payload_size), payload_size)) {
		ret = -EFAULT;
		goto out;
	}
	/* Do not consume on a short user buffer or a failed copy. */
	if (kfifo_out(&miev_dev->fifo, record_buffer, total) != total)
		ret = -EIO;
	else
		ret = payload_size;
out:
	mutex_unlock(&miev_dev->lock);
	return ret;
}

static ssize_t miev_write(struct file *filp, const char __user *ubuf,
			  size_t size, loff_t *offset)
{
	char *buffer;
	int ret;

	if (!size)
		return 0;
	/* Retain the existing userspace write truncation policy. */
	size = min_t(size_t, size, BUF_MAX_SIZE);
	buffer = memdup_user(ubuf, size);
	if (IS_ERR(buffer))
		return PTR_ERR(buffer);
	ret = write_kbuf(buffer, size);
	kfree(buffer);
	return ret;
}

static const struct file_operations miev_fops = {
	.owner = THIS_MODULE,
	.read = miev_read,
	.write = miev_write,
	.unlocked_ioctl = miev_ioctl,
	.poll = miev_poll,
};

static int __init miev_init_module(void)
{
	struct device *device;
	int ret;

	miev_dev = kzalloc(sizeof(*miev_dev), GFP_KERNEL);
	if (!miev_dev)
		return -ENOMEM;
	mutex_init(&miev_dev->lock);
	init_waitqueue_head(&miev_dev->wait_queue);
	record_buffer = kmalloc(BUF_MAX_SIZE + sizeof(int), GFP_KERNEL);
	if (!record_buffer) {
		ret = -ENOMEM;
		goto err_alloc;
	}
	ret = kfifo_alloc(&miev_dev->fifo, FIFO_SIZE, GFP_KERNEL);
	if (ret)
		goto err_buffer;
	miev_dev->dev_no = MKDEV(DEV_MAJOR, DEV_MINOR);
	ret = register_chrdev_region(miev_dev->dev_no, 1, DEV_NAME);
	if (ret < 0) {
		ret = alloc_chrdev_region(&miev_dev->dev_no, 0, 1, DEV_NAME);
		if (ret < 0)
			goto err_fifo;
	}
	cdev_init(&miev_dev->chrdev, &miev_fops);
	miev_dev->chrdev.owner = THIS_MODULE;
	ret = cdev_add(&miev_dev->chrdev, miev_dev->dev_no, 1);
	if (ret)
		goto err_region;
	miev_dev->my_class = class_create(DEV_NAME);
	if (IS_ERR(miev_dev->my_class)) {
		ret = PTR_ERR(miev_dev->my_class);
		goto err_cdev;
	}
	device = device_create(miev_dev->my_class, NULL, miev_dev->dev_no, NULL, DEV_NAME);
	if (IS_ERR(device)) {
		ret = PTR_ERR(device);
		goto err_class;
	}
	return 0;

err_class:
	class_destroy(miev_dev->my_class);
err_cdev:
	cdev_del(&miev_dev->chrdev);
err_region:
	unregister_chrdev_region(miev_dev->dev_no, 1);
err_fifo:
	kfifo_free(&miev_dev->fifo);
err_buffer:
	kfree(record_buffer);
err_alloc:
	kfree(miev_dev);
	miev_dev = NULL;
	return ret;
}

static void __exit miev_exit_module(void)
{
	device_destroy(miev_dev->my_class, miev_dev->dev_no);
	class_destroy(miev_dev->my_class);
	cdev_del(&miev_dev->chrdev);
	unregister_chrdev_region(miev_dev->dev_no, 1);
	kfifo_free(&miev_dev->fifo);
	kfree(record_buffer);
	kfree(miev_dev);
}

module_init(miev_init_module);
module_exit(miev_exit_module);
MODULE_AUTHOR("huangqibo <huangqibo@xiaomi.com>");
MODULE_DESCRIPTION("exception log transfer.");
MODULE_LICENSE("GPL");
