// SPDX-License-Identifier: GPL-2.0-only
/* Myron logical brightness compatibility; no hardware/DCS operations.
 * Event ABI: MiCode display-drivers 6def61b29a39710078287416afd3b62f43729c37.
 * Only the version query and primary BRIGHTNESS_CLONE events are implemented.
 * All other display feature operations fail with -ENOTTY/-EOPNOTSUPP.
 */
#include <linux/compat.h>
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/kref.h>
#include <linux/kernel.h>
#include <linux/list.h>
#include <linux/cdev.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/poll.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include "dsi_display.h"
#include "dsi_panel.h"
#include "myron_mi_clone_state.h"

#define MYRON_CLONE_CLIENTS 32U
struct myron_clone_request { u32 flag, disp_id, type; };
struct myron_clone_version { u32 flag, disp_id, version; };
#define MYRON_CLONE_VERSION _IOR('D', 0, struct myron_clone_version)
#define MYRON_CLONE_REGISTER _IOW('D', 7, struct myron_clone_request)
#define MYRON_CLONE_DEREGISTER _IOW('D', 8, struct myron_clone_request)

struct myron_clone {
	struct kref ref;
	struct mutex lock;
	struct list_head clients;
	struct cdev cdev;
	struct device feature;
	dev_t devt;
	struct class *class;
	struct device *device;
	struct dsi_display *owner; /* identity only; callbacks never dereference it */
	u32 maximum, value, client_count;
	bool active;
};
struct myron_clone_client {
	struct list_head link;
	struct myron_clone *state;
	wait_queue_head_t wait;
	struct myron_clone_queue queue;
	bool subscribed;
};
static DEFINE_MUTEX(myron_clone_owner_lock);
static struct myron_clone *myron_clone_owner;

static void myron_clone_free(struct kref *ref)
{
	struct myron_clone *state = container_of(ref, struct myron_clone, ref);

	kfree(state);
}

static void myron_clone_feature_release(struct device *dev)
{
	struct myron_clone *state = container_of(dev, struct myron_clone, feature);

	kref_put(&state->ref, myron_clone_free);
}

static ssize_t max_brightness_clone_show(struct device *dev,
		struct device_attribute *attr, char *buf)
{
	struct myron_clone *state = dev_get_drvdata(dev);
	ssize_t rc;

	mutex_lock(&state->lock);
	rc = state->active ? sysfs_emit(buf, "%u\n", state->maximum) : -ENODEV;
	mutex_unlock(&state->lock);
	return rc;
}
static ssize_t brightness_clone_show(struct device *dev,
		struct device_attribute *attr, char *buf)
{
	struct myron_clone *state = dev_get_drvdata(dev);
	ssize_t rc;

	mutex_lock(&state->lock);
	rc = state->active ? sysfs_emit(buf, "%u\n", state->value) : -ENODEV;
	mutex_unlock(&state->lock);
	return rc;
}
static ssize_t brightness_clone_store(struct device *dev,
		struct device_attribute *attr, const char *buf, size_t count)
{
	struct myron_clone *state = dev_get_drvdata(dev);
	struct myron_clone_client *client;
	u32 value;
	int rc = kstrtou32(buf, 10, &value);

	if (rc)
		return rc;
	mutex_lock(&state->lock);
	if (!state->active) {
		mutex_unlock(&state->lock);
		return -ENODEV;
	}
	state->value = myron_clone_bound(value, state->maximum);
	list_for_each_entry(client, &state->clients, link) {
		if (client->subscribed && myron_clone_push(&client->queue, state->value))
			wake_up_interruptible(&client->wait);
	}
	mutex_unlock(&state->lock);
	/* Cached logical value only: existing DRM backlight remains sole writer. */
	return count;
}
static DEVICE_ATTR_RO(max_brightness_clone);
static DEVICE_ATTR_RW(brightness_clone);
static struct attribute *myron_clone_attrs[] = {
	&dev_attr_max_brightness_clone.attr,
	&dev_attr_brightness_clone.attr,
	NULL,
};
ATTRIBUTE_GROUPS(myron_clone);

