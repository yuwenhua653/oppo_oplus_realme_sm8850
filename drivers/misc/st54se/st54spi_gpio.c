// SPDX-License-Identifier: GPL-2.0
/*
 * ST54SPI GPIO driver
 * Copyright (C) 2021 ST Microelectronics S.A.
 * Copyright (c) 2022 Qualcomm Innovation Center, Inc. All rights reserved.
 *  * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 *
 **********************************************************************************/

/* Myron 6.12 adaptation. Preserve the stock probe-owned GPIO and multi-open ABI.
 * cdev's parent device owns lifetime across opens racing with removal. */
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/err.h>
#include <linux/fs.h>
#include <linux/gpio.h>
#include <linux/ioctl.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of_gpio.h>
#include <linux/platform_device.h>
#include <linux/slab.h>

#define ST54SPI_GPIO__MAGIC 0xEB
#define ST54SPI_GET_GPIO _IOW(ST54SPI_GPIO__MAGIC, 0x01, unsigned int)
#define ST54SPI_SET_GPIO _IOW(ST54SPI_GPIO__MAGIC, 0x02, unsigned int)

struct st54spi_gpio_device {
    dev_t devt;
    struct cdev cdev;
    struct device chardev;
    struct class *class;
    struct mutex lock;
    int gpio;
    bool requested;
    bool dead;
};

static void st54spi_gpio_free(struct device *dev)
{
    struct st54spi_gpio_device *s = container_of(dev,
            struct st54spi_gpio_device, chardev);
    mutex_destroy(&s->lock);
    kfree(s);
}

static long st54spi_gpio_dev_ioctl(struct file *file, unsigned int cmd,
        unsigned long arg)
{
    struct st54spi_gpio_device *s = file->private_data;
    int ret = 0;
    if (!s)
        return -ENODEV;
    mutex_lock(&s->lock);
    if (s->dead || !s->requested) {
        ret = -ENODEV;
        goto out;
    }
    switch (cmd) {
    case ST54SPI_GET_GPIO:
        ret = gpio_get_value(s->gpio);
        break;
    case ST54SPI_SET_GPIO:
        if (arg > 1)
            ret = -ENOIOCTLCMD;
        else if (arg == 1)
            gpio_set_value(s->gpio, 1); /* stock SET(0) acknowledges only */
        break;
    default:
        ret = -ENOIOCTLCMD;
        break;
    }
out:
    mutex_unlock(&s->lock);
    return ret;
}

static int st54spi_gpio_dev_open(struct inode *inode, struct file *file)
{
    struct st54spi_gpio_device *s = container_of(inode->i_cdev,
            struct st54spi_gpio_device, cdev);
    int ret;
    get_device(&s->chardev);
    mutex_lock(&s->lock);
    if (s->dead) {
        ret = -ENODEV;
        goto fail;
    }
    file->private_data = s;
    mutex_unlock(&s->lock);
    return 0;
fail:
    mutex_unlock(&s->lock);
    put_device(&s->chardev);
    return ret;
}

static int st54spi_gpio_dev_release(struct inode *inode, struct file *file)
{
    struct st54spi_gpio_device *s = file->private_data;
    file->private_data = NULL;
    put_device(&s->chardev);
    return 0;
}

static loff_t st54spi_gpio_llseek(struct file *file, loff_t offset, int whence)
{
    return -ESPIPE;
}

static const struct file_operations st54spi_gpio_dev_fops = {
    .owner = THIS_MODULE,
    .llseek = st54spi_gpio_llseek,
    .open = st54spi_gpio_dev_open,
    .release = st54spi_gpio_dev_release,
    .unlocked_ioctl = st54spi_gpio_dev_ioctl,
#ifdef CONFIG_COMPAT
    .compat_ioctl = st54spi_gpio_dev_ioctl, /* arg is a scalar, not a pointer */
#endif
};

