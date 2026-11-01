load("@bazel_skylib//rules:write_file.bzl", "write_file")
load(":kleaf-scripts/msm_kernel_extensions.bzl", "get_custom_dtbo_img_list", "get_dtb_list", "get_dtbo_list", "get_dtstree")
load("//build/kernel/kleaf:kernel.bzl", "kernel_build", "kernel_build_config")

def define_qcom_dtb_setup():
    write_file(
        name = "dtb_build_config",
        out = "build.config.qcom.dtbs",
        content = [
            "KERNEL_DIR=common",
            "SOC_DIR={}".format(native.package_name()),
            "export DTC_INCLUDE=${ROOT_DIR}/${SOC_DIR}/include",
            "BOOT_IMAGE_HEADER_VERSION=4",
            "BUILD_INIT_BOOT_IMG=1",
            "LZ4_RAMDISK=1",
            "PAGE_SIZE=4096",
            "BASE_ADDRESS=0x80000000",
            "VENDOR_BOOTCONFIG+='androidboot.first_stage_console=1 androidboot.hardware=qcom_kp'",
            'DTC_FLAGS="-@"',
            "KERNEL_BINARY=Image",
            "",
        ],
    )

    kernel_build_config(
        name = "build.config.qcom.dtb",
        srcs = [
            ":dtb_build_config",
            "//common:build.config.common",
        ],
    )

