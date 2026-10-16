/* R61 diagnostic qualification: raw reads only, never a battery provider.
 * This parameter is immutable after module load and deliberately defaults off.
 * A future installation must explicitly select the diagnostic-only mode.
 */
static bool myron_readonly_diag;
module_param(myron_readonly_diag, bool, 0444);
MODULE_PARM_DESC(myron_readonly_diag,
	"Read-only raw gauge diagnostics; no charging policy or MCA registration");

static int bq_myron_diag_read(struct i2c_client *client, unsigned int index)
{
	/* The same register map used by this driver's real gauge read paths.
	 * SMBus command-byte selection is part of the read transaction; this
	 * path never sends a write-word, MAC/configuration or programming command.
	 */
	return i2c_smbus_read_word_data(client, bq27z561_regs[index]);
}

static ssize_t raw_soc_show(struct device *dev,
			   struct device_attribute *attr, char *buf)
{
	int ret = bq_myron_diag_read(to_i2c_client(dev), BQ_FG_REG_SOC);

	if (ret < 0)
		return ret;
	return sysfs_emit(buf, "%u\n", (unsigned int)ret);
}
static DEVICE_ATTR_RO(raw_soc);

static ssize_t raw_voltage_mv_show(struct device *dev,
				  struct device_attribute *attr, char *buf)
{
	int ret = bq_myron_diag_read(to_i2c_client(dev), BQ_FG_REG_VOLT);

	if (ret < 0)
		return ret;
	return sysfs_emit(buf, "%u\n", (unsigned int)ret);
}
static DEVICE_ATTR_RO(raw_voltage_mv);

static ssize_t raw_temperature_deci_kelvin_show(struct device *dev,
				struct device_attribute *attr, char *buf)
{
	int ret = bq_myron_diag_read(to_i2c_client(dev), BQ_FG_REG_TEMP);

	if (ret < 0)
		return ret;
	return sysfs_emit(buf, "%u\n", (unsigned int)ret);
}
static DEVICE_ATTR_RO(raw_temperature_deci_kelvin);

static struct attribute *bq_myron_diag_attrs[] = {
	&dev_attr_raw_soc.attr,
	&dev_attr_raw_voltage_mv.attr,
	&dev_attr_raw_temperature_deci_kelvin.attr,
	NULL,
};

static const struct attribute_group bq_myron_diag_group = {
	.name = "myron_readonly_gauge",
	.attrs = bq_myron_diag_attrs,
};

static int bq_myron_diag_probe(struct i2c_client *client)
{
	static const unsigned int indices[] = {
		BQ_FG_REG_SOC, BQ_FG_REG_VOLT, BQ_FG_REG_TEMP,
	};
	unsigned int i;
	int ret;

	/* This capture's exact enabled gauge identity. Do not match the other
	 * BQ/NFG variants supported by the full reference driver in this mode.
	 */
	if (client->addr != 0x55 || !client->dev.of_node ||
	    !of_device_is_compatible(client->dev.of_node, "ti,bq27z561_master"))
		return -ENODEV;
	if (!i2c_check_functionality(client->adapter, I2C_FUNC_SMBUS_READ_WORD_DATA))
		return -EOPNOTSUPP;
	for (i = 0; i < ARRAY_SIZE(indices); i++) {
		ret = bq_myron_diag_read(client, indices[i]);
		if (ret < 0)
			return dev_err_probe(&client->dev, ret,
				"read-only gauge register read failed\n");
	}
	ret = devm_device_add_group(&client->dev, &bq_myron_diag_group);
	if (ret)
		return ret;
	dev_info(&client->dev,
		 "read-only gauge diagnostics ready; no MCA provider registered\n");
	return 0;
}
