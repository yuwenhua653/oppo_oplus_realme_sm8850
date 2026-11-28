### AnyKernel3 device configuration; core and binaries are upstream osm0sis.
properties() { '
kernel.string=Myron 6.12.118 KernelSU Next by yuzuli
do.devicecheck=1
do.modules=0
do.systemless=0
do.cleanup=1
do.cleanuponabort=0
device.name1=myron
supported.versions=
supported.patchlevels=
supported.vendorpatchlevels=
'; }

BLOCK=boot;
IS_SLOT_DEVICE=1;
RAMDISK_COMPRESSION=auto;
PATCH_VBMETA_FLAG=auto;

. tools/ak3-core.sh;

# boot v4 has its first-stage ramdisk in init_boot: retain existing boot data.
split_boot;
flash_boot;