static int myron_clone_open(struct inode *inode, struct file *file)
{
	struct myron_clone *state = container_of(inode->i_cdev, struct myron_clone, cdev);
	struct myron_clone_client *client;
	int rc = 0;

	client = kzalloc(sizeof(*client), GFP_KERNEL);
	if (!client)
		return -ENOMEM;
	init_waitqueue_head(&client->wait);
	client->state = state;
	mutex_lock(&state->lock);
	if (!state->active)
		rc = -ENODEV;
	else if (state->client_count == MYRON_CLONE_CLIENTS)
		rc = -EMFILE;
	else {
		kref_get(&state->ref);
		state->client_count++;
		list_add_tail(&client->link, &state->clients);
		file->private_data = client;
	}
	mutex_unlock(&state->lock);
	if (rc)
		kfree(client);
	return rc;
}
static int myron_clone_release(struct inode *inode, struct file *file)
{
	struct myron_clone_client *client = file->private_data;
	struct myron_clone *state = client->state;

	mutex_lock(&state->lock);
	list_del(&client->link);
	state->client_count--;
	mutex_unlock(&state->lock);
	kfree(client);
	kref_put(&state->ref, myron_clone_free);
	return 0;
}
static long myron_clone_ioctl(struct file *file, unsigned int cmd,
		unsigned long arg)
{
	struct myron_clone_client *client = file->private_data;
	struct myron_clone *state = client->state;
	struct myron_clone_request req;
	struct myron_clone_version version = { 0, 0, 0x100 };
	int rc = 0;

	if (cmd != MYRON_CLONE_VERSION && cmd != MYRON_CLONE_REGISTER &&
			cmd != MYRON_CLONE_DEREGISTER)
		return -ENOTTY;
	if (cmd != MYRON_CLONE_VERSION &&
			copy_from_user(&req, (void __user *)arg, sizeof(req)))
		return -EFAULT;
	mutex_lock(&state->lock);
	if (!state->active)
		rc = -ENODEV;
	else if (cmd == MYRON_CLONE_VERSION) {
		/* Protocol version only; no claim that other feature ioctls exist. */
		if (copy_to_user((void __user *)arg, &version, sizeof(version)))
			rc = -EFAULT;
	} else if (req.disp_id != 0 || req.type != MYRON_CLONE_EVENT)
		rc = -EOPNOTSUPP;
	else
		client->subscribed = cmd == MYRON_CLONE_REGISTER;
	mutex_unlock(&state->lock);
	return rc;
}
#ifdef CONFIG_COMPAT
static long myron_clone_compat_ioctl(struct file *file, unsigned int cmd,
		unsigned long arg)
{
	return myron_clone_ioctl(file, cmd, (unsigned long)compat_ptr(arg));
}
#endif
static __poll_t myron_clone_poll(struct file *file, poll_table *wait)
{
	struct myron_clone_client *client = file->private_data;
	struct myron_clone *state = client->state;
	__poll_t mask = 0;

	poll_wait(file, &client->wait, wait);
	mutex_lock(&state->lock);
	if (!state->active)
		mask = EPOLLHUP | EPOLLERR;
	else if (client->queue.count)
		mask = EPOLLIN | EPOLLRDNORM;
	mutex_unlock(&state->lock);
	return mask;
}
static ssize_t myron_clone_read(struct file *file, char __user *buf,
		size_t count, loff_t *offset)
{
	struct myron_clone_client *client = file->private_data;
	struct myron_clone *state = client->state;
	struct myron_clone_queue *q = &client->queue;
	int rc;

	if (!count)
		return 0;
	if (count < sizeof(struct myron_clone_event))
		return -EINVAL;
	for (;;) {
		rc = mutex_lock_interruptible(&state->lock);
		if (rc)
			return rc;
		if (!state->active) {
			rc = -ENODEV;
			break;
		}
		if (q->count) {
			if (copy_to_user(buf, &q->events[q->head], sizeof(q->events[0]))) {
				rc = -EFAULT;
				break;
			}
			q->head = (q->head + 1) % MYRON_CLONE_QUEUE;
			q->count--;
			rc = sizeof(q->events[0]);
			break;
		}
		mutex_unlock(&state->lock);
		if (file->f_flags & O_NONBLOCK)
			return -EAGAIN;
		rc = wait_event_interruptible(client->wait,
			!READ_ONCE(state->active) || READ_ONCE(q->count));
		if (rc)
			return rc;
	}
	mutex_unlock(&state->lock);
	return rc;
}
static const struct file_operations myron_clone_fops = {
	.owner = THIS_MODULE,
	.open = myron_clone_open,
	.release = myron_clone_release,
	.unlocked_ioctl = myron_clone_ioctl,
#ifdef CONFIG_COMPAT
	.compat_ioctl = myron_clone_compat_ioctl,
#endif
	.poll = myron_clone_poll,
	.read = myron_clone_read,
	.llseek = NULL, /* Event queue: reject seeking with -ESPIPE. */
};

