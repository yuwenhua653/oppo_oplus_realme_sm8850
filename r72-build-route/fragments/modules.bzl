    # R72 independent read-only PMIC client; compilation does not enable loading.
    registry.register(
        name = "drivers/power/supply/myron_mca_readonly/myron_mca_readonly",
        out = "myron_mca_readonly.ko",
        config = "CONFIG_MYRON_MCA_READONLY",
        srcs = [
            "drivers/power/supply/myron_mca_readonly/myron_mca_readonly.c",
            "include/linux/soc/qcom/qti_pmic_glink.h",
        ],
        includes = ["include"],
        deps = ["drivers/soc/qcom/qti_pmic_glink"],
    )
