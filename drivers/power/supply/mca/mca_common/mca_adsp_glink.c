#include <linux/module.h>
#include <linux/init.h>
#include <linux/slab.h>
#include <linux/device.h>
#include <linux/platform_device.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>
#include <linux/completion.h>
#include <linux/workqueue.h>
#include <linux/list.h>
#include <linux/string.h>
#include <linux/err.h>
#include <linux/mod_devicetable.h>
#include <linux/of_device.h>
#include <linux/soc/qcom/qti_pmic_glink.h>
#include <mca/common/mca_log.h>
#include <mca/common/mca_adsp_glink.h>

#ifndef MCA_LOG_TAG
#define MCA_LOG_TAG "mca_adsp_glink"
#endif

#define MCA_ADSP_GLINK_OWNER 0x800A
#define MCA_ADSP_GLINK_QBG_OWNER 0x8009
#define MCA_ADSP_GLINK_MSG_REQ 1 /* hdr.type: request/response */
#define MCA_ADSP_GLINK_MSG_NOTIFY 2 /* hdr.type: async notification */
#define MCA_ADSP_GLINK_OPCODE_READ 1
#define MCA_ADSP_GLINK_OPCODE_WRITE 2
#define MCA_ADSP_PROP_DATA_LEN 256
#define MCA_ADSP_GLINK_TIMEOUT_MS 250

struct mca_adsp_glink_req_msg {
	struct pmic_glink_hdr hdr;
	u32 property_id;
	u32 seq;
	u8 data[MCA_ADSP_PROP_DATA_LEN];
} __packed;

struct mca_adsp_glink_resp_msg {
	struct pmic_glink_hdr hdr;
	u32 property_id;
	u32 retcode;
	u32 seq;
	u8 data[MCA_ADSP_PROP_DATA_LEN];
} __packed;

struct mca_adsp_glink_notify_msg {
	struct pmic_glink_hdr hdr;
	u32 property_id;
	u8 data[MCA_ADSP_PROP_DATA_LEN];
} __packed;

struct mca_adsp_glink_dev {
	struct device *dev;
	struct pmic_glink_client *client;
	struct mutex rw_lock;
	struct completion ack;
	spinlock_t pending_lock;
	bool pending;
	u32 cur_owner;
	u32 cur_opcode;
	u32 cur_seq;
	int glink_state;
	struct work_struct sync_work;
	u32 cur_property_id;
	int retcode;
	u32 remote_retcode;
	u32 seq;
	u8 read_buf[MCA_ADSP_PROP_DATA_LEN];
};

struct mca_adsp_ops_node {
	struct list_head node;
	void *priv;
	struct mca_adsp_glink_ops *ops;
};

static struct mca_adsp_glink_dev *g_mca_adsp_glink;
static LIST_HEAD(g_mca_adsp_glink_ops_head);
static LIST_HEAD(g_mca_adsp_glink_qbg_ops_head);

/* rw_lock serializes senders; pending_lock also covers the RX callback. */
static int mca_adsp_glink_begin_request(struct mca_adsp_glink_dev *mca,
				       const struct mca_adsp_glink_req_msg *msg)
{
	unsigned long flags;
	int ret = 0;

	spin_lock_irqsave(&mca->pending_lock, flags);
	if (mca->glink_state != PMIC_GLINK_STATE_UP) {
		ret = -ENOTCONN;
		goto out;
	}
	reinit_completion(&mca->ack);
	mca->retcode = 0;
	mca->remote_retcode = 0;
	memset(mca->read_buf, 0, sizeof(mca->read_buf));
	mca->cur_property_id = msg->property_id;
	mca->cur_owner = msg->hdr.owner;
	mca->cur_opcode = msg->hdr.opcode;
	mca->cur_seq = msg->seq;
	mca->pending = true;
out:
	spin_unlock_irqrestore(&mca->pending_lock, flags);
	return ret;
}

static void mca_adsp_glink_end_request(struct mca_adsp_glink_dev *mca)
{
	unsigned long flags;

	spin_lock_irqsave(&mca->pending_lock, flags);
	mca->pending = false;
	mca->cur_property_id = 0xffffffff;
	spin_unlock_irqrestore(&mca->pending_lock, flags);
}