int myron_mi_clone_attach(struct dsi_display *display)
{
	struct myron_clone *state;
	struct device_node *node;
	u32 maximum = MYRON_CLONE_DEFAULT;
	int rc;

	if (!display || !display->panel || !display->panel_node ||
			strcmp(display->display_type, "primary"))
		return -ENODEV;
	node = display->panel->panel_of_node;
	if (node != display->panel_node || !display->panel->name ||
			strcmp(display->panel->name, "xiaomi p11u 42 0d 0a cmd mode dsc dsi panel"))
		return -ENODEV;
	if (of_find_property(node, "mi,max-brightness-clone", NULL)) {
		if (of_property_count_u32_elems(node, "mi,max-brightness-clone") != 1)
			return -EINVAL;
		rc = of_property_read_u32(node, "mi,max-brightness-clone", &maximum);
		if (rc)
			return rc;
	}
	if (!myron_clone_max_valid(maximum))
		return -ERANGE;
	mutex_lock(&myron_clone_owner_lock);
	if (myron_clone_owner) {
		rc = -EBUSY;
		goto out;
	}
	state = kzalloc(sizeof(*state), GFP_KERNEL);
	if (!state) {
		rc = -ENOMEM;
		goto out;
	}
	kref_init(&state->ref);
	mutex_init(&state->lock);
	INIT_LIST_HEAD(&state->clients);
	state->owner = display;
	state->maximum = maximum;
	state->class = class_create("mi_display");
	if (IS_ERR(state->class)) {
		rc = PTR_ERR(state->class);
		goto free_state;
	}
	rc = alloc_chrdev_region(&state->devt, 0, 1, "disp_feature");
	if (rc)
		goto destroy_class;
	device_initialize(&state->feature);
	kref_get(&state->ref); /* feature/cdev lifetime can outlive detach */
	state->feature.release = myron_clone_feature_release;
	state->feature.class = state->class;
	state->feature.devt = state->devt;
	/* Match vendor topology: virtual mi_display/disp_feature parent. */
	rc = dev_set_name(&state->feature, "disp_feature");
	if (rc)
		goto put_feature;
	cdev_init(&state->cdev, &myron_clone_fops);
	state->cdev.owner = THIS_MODULE;
	rc = cdev_device_add(&state->cdev, &state->feature);
	if (rc)
		goto put_feature;
	state->device = device_create_with_groups(state->class, &state->feature,
			0, state, myron_clone_groups, "disp-DSI-0");
	if (IS_ERR(state->device)) {
		rc = PTR_ERR(state->device);
		goto remove_feature;
	}
	mutex_lock(&state->lock);
	state->active = true;
	mutex_unlock(&state->lock);
	myron_clone_owner = state;
	pr_info("MYRON_R78 clone attached max=%u domain=logical panel=%pOF\n", maximum, node);
	goto out;
remove_feature:
	cdev_device_del(&state->cdev, &state->feature);
put_feature:
	put_device(&state->feature);
	unregister_chrdev_region(state->devt, 1);
destroy_class:
	class_destroy(state->class);
free_state:
	kref_put(&state->ref, myron_clone_free);
out:
	mutex_unlock(&myron_clone_owner_lock);
	return rc;
}

void myron_mi_clone_detach(struct dsi_display *display)
{
	struct myron_clone *state;
	struct myron_clone_client *client;

	mutex_lock(&myron_clone_owner_lock);
	state = myron_clone_owner;
	if (!state || state->owner != display)
		goto out;
	mutex_lock(&state->lock);
	state->active = false;
	list_for_each_entry(client, &state->clients, link)
		wake_up_interruptible(&client->wait);
	mutex_unlock(&state->lock);
	/* cdev_device_del stops new opens; sysfs removal drains callbacks.
	 * The cdev holds its parent device: in-flight opens retain state even
	 * before open() takes a client kref. Existing FDs see ENODEV/HUP.
	 */
	device_unregister(state->device);
	cdev_device_del(&state->cdev, &state->feature);
	unregister_chrdev_region(state->devt, 1);
	put_device(&state->feature);
	class_destroy(state->class);
	myron_clone_owner = NULL;
	kref_put(&state->ref, myron_clone_free);
out:
	mutex_unlock(&myron_clone_owner_lock);
}
