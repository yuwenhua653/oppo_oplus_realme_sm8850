# 红米 K90PM（myron）ROM 内核源码编译接入

本改动基于 Evolution X `cnb` 的 myron `941665af189930742a02deb258583ec697a7e8ec`，
配合原 `sm8850-common` `98310d6cb945d6ca3d76a8bf2932dc83b0f65b0a`。
只增加 myron 设备层构建规则，common、vendor/lineage、build/make、平台策略均不修改。

ROM 的 `kernel`、模块打包和镜像目标现在依赖 `kernel/build.mk` 中的源码构建规则。
该规则调用 `myron/kernel-6.12` 入口，锁定提交
`ae506d4278722b0a02158de05e8f2918d3ece0f7`，使用其 53 项精确依赖和 54 项 Kleaf 目标。
没有复制下载的 Image，没有使用旧 `.ko`，没有在 ROM 内再次执行内核源码迁移补丁。

`TARGET_NO_KERNEL_OVERRIDE=true` 用于关闭进化 X 的旧 make/defconfig 构建器，
内核编译由本设备 Android.mk 接管。`MYRON_KERNEL_SOURCE` 是实际 ACK 源码目录。
`TARGET_KERNEL_SOURCE` 在这个配置下仅供现有 `generated_kernel_headers` 使用，
继续指向原 Qualcomm 用户空间 UAPI 导出目录；它不决定 Image/模块的来源。

实际内核源码工作区固定为 `kernel/xiaomi/myron`：ACK 源码位于其 `common`，
Qualcomm 模块和 DTS 位于其 `vendor` 等目录；编译入口仍为 `kernel/xiaomi/myron-build`。
内核构建规则显示 `Building KERNEL image`，随后由原 Kleaf 流程构建或校验复用产物。
这条提示不表示每次都会重编全部源码；缓存复用结果会继续明确输出。

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

## 从已有 R123 工作区迁移并编译完整 ROM

已完成源码镜像构建的工作区继续使用原 `OUT_DIR`。更新设备适配器后，在 ROM 根目录运行：

```sh
export OUT_DIR=out-myron-r123-source
export SOONG_NINJA=ninja
python3 -B device/xiaomi/myron/kernel/rom_kernel.py relocate \
  --workspace kernel/xiaomi/myron \
  --legacy-workspace "$OUT_DIR/target/product/myron/obj/MYRON_KERNEL/workspace" \
  --dist "$OUT_DIR/target/product/myron/obj/MYRON_KERNEL/dist"
python3 -B device/xiaomi/myron/kernel/rom_kernel.py verify
```

迁移先严格检查入口和源码版本，再以原子重命名将完整旧工作区移到
`kernel/xiaomi/myron`，在旧位置建立相对符号链接，保持已有缓存中的旧路径可达。
源码、工具链、Kleaf 内部缓存和原始产物整体保留；用于 ROM 打包的 `dist`、
源码 DT 输出和最终镜像仍位于所选 `OUT_DIR`。不需要清空输出或重新执行 `prepare`。
如果新旧位置各有独立工作区，工具会停止，不会覆盖或合并两套源码。

新的工作区根目录包含 `.find-ignore`，由当前 cnb 的 Soong 文件扫描器排除其中的
Android.bp、Android.mk，避免内核附带工具与 ROM 项目重名。该标记不能移到
`kernel/xiaomi` 父目录，否则会屏蔽仍需使用的 UAPI 项目。不同 `OUT_DIR` 共用这一套
内核源码和内部缓存；工作区锁用于串行处理内核操作。保留迁移生成的旧路径链接，
不要手工删除缓存引用的路径。

Ninja 同时会将 ROM 源码挂载为只读；`.find-ignore` 只控制扫描，不授予写权限。
设备配置通过 `BUILD_BROKEN_SRC_DIR_RW_ALLOWLIST` 精确放行 `kernel/xiaomi/myron`
及现有的共享锁文件 `kernel/xiaomi/.myron-adapter.lock`，供 Kleaf 内部输出、Git 元数据和
锁操作使用。首次运行须在普通终端先完成上述 `relocate`/`prepare`，保证挂载目标存在。
其他源码目录继续只读，不设置全局 `BUILD_BROKEN_SRC_DIR_IS_WRITABLE=true`。

上述命令的默认工作区就是 `kernel/xiaomi/myron`，默认 `dist` 按 `OUT_DIR` 计算；
迁移完成后日常 `verify` 和正常 ROM 编译不再需要指定旧工作区路径。
已有完整源码产物通过校验时会复用；保留缓存不代表将来所有 Bazel 动作都能避免重新分析。