int mca_adsp_glink_write_prop(int prop_id, void *value, size_t size)
{
	struct mca_adsp_glink_dev *mca = g_mca_adsp_glink;
	struct mca_adsp_glink_req_msg msg = { 0 };
	int ret = -1;

	if (!value || size >= MCA_ADSP_PROP_DATA_LEN || !mca)
		return -1;

	mutex_lock(&mca->rw_lock);
	mca->seq++;
	msg.hdr.owner = MCA_ADSP_GLINK_OWNER;
	msg.hdr.type = MCA_ADSP_GLINK_MSG_REQ;
	msg.hdr.opcode = MCA_ADSP_GLINK_OPCODE_WRITE;
	msg.property_id = prop_id;
	msg.seq = mca->seq;
	memcpy(msg.data, value, size);

	ret = mca_adsp_glink_begin_request(mca, &msg);
	if (ret) {
		mca_log_err("glink state is down\n");
		goto out;
	}
	ret = pmic_glink_write(mca->client, &msg, sizeof(msg));
	if (ret == 0) {
		if (wait_for_completion_timeout(
			    &mca->ack,
			    msecs_to_jiffies(MCA_ADSP_GLINK_TIMEOUT_MS)) == 0) {
			mca_log_err("timed out sending message, prop_id: %d\n",
				    mca->cur_property_id);
			ret = -ETIMEDOUT;
		} else {
			ret = mca->retcode;
		}
	}
out:
	mca_adsp_glink_end_request(mca);
	mutex_unlock(&mca->rw_lock);
	return ret;
}
EXPORT_SYMBOL(mca_adsp_glink_write_prop);

int mca_adsp_glink_read_prop(int prop_id, void *value, size_t size)
{
	struct mca_adsp_glink_dev *mca = g_mca_adsp_glink;
	struct mca_adsp_glink_req_msg msg = { 0 };
	int ret = -1;

	if (!value || size >= MCA_ADSP_PROP_DATA_LEN || !mca)
		return -1;

	mutex_lock(&mca->rw_lock);
	mca->seq++;
	msg.hdr.owner = MCA_ADSP_GLINK_OWNER;
	msg.hdr.type = MCA_ADSP_GLINK_MSG_REQ;
	msg.hdr.opcode = MCA_ADSP_GLINK_OPCODE_READ;
	msg.property_id = prop_id;
	msg.seq = mca->seq;

	ret = mca_adsp_glink_begin_request(mca, &msg);
	if (ret) {
		mca_log_err("glink state is down\n");
		goto out;
	}
	ret = pmic_glink_write(mca->client, &msg, sizeof(msg));
	if (ret == 0) {
		if (wait_for_completion_timeout(
			    &mca->ack,
			    msecs_to_jiffies(MCA_ADSP_GLINK_TIMEOUT_MS)) == 0) {
			mca_log_err("timed out sending message, prop_id: %d\n",
				    mca->cur_property_id);
			ret = -ETIMEDOUT;
		} else {
			ret = mca->retcode;
			if (ret == 0) {
				memcpy(value, mca->read_buf, size);
				memset(mca->read_buf, 0,
				       MCA_ADSP_PROP_DATA_LEN);
			}
		}
	}
out:
	mca_adsp_glink_end_request(mca);
	mutex_unlock(&mca->rw_lock);
	return ret;
}
EXPORT_SYMBOL(mca_adsp_glink_read_prop);

int mca_adsp_glink_resister_ops(struct mca_adsp_glink_ops *ops, void *priv)
{
	struct mca_adsp_ops_node *n;

	n = kzalloc(sizeof(*n), GFP_KERNEL);
	if (!n)
		return -ENOMEM;

	n->ops = ops;
	n->priv = priv;
	list_add(&n->node, &g_mca_adsp_glink_ops_head);
	return 0;
}
EXPORT_SYMBOL(mca_adsp_glink_resister_ops);

int mca_adsp_glink_qbg_write_prop(int prop_id, void *value, size_t size)
{
	struct mca_adsp_glink_dev *mca = g_mca_adsp_glink;
	struct mca_adsp_glink_req_msg msg = { 0 };
	int ret = -1;

	if (!value || size >= MCA_ADSP_PROP_DATA_LEN || !mca)
		return -1;

	mutex_lock(&mca->rw_lock);
	mca->seq++;
	msg.hdr.owner = MCA_ADSP_GLINK_QBG_OWNER;
	msg.hdr.type = MCA_ADSP_GLINK_MSG_REQ;
	msg.hdr.opcode = MCA_ADSP_GLINK_OPCODE_WRITE;
	msg.property_id = prop_id;
	msg.seq = mca->seq;
	memcpy(msg.data, value, size);

	ret = mca_adsp_glink_begin_request(mca, &msg);
	if (ret) {
		mca_log_err("glink state is down\n");
		goto out;
	}
	ret = pmic_glink_write(mca->client, &msg, sizeof(msg));
	if (ret == 0) {
		if (wait_for_completion_timeout(
			    &mca->ack,
			    msecs_to_jiffies(MCA_ADSP_GLINK_TIMEOUT_MS)) == 0) {
			mca_log_err("timed out sending message, prop_id: %d\n",
				    mca->cur_property_id);
			ret = -ETIMEDOUT;
		} else {
			ret = mca->retcode;
		}
	}
out:
	mca_adsp_glink_end_request(mca);
	mutex_unlock(&mca->rw_lock);
	return ret;
}
EXPORT_SYMBOL(mca_adsp_glink_qbg_write_prop);

