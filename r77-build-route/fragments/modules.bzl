    # R77 independent observer; DDK generates its Makefile from this single TU.
    registry.register(
        name = "drivers/thermal/myron_buck_thermal",
        out = "myron_buck_thermal.ko",
        config = "CONFIG_MYRON_BUCK_THERMAL",
        srcs = ["drivers/thermal/myron_buck_thermal.c"],
        deps = [],
    )