static int st54spi_gpio_probe(struct platform_device *pdev)
{
    struct st54spi_gpio_device *s;
    int gpio, ret;
    if (!pdev->dev.of_node)
        return -ENODEV;
    gpio = of_get_named_gpio(pdev->dev.of_node, "gpio-power_nreset", 0);
    if (gpio < 0)
        return gpio; /* preserve -EPROBE_DEFER */
    if (!gpio_is_valid(gpio))
        return -EINVAL;
    s = kzalloc(sizeof(*s), GFP_KERNEL);
    if (!s)
        return -ENOMEM;
    s->gpio = gpio;
    mutex_init(&s->lock);
    device_initialize(&s->chardev);
    s->chardev.release = st54spi_gpio_free;
    s->chardev.parent = &pdev->dev;
    ret = gpio_request(s->gpio, "gpio-power_nreset");
    if (ret) {
        ret = -EFAULT;
        goto put;
    }
    s->requested = true;
    ret = gpio_direction_output(s->gpio, 1); /* stock probe leaves nRESET high */
    if (ret) {
        ret = -EFAULT;
        goto free_gpio;
    }
    ret = alloc_chrdev_region(&s->devt, 0, 1, "st54spi_gpio");
    if (ret)
        goto free_gpio;
    s->class = class_create("st54spi_gpio");
    if (IS_ERR(s->class)) {
        ret = PTR_ERR(s->class);
        goto unregister;
    }
    s->chardev.class = s->class;
    s->chardev.devt = s->devt;
    ret = dev_set_name(&s->chardev, "st54spi_gpio");
    if (ret)
        goto destroy;
    dev_set_drvdata(&s->chardev, s);
    cdev_init(&s->cdev, &st54spi_gpio_dev_fops);
    s->cdev.owner = THIS_MODULE;
    /* cdev_device_add sets the cdev parent to chardev's kobject; this
     * retains s until an in-progress open can take its explicit reference. */
    ret = cdev_device_add(&s->cdev, &s->chardev);
    if (ret) {
        /* An open can occur while cdev_device_add is publishing cdev,
         * even if device_add subsequently fails. */
        mutex_lock(&s->lock);
        s->dead = true;
        if (s->requested) {
            gpio_free(s->gpio);
            s->requested = false;
        }
        mutex_unlock(&s->lock);
        goto destroy;
    }
    platform_set_drvdata(pdev, s);
    return 0;
destroy:
    class_destroy(s->class);
unregister:
    unregister_chrdev_region(s->devt, 1);
free_gpio:
    if (s->requested) {
        gpio_free(s->gpio);
        s->requested = false;
    }
put:
    put_device(&s->chardev);
    return ret;
}

static void st54spi_gpio_remove(struct platform_device *pdev)
{
    struct st54spi_gpio_device *s = platform_get_drvdata(pdev);
    mutex_lock(&s->lock);
    s->dead = true;
    if (s->requested) {
        gpio_free(s->gpio);
        s->requested = false;
    }
    mutex_unlock(&s->lock);
    cdev_device_del(&s->cdev, &s->chardev);
    class_destroy(s->class);
    unregister_chrdev_region(s->devt, 1);
    platform_set_drvdata(pdev, NULL);
    put_device(&s->chardev);
}

static const struct of_device_id st54spi_gpio_of_match[] = {
    { .compatible = "st,st54spi_gpio" }, {},
};
MODULE_DEVICE_TABLE(of, st54spi_gpio_of_match);
static struct platform_driver st54spi_gpio_driver = {
    .driver = {
        .name = "st54spi_gpio",
        .of_match_table = st54spi_gpio_of_match,
    },
    .probe = st54spi_gpio_probe,
    .remove = st54spi_gpio_remove,
};
module_platform_driver(st54spi_gpio_driver);
MODULE_AUTHOR("STMicroelectronics");
MODULE_DESCRIPTION("ST54SPI GPIO driver");
MODULE_LICENSE("GPL v2");
MODULE_ALIAS("st54spi_gpio");