int mca_adsp_glink_qbg_read_prop(int prop_id, void *value, size_t size)
{
	struct mca_adsp_glink_dev *mca = g_mca_adsp_glink;
	struct mca_adsp_glink_req_msg msg = { 0 };
	int ret = -1;

	if (!value || size >= MCA_ADSP_PROP_DATA_LEN || !mca)
		return -1;

	mutex_lock(&mca->rw_lock);
	mca->seq++;
	msg.hdr.owner = MCA_ADSP_GLINK_QBG_OWNER;
	msg.hdr.type = MCA_ADSP_GLINK_MSG_REQ;
	msg.hdr.opcode = MCA_ADSP_GLINK_OPCODE_READ;
	msg.property_id = prop_id;
	msg.seq = mca->seq;

	ret = mca_adsp_glink_begin_request(mca, &msg);
	if (ret) {
		mca_log_err("glink state is down\n");
		goto out;
	}
	ret = pmic_glink_write(mca->client, &msg, sizeof(msg));
	if (ret == 0) {
		if (wait_for_completion_timeout(
			    &mca->ack,
			    msecs_to_jiffies(MCA_ADSP_GLINK_TIMEOUT_MS)) == 0) {
			mca_log_err("timed out sending message, prop_id: %d\n",
				    mca->cur_property_id);
			ret = -ETIMEDOUT;
		} else {
			ret = mca->retcode;
			if (ret == 0) {
				memcpy(value, mca->read_buf, size);
				memset(mca->read_buf, 0,
				       MCA_ADSP_PROP_DATA_LEN);
			}
		}
	}
out:
	mca_adsp_glink_end_request(mca);
	mutex_unlock(&mca->rw_lock);
	return ret;
}
EXPORT_SYMBOL(mca_adsp_glink_qbg_read_prop);

int mca_adsp_glink_qbg_resister_ops(struct mca_adsp_glink_ops *ops, void *priv)
{
	struct mca_adsp_ops_node *n;

	n = kzalloc(sizeof(*n), GFP_KERNEL);
	if (!n)
		return -ENOMEM;

	n->ops = ops;
	n->priv = priv;
	list_add(&n->node, &g_mca_adsp_glink_qbg_ops_head);
	return 0;
}
EXPORT_SYMBOL(mca_adsp_glink_qbg_resister_ops);

static int
mca_adsp_glink_handle_notification(struct mca_adsp_glink_dev *mca,
				   struct mca_adsp_glink_notify_msg *msg)
{
	struct mca_adsp_ops_node *n;
	struct list_head *head;

	head = (msg->hdr.owner == MCA_ADSP_GLINK_QBG_OWNER) ?
		       &g_mca_adsp_glink_qbg_ops_head :
		       &g_mca_adsp_glink_ops_head;

	mca_log_info("mca_adsp receive notification %d, owner %d\n",
		     msg->property_id, msg->hdr.owner);
	list_for_each_entry(n, head, node) {
		if (n->ops && n->ops->notification)
			n->ops->notification(msg->property_id, msg->data,
					     MCA_ADSP_PROP_DATA_LEN, n->priv);
	}
	return 0;
}

static int mca_adsp_glink_handle_message(struct mca_adsp_glink_dev *mca,
					 struct mca_adsp_glink_resp_msg *msg,
					 size_t len)
{
	unsigned long flags;

	/* Accept only the fixed response format defined above. */
	if (len != sizeof(*msg))
		return 0;

	spin_lock_irqsave(&mca->pending_lock, flags);
	if (!mca->pending || msg->hdr.type != MCA_ADSP_GLINK_MSG_REQ ||
	    msg->hdr.owner != mca->cur_owner ||
	    msg->hdr.opcode != mca->cur_opcode ||
	    msg->property_id != mca->cur_property_id ||
	    msg->seq != mca->cur_seq)
		goto out;

	/* The wire status is unsigned; only zero denotes a successful reply. */
	mca->remote_retcode = msg->retcode;
	mca->retcode = msg->retcode ? -EREMOTEIO : 0;
	if (!msg->retcode && msg->hdr.opcode == MCA_ADSP_GLINK_OPCODE_READ)
		memcpy(mca->read_buf, msg->data, MCA_ADSP_PROP_DATA_LEN);
	mca->pending = false;
	complete(&mca->ack);
out:
	spin_unlock_irqrestore(&mca->pending_lock, flags);
	return 0;
}

