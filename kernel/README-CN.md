# 红米 K90PM（myron）ROM 内核源码编译接入

本改动基于 Evolution X `cnb` 的 myron `941665af189930742a02deb258583ec697a7e8ec`，
配合原 `sm8850-common` `98310d6cb945d6ca3d76a8bf2932dc83b0f65b0a`。
只增加 myron 设备层构建规则，common、vendor/lineage、build/make、平台策略均不修改。

ROM 的 `kernel`、模块打包和镜像目标现在依赖 `kernel/build.mk` 中的源码构建规则。
该规则调用 `myron/kernel-6.12` 入口，锁定提交
`bb043db67432d670e171835d3719618adb31470a`，使用其 53 项精确依赖和 54 项 Kleaf 目标。
没有复制下载的 Image，没有使用旧 `.ko`，没有在 ROM 内再次执行内核源码迁移补丁。

`TARGET_NO_KERNEL_OVERRIDE=true` 用于关闭进化 X 的旧 make/defconfig 构建器，
内核编译由本设备 Android.mk 接管。`MYRON_KERNEL_SOURCE` 是实际 ACK 源码目录。
`TARGET_KERNEL_SOURCE` 在这个配置下仅供现有 `generated_kernel_headers` 使用，
继续指向原 Qualcomm 用户空间 UAPI 导出目录；它不决定 Image/模块的来源。

## 接入现有 ROM 源码

已有 SELinux、Recovery、相机等改动时，使用独立目录中的本设备分支合并，避免替换整个设备树：

```sh
git clone --single-branch --branch myron/device-cnb-source \
  https://github.com/yuwenhua653/oppo_oplus_realme_sm8850.git /tmp/myron-source-adapter
python3 /tmp/myron-source-adapter/kernel/apply_source_build.py /你的/evo/源码目录
python3 /tmp/myron-source-adapter/kernel/apply_source_build.py /你的/evo/源码目录 --apply
```

合并脚本保留原 BoardConfig 中内核块以外的内容及全部 sepolicy 文件。
内核块本身存在额外本地改动时会停止并显示原因，不会强制覆盖。
重复应用不产生修改。完整设备分支也可以用于全新 checkout，但它不包含你本地额外的策略改动。

在 ROM 根目录拉取编译入口。已有 `kernel/xiaomi/myron-build` 项目时，修改现有 manifest 的
revision 为上述提交，不要再增加同路径项目；尚不存在时：

```sh
mkdir -p .repo/local_manifests
cp device/xiaomi/myron/kernel/local_manifest.xml .repo/local_manifests/myron-source.xml
repo sync -c kernel/xiaomi/myron-build
```

保留 `kernel/xiaomi/myron-prebuilt` 依赖：默认使用其既有 UAPI 头文件，显式 OEM 模式也使用其中 DTB/DTBO。
其原 `kernel`、`vendor_dlkm/*.ko`、`vendor_ramdisk/*.ko`、`system_dlkm/*.ko` 已不再作为构建输入。
R123 源码 DT 已通过本轮真机功能验证，默认启用 `MYRON_DT_MODE=source`。
正常 ROM 镜像目标会编译并装配配套 DTB/DTBO；临时对照可显式指定 `MYRON_DT_MODE=oem`。
具体证据、使用方式和验证边界见 [DT-STATUS.md](DT-STATUS.md)。
本轮检查的 OEM 仓库提交是 `9999f765b53876bf7a013a4fde5221153ad570fc`。

第一次切换请用新 OUT_DIR，避免旧预编译模块和旧版本目录残留到增量输出：

```sh
export OUT_DIR=out-myron-source
export SOONG_NINJA=ninja
python3 -B device/xiaomi/myron/kernel/rom_kernel.py prepare \
  --workspace "$OUT_DIR/target/product/myron/obj/MYRON_KERNEL/workspace" --jobs 4
source build/envsetup.sh
# 使用你当前 cnb checkout 已正常使用的 lineage_myron lunch 组合。
# lunch ...
m kernel
# 或执行平时的 ROM 打包目标；它同样会先构建内核和模块。
```

`prepare` 只同步并检查源码、工具链，不编译内核。后续 `m` 自动编译。
`OUT_DIR` 使用相对 ROM 根目录的路径；当前 cnb 的 fsgen 会拒绝绝对路径形式的源码模块和 DTBO 输入。
若已经使用绝对路径，只需在 ROM 根目录将 `OUT_DIR` 改成同一目录的相对写法，无需删除输出或重新同步。
`SOONG_NINJA=ninja` 在当前 shell 中选择原生 Ninja，可避开 Siso 的 `@config//main.star` 配置加载失败。
可通过构建参数 `MYRON_KERNEL_JOBS=4 MYRON_KERNEL_RAM_MB=16000` 调整资源；
默认 2 个任务 / 10000 MB。宿主为 x86-64 Ubuntu，内核工作区至少预留 100 GB，
完整 ROM 另需其正常磁盘和内存空间。内核工具链与 ROM 用户空间 Clang 独立，均按原有配置使用。