def define_qcom_dtbs(
        stem,
        target,
        defconfig,
        cmdline = [""]):
    """Build a the dtbs for a target/variant.

    Args:
        stem: The name of the rule
        target: Configuration to use to build the DTBs
        defconfig: defconfig for the kernel_build.

    Returns:
        A tuple:
        - the first item is the list of DTBs to be built
        - the second item is the list of DTBOs to be built
    """

    write_file(
        name = "{}_cmdline_extras".format(stem),
        out = "{}.cmdline.extras".format(stem),
        content = ["KERNEL_VENDOR_CMDLINE='{}'".format(" ".join(cmdline)), ""],
    )

    kernel_build_config(
        name = "{}.build.config.qcom.dtb".format(stem),
        srcs = [
            ":{}_cmdline_extras".format(stem),
            ":build.config.qcom.dtb",
        ],
    )

    dtb_list = get_dtb_list(target)
    dtbo_list = get_dtbo_list(target)
    custom_dtbo_img_list = get_custom_dtbo_img_list(target)

    # Retain already-generated subsystem overlays for offline DT composition.
    # This list is not a device dtbo.img recipe; board/family alternatives conflict.
    diagnostic_dtbo_outs = []
    if target == "canoe" and stem == "canoe_perf":
        diagnostic_dtbo_outs = [
            "canoe-audio-atp.dtbo",
            "canoe-audio-cdp-pandeiro-i2s.dtbo",
            "canoe-audio-cdp-wsa885x.dtbo",
            "canoe-audio-cdp.dtbo",
            "canoe-audio-hamilton-cdp.dtbo",
            "canoe-audio-hamilton-mtp.dtbo",
            "canoe-audio-hamilton-rcm.dtbo",
            "canoe-audio-hdk.dtbo",
            "canoe-audio-mtp-3.5mm.dtbo",
            "canoe-audio-mtp-pictor.dtbo",
            "canoe-audio-mtp-qmp.dtbo",
            "canoe-audio-mtp-wsa885x.dtbo",
            "canoe-audio-mtp.dtbo",
            "canoe-audio-qrd-sku2.dtbo",
            "canoe-audio-qrd.dtbo",
            "canoe-audio-rcm.dtbo",
            "canoe-audio-rumi.dtbo",
            "canoe-camera-sensor-cdp.dtbo",
            "canoe-camera-sensor-hdk.dtbo",
            "canoe-camera-sensor-mtp.dtbo",
            "canoe-camera-sensor-qrd.dtbo",
            "canoe-camera-sensor-rumi.dtbo",
            "canoe-cdp-kiwi-no-l3k.dtbo",
            "canoe-cdp-kiwi-no-l6k.dtbo",
            "canoe-cdp-peach-no-l3k.dtbo",
            "canoe-cdp-peach-no-l6k.dtbo",
            "canoe-dsp.dtbo",
            "canoe-dsp_v2.dtbo",
            "canoe-eva.dtbo",
            "canoe-gpu.dtbo",
            "canoe-hfi-core.dtbo",
            "canoe-ipa.dtbo",
            "canoe-kiwi-bt.dtbo",
            "canoe-kiwi-cnss.dtbo",
            "canoe-mm-atp-overlay.dtbo",
            "canoe-mm-cdp-kiwi-overlay.dtbo",
            "canoe-mm-cdp-overlay.dtbo",
            "canoe-mm-cdp-st54l-pandeiro-overlay.dtbo",
            "canoe-mm-mtp-overlay.dtbo",
            "canoe-mm-qrd-sku1-overlay.dtbo",
            "canoe-mm-qrd-sku2-overlay.dtbo",
            "canoe-mm-rcm-kiwi-overlay.dtbo",
            "canoe-mm-rcm-overlay.dtbo",
            "canoe-mm-rcm-st54l-pandeiro-overlay.dtbo",
            "canoe-mm-rumi-overlay.dtbo",
            "canoe-peach-bt.dtbo",
            "canoe-peach-cnss.dtbo",
            "canoe-sde-display-atp-overlay.dtbo",
            "canoe-sde-display-cdp-kiwi-overlay.dtbo",
            "canoe-sde-display-cdp-overlay.dtbo",
            "canoe-sde-display-cdp-st54l-pandeiro-overlay.dtbo",
            "canoe-sde-display-hdk-overlay.dtbo",
            "canoe-sde-display-mtp-overlay.dtbo",
            "canoe-sde-display-qrd-sku1-overlay.dtbo",
            "canoe-sde-display-qrd-sku2-overlay.dtbo",
            "canoe-sde-display-rcm-kiwi-overlay.dtbo",
            "canoe-sde-display-rcm-overlay.dtbo",
            "canoe-sde-display-rcm-st54l-pandeiro-overlay.dtbo",
            "canoe-sde-display-rumi-overlay.dtbo",
            "canoe-v2-gpu.dtbo",
            "canoe-vidc-v2.dtbo",
            "canoe-vidc-v3.dtbo",
            "canoe-vidc.dtbo",
            "canoe-wcn786x-bt.dtbo",
            "canoe-wcn786x-no-l6k.dtbo",
            "canoep-hdk-peach-bt.dtbo",
            "canoep-hdk-peach-cnss.dtbo",
            "canoep-sg-gpu.dtbo",
            "canoep-sg-v2-gpu.dtbo",
        ]
        diagnostic_dtbo_outs = [name for name in diagnostic_dtbo_outs if name not in dtb_list + dtbo_list]

    kernel_build(
        name = "{}_dtb_build".format(stem),
        srcs = [
            # keep sorted
            ":additional_msm_headers_aarch64_globs",
            "//common:kernel_aarch64_sources",
        ],
        build_config = ":{}.build.config.qcom.dtb".format(stem),
        dtstree = get_dtstree(target),
        outs = dtb_list + dtbo_list + diagnostic_dtbo_outs + ["vmlinux", "Module.symvers", "Image", "System.map", ".config"],
        base_kernel = ":{}_base_kernel".format(stem),
        kconfig_ext = ":kconfig.msm.generated",
        makefile = "//common:Makefile",
        defconfig = defconfig,
        post_defconfig_fragments = [
            ":{}_merged_defconfig".format(stem),
        ],
        make_goals = [
            "dtbs",
        ],
        visibility = ["//visibility:public"],
    )
    return [dtb_list, dtbo_list, custom_dtbo_img_list]
