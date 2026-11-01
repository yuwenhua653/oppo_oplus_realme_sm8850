# R117：源码 DT 装配已接入，真实源码检查仍有阻塞

目标为红米 K90PM / myron。默认 `MYRON_DT_MODE=oem`，保持原厂 DT。
目前不能把 `MYRON_DT_MODE=source` 当作已经可以刷机的配置。

新增的 `source_dt.py`、`dt-profile.json` 和设备层 Make 规则完成以下工作：

- 固定原厂顺序下的 8 个基础 DTB，对应源码的 canoe/canoep、v1/v2、thermal profile 变体。
- 对基础 DT、SoC 组件和板级 overlay 分别建模，不把所有 `.dtbo` 按文件名顺序拼接。
- 使用 `fdtoverlay` 合并基础层、`fdtoverlaymerge` 合并板级 overlay，并恢复各层应有的硬件标识。
- 用 `mkdtboimg` 生成与已核对原厂格式相符的单表项容器：4096 页、版本 0、id/rev/custom 为 0。
- 逐个合并检查 8 个变体及必需硬件提供者，然后才生成供 ROM 消费的 `dtb.img` / `dtbo.img`。
- 原厂模式不依赖源码 DT 装配。源码模式下，vendor_boot 使用新 DTB，DTBO 仍由 Android 标准规则添加 AVB/footer。
- 失败时删除旧 DT 镜像并返回非零，不用原厂文件或上次成功文件冒充新的源码产物。

## 本轮真实检查结果

输入为 R115 成功编译产物，DTS 提交 `9956353d359e30561eac7d33c71e2ffb1afeb700`。
原厂对照是公开 myron-prebuilt 提交 `9999f765b53876bf7a013a4fde5221153ad570fc`。

1. 8 个基础 DTB 的根节点 msm-id/board-id 均找到唯一且一致的源码产物。
2. 先前收集的 3 个基础组件加 4 个 myron 板级组件能顺序应用，但不构成完整硬件树。
3. 缺少编译产物 `canoe-camera.dtbo`。v1 源码存在，但当前平台产物列表只收集了 v2 相机基础 overlay；不能将 v2 用于所有 v1 变体来掩盖缺口。
4. GPU overlay 引用 `debugbus_en`、`gpu_niden_en`，当前 DTS 树中查到引用，未查到对应定义。实际 `fdtoverlay` 返回 `FDT_ERR_NOTFOUND`。
5. 音频树存在只有节点位置或子节点、缺少宏模块 `compatible` / `reg` 的占位结构。RX/TX/VA/WSA2 等提供者必须补齐；overlay 能应用不表示驱动能够绑定。
6. 若干 SoC/SKU 标识无法在当前组件之间直接对应，尤其 CanoeP thermal profile。检查器记录为待审核，没有自行扩大 ID、改芯片版本或假定掩码。

这次严格预检记录了 1 个缺失产物、12 条未解析符号记录、22 条 SoC/SKU 映射待审核记录。
这些记录跨多个变体重复，不表示有 35 个独立硬件故障。
增加已有 DSP/EVA/HFI/IPA/video/peach 组件能够补入部分节点，但不会消除上述 GPU/音频/版本选择问题。

## 已完成验证

- 5 项测试通过：畸形 FDT 拒绝、真实 R115 阻塞、失败后旧镜像清除、8 变体测试数据装配与回读、禁用父总线下的提供者拒绝。
- 实际 Kati/Ninja 检查通过：OEM 和 source 两种模式的干净依赖图，使用当前进化 X 原生 DTB/DTBO 打包规则。
- R116 升级合并测试通过：只接受与上版哈希完全一致的适配器文件更新，保留本地策略，重复应用无改动。
- 没有进行新的完整内核编译、完整 ROM 编译或真机测试；没有生成可刷的源码 DT 镜像。

## 如何复查与后续使用

已有完整编译产物时可直接检查，无需再编译 90 分钟：

```sh
python3 -B device/xiaomi/myron/kernel/source_dt.py \
  --full /已有的/kernel_workspace/integration-artifacts/full \
  --output /单独的/source-dt-check
```

当前 R115 输入会在预检返回失败，报告位于 `source-dt-report.json`；这是检测到真实阻塞的结果。
输入问题修复后，装配阶段还需要 PATH 中有 `fdtoverlay`、`fdtoverlaymerge`、`fdtput`、`mkdtboimg`，
也可用脚本同名参数指定其路径。

后续在 DTS 修复且更新锁定版本后，ROM 环境中的目标为：

```sh
m myron-source-dt-check
# 检查全部通过后，再测试源码 DT 的 ROM 配置：
m MYRON_DT_MODE=source
```

现在不应为了获得同样的预检失败而重跑完整内核构建。设备适配器修改可复用符合当前源码提交、
入口提交和输出哈希的已有成功编译结果，重新验证并装配，不改原构建时间。

后续修复应依次处理相机产物收集、GPU 提供者定义、音频完整绑定及各 SoC/SKU 的映射。
通过上述静态检查后仍需要匹配整包的真机测试，静态通过不是硬件功能保证。