在此前成功使用的同一 `lunch` 环境中，编译完整 Evolution X OTA 包：

```sh
m -j4 evolution MYRON_DT_MODE=source \
  MYRON_KERNEL_JOBS=2 MYRON_KERNEL_RAM_MB=10000
```

新终端需要先 `source build/envsetup.sh` 并重新执行原来成功的 `lineage_myron` lunch 组合。
`evolution` 是当前 cnb 的整包目标，自动带上 boot、vendor_boot、DTBO、system_dlkm、
vendor_dlkm 等配套镜像，并在 `$OUT_DIR/target/product/myron/` 生成 ROM ZIP 和 SHA256 文件。
可以先运行 `m -j4 kernel` 仅检查内核，但无需将它作为每次整包编译的额外前置步骤。
这次目录迁移与构建规则检查不等于完整 ROM 编译成功；整包构建和刷入回归仍待执行。

首次接入且没有已有源码工作区时，才执行下面的源码准备。若此前使用预编译内核，
首次源码构建应选独立 `OUT_DIR`，避免混用旧预编译输出；不要因此更换已经成功的 R123 输出目录。

```sh
export OUT_DIR=out-myron-source
export SOONG_NINJA=ninja
python3 -B device/xiaomi/myron/kernel/rom_kernel.py prepare --jobs 4
source build/envsetup.sh
# 使用你当前 cnb checkout 已正常使用的 lineage_myron lunch 组合。
# lunch ...
m -j4 evolution MYRON_DT_MODE=source \
  MYRON_KERNEL_JOBS=2 MYRON_KERNEL_RAM_MB=10000
```

`prepare` 只同步并检查源码、工具链，不编译内核。后续 `m` 自动编译。
内核入口、53 项依赖清单及 DTS 锁定不变；合并脚本保留已安装的 Myron 扁平 UAPI
头文件修复和音频模块选项。历史验证 JSON 保留原始内容，不作为本次完整 ROM 通过记录。
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

## 2026-11-05：源码镜像音频参数与 vendor_dlkm 打包

本轮源码镜像可启动，但真机报告无声音。采集中 295 个模块已加载，三个 TFA I2C
设备均已绑定，TFA 模块引用数却由正常 R123 的 3 变为 0；运行分区缺少 `modules.options`。
正常 R123 的加载器会传入 `machine_dlkm.ko myron_tfa_links=1`，而锁定模块源码的
该参数默认为关闭。本次通过 Android 标准 `BOARD_VENDOR_KERNEL_MODULES_OPTIONS_FILE`
将 `options machine_dlkm myron_tfa_links=1` 装入 `vendor_dlkm/lib/modules/modules.options`，
恢复三个 TFA codec 链路所需的加载参数。修复提交为
`8241d5eb0f3d0700575dde5203157bed1c38702b`；用户于 2026-11-05 确认“音频已经恢复”。
该结论来自用户真机反馈，本轮没有新增日志采集或参数读回，也不代表完整 ROM 已通过验证。

同时保留已实测启动的 EROFS / `lz4hc,9` / 非 sparse 配置：此前镜像为 27,598,848
字节，小于该设备现有 vendor_dlkm 分区的 53,805,056 字节。新增参数后的实际大小仍需检查。
入口、DTS、源码 lock、Image 和模块源码均未修改。合并器保留既有扁平头文件修复，以及
用户追加在设备 `BoardConfig.mk` 中的同值 EROFS 配置；未知适配器修改仍会停止合并。

在已完成本轮 R123 全量源码构建、已 `lunch` 的同一 ROM 工作区中，沿用原输出目录重打包：

```sh
export OUT_DIR=out-myron-r123-source
export SOONG_NINJA=ninja
m -j4 vendor_dlkmimage
cat "$OUT_DIR/target/product/myron/vendor_dlkm/lib/modules/modules.options"
file "$OUT_DIR/target/product/myron/vendor_dlkm.img"
stat -c '%s bytes' "$OUT_DIR/target/product/myron/vendor_dlkm.img"
```

已有完整源码产物通过校验时，此目标复用内核和模块，只更新打包结果；无需清空 OUT_DIR 或
重跑 `prepare`。确认参数文件包含上述行、镜像为 EROFS 且适合现有分区。此单分区更新只适用于
当前已运行的同一批 R123 Image/模块；切换内核来源时仍需配套镜像。重新启动加载后再检查
`/sys/module/machine_dlkm/parameters/myron_tfa_links` 为 `Y`，并实际测试扬声器、听筒等音频路径。

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