static int mca_adsp_glink_callback(void *priv, void *data, size_t len)
{
	struct mca_adsp_glink_dev *mca = priv;
	struct pmic_glink_hdr hdr;

	if (!mca || !data || len < sizeof(hdr))
		return 0;

	memcpy(&hdr, data, sizeof(hdr));
	if (hdr.owner != MCA_ADSP_GLINK_OWNER &&
	    hdr.owner != MCA_ADSP_GLINK_QBG_OWNER)
		return 0;

	if (hdr.type == MCA_ADSP_GLINK_MSG_NOTIFY) {
		if (len != sizeof(struct mca_adsp_glink_notify_msg))
			return 0;
		/* No notification opcode value is defined by this wire contract. */
		return mca_adsp_glink_handle_notification(mca, data);
	}

	if (hdr.type != MCA_ADSP_GLINK_MSG_REQ ||
	    (hdr.opcode != MCA_ADSP_GLINK_OPCODE_READ &&
	     hdr.opcode != MCA_ADSP_GLINK_OPCODE_WRITE))
		return 0;

	return mca_adsp_glink_handle_message(mca, data, len);
}

static void mca_adsp_glink_sync_work(struct work_struct *work)
{
	struct mca_adsp_ops_node *n;

	list_for_each_entry(n, &g_mca_adsp_glink_ops_head, node) {
		if (n->ops && n->ops->glink_state_up)
			n->ops->glink_state_up(n->priv);
	}
	list_for_each_entry(n, &g_mca_adsp_glink_qbg_ops_head, node) {
		if (n->ops && n->ops->glink_state_up)
			n->ops->glink_state_up(n->priv);
	}
}

static void mca_adsp_glink_state_cb(void *priv, enum pmic_glink_state state)
{
	struct mca_adsp_glink_dev *mca = priv;
	struct mca_adsp_ops_node *n;
	unsigned long flags;

	/* Serialize link loss with request admission and response completion. */
	spin_lock_irqsave(&mca->pending_lock, flags);
	mca->glink_state = state;
	if (state != PMIC_GLINK_STATE_UP && mca->pending) {
		mca->pending = false;
		mca->retcode = -ENOTCONN;
		complete(&mca->ack);
	}
	spin_unlock_irqrestore(&mca->pending_lock, flags);
	if (state == PMIC_GLINK_STATE_UP) {
		queue_work(system_wq, &mca->sync_work);
	} else {
		list_for_each_entry(n, &g_mca_adsp_glink_ops_head, node) {
			if (n->ops && n->ops->glink_state_down)
				n->ops->glink_state_down(n->priv);
		}
		list_for_each_entry(n, &g_mca_adsp_glink_qbg_ops_head, node) {
			if (n->ops && n->ops->glink_state_down)
				n->ops->glink_state_down(n->priv);
		}
	}
}

static int mca_adsp_glink_probe(struct platform_device *pdev)
{
	struct mca_adsp_glink_dev *mca;
	struct pmic_glink_client_data client_data = { 0 };
	int ret;

	mca = devm_kzalloc(&pdev->dev, sizeof(*mca), GFP_KERNEL);
	if (!mca)
		return -ENOMEM;

	mca->dev = &pdev->dev;
	mca->cur_property_id = 0xffffffff;
	mutex_init(&mca->rw_lock);
	spin_lock_init(&mca->pending_lock);
	init_completion(&mca->ack);
	mca->glink_state = 1;
	INIT_WORK(&mca->sync_work, mca_adsp_glink_sync_work);

	client_data.name = "mca_adap_glink";
	client_data.id = MCA_ADSP_GLINK_OWNER;
	client_data.priv = mca;
	client_data.msg_cb = mca_adsp_glink_callback;
	client_data.state_cb = mca_adsp_glink_state_cb;

	mca->client = pmic_glink_register_client(&pdev->dev, &client_data);
	if (IS_ERR(mca->client)) {
		ret = PTR_ERR(mca->client);
		if (ret == -EPROBE_DEFER)
			return ret;
		mca_log_err("Error in registering with pmic_glink %d\n", ret);
		return ret;
	}

	platform_set_drvdata(pdev, mca);
	g_mca_adsp_glink = mca;
	mca_log_err("probe ok\n");
	return 0;
}

static void mca_adsp_glink_remove(struct platform_device *pdev)
{
	return;
}

static const struct of_device_id mca_adsp_match_table[] = {
	{ .compatible = "mca,adsp_glink" },
	{},
};

static struct platform_driver mca_adsp_driver = {
	.driver = {
		.name = "mca_adsp_glink",
		.of_match_table = mca_adsp_match_table,
	},
	.probe = mca_adsp_glink_probe,
	.remove = mca_adsp_glink_remove,
};
module_platform_driver(mca_adsp_driver);

MODULE_DESCRIPTION("mca glink driver");
MODULE_AUTHOR("liyuze1@xiaomi.com");
MODULE_LICENSE("GPL v2");