## 模块与增量检查

`modules.json` 固定 297 个源码模块提供者，明确选择 ACK 的 zram/zsmalloc，
不选择同名 Qualcomm 参考实现。Android 使用标准模块规则生成 depmod 和加载清单：

- system_dlkm：3 个 GKI 模块，保留签名；vendor_dlkm：294 个模块。
- vendor ramdisk 与 Recovery：234 个模块，加载清单分别为 114 / 234 项。
- vendor 常规加载清单：225 项；诊断用 readonly 模块随产物保留但不主动加载。

加载清单以公开 OEM 清单和源码模块依赖构建，去重并补齐依赖；源触摸、背光和对应音频提供者
使用实际源码模块名。没有可用且已选定源码提供者的 OEM 条目在 JSON 中逐项列出，
不会偷偷回填旧版本模块。这里没有宣称每个被排除模块都不影响功能。

每次构建检查入口提交、53 个源码仓库是否干净、全部输出哈希、vermagic、依赖清单、
内核与模块符号 CRC。改动源码必须先提交并更新 lock；依赖变化需复审并更新模块目录。
未改动且已验证的源码编译结果会复用；只改设备打包规则时，也会先尝试验证并复用完整编译原始产物，
避免重新编译整个内核。缺失或被篡改的缓存停止，不降级使用旧内核。
版本来自真实 common 提交，时间来自实际构建开始时间，保留表示 4 KiB 页的 `-4k`。

内核与源码 DT 的每次成功校验分别生成 `kernel-check.d`、`dt-check.d` 依赖文件，
记录保留的不存在输入 `$(MYRON_KERNEL_OUT)/.source-check-force`。
原生 Ninja 的动态依赖处理使校验每次运行，同时兼容 cnb 的真实产物依赖 `.PHONY` 限制，
以及缺失输出和缺失依赖文件的严格检查。该保留路径不是输出，不要创建同名文件或规则。
`Image` 与 DT 的 `.KATI_RESTAT`、模块及 DTBO 隐式输出声明保持不变。
内容相同时不重写的 `PRODUCT_OUT/kernel`、`PRODUCT_OUT/dtb.img` 复制规则也启用 restat。
已用真实 Kati/Android Ninja 的 cnb 严格选项验证上述规则、连续两次校验、缓存复用、
直接构建隐式输出和失败阻断；该小型测试用替代命令模拟昂贵的内核/DT 任务，不代表完整 ROM 构建通过。

## 当前验证与边界

已用成功的 R115 完整编译产物运行适配器：297 个模块、18,543 项导入 CRC 检查通过。
另用实际 Kati/Ninja 和当前进化 X 模块规则验证干净输出目录的内核及四组模块依赖图。
以上属于历史构建适配器验证，不是完整 Soong/ROM 构建。R123 已完成独立 DT 测试包的真机功能验证，
但本次源码接入尚未生成新的完整 ROM。

尤其：本次设备构建规则不是 R115 三镜像包的源码复现。R115 的定制早期加载器、
DSP/VPP/ready broker、Recovery 独立运行时尚未全部整理进公开设备树；本次不会移植或覆盖它们。
已有 R113 设备策略保留，但不能据此宣称完整 R110/R115 行为已在 ROM 源码中复现。
首次源码 ROM 的模块加载时序、快充、DSP/相机、Recovery 等仍须完整编译和真机回归。
不要将生成的单独 boot 或 dlkm 与旧版模块分开刷入；先完成匹配整包验证。

## R123 DT 专项验证与默认源码模式

最新进度和准确验证范围见 [DT-STATUS.md](DT-STATUS.md)。
32 个 DT 输入可独立从锁定源码编译；八变体使用严格硬件检查和有限 foundry-zero 匹配。
专项 CI 必须全部通过才输出原始 DTB/DTBO；不会编译 Image、模块或完整 ROM。
原始 DT 镜像不是可刷整包。R123 实测修正已合入，默认使用源码 DT，CI 同时校验 FastRPC 顺序和关键板级属性。
现有 R115 全量产物不满足新入口身份检查，需要新全量构建才能作为其产物使用。
