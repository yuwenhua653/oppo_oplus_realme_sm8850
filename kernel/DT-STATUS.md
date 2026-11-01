# R119：八变体源码 DT 装配

目标：红米 K90PM / myron。默认仍为 `MYRON_DT_MODE=oem`，源码模式需真机验证。

## 本轮变化

两个 CanoeP 温控变体原始 MSM-ID `0x1010295` 保持不变。根据高通 ABL 的明确
foundry-zero 回退实现，只为 v1/v2 两个已核实 ID 对允许组件匹配；芯片编号、OEM 高位
及版本必须相同。相机和显示已有精确 ID，继续优先精确匹配。
规则、固定版本的原始依据和证据边界见 [DT-ID-MATCHING.md](DT-ID-MATCHING.md)。
未放宽硬件提供者、GPU 版本、音频寄存器、震动路径或输出容器检查。

DTS 保持 `feff8ac781caca95799d642f79a6bfa23a17e639`，
内核入口保持 `eff369c241c9219757bb04f46899d21a5ed14d5c`。
R118 已补齐的相机、音频、GPU、MMRM、fence、SYNX、SMEM mailbox、指纹辅助及
WCN786x 蓝牙组件都纳入本轮装配。没有修改 ROM 通用源码或内核源码。

`source_dt.py --compiled` 可从经过哈希/来源检查的 DT 专项编译产物装配原始镜像；
ROM 构建使用 `--full` 路径，并显式传入 `--build-status`：入口提交、DTS 提交、
构建成功状态及内核版本/时间横幅必须与产物一致，旧全量产物不能作为新源码的证明。
CI 改为全部八变体通过才成功，不再把“诊断完成但仍有阻塞”显示为通过。
成功后上传 `dtb.img`、`dtbo.img`、编译来源和装配报告。
这些是原始构建输入，不是含 boot/vendor_boot/AVB 的可刷包。

## 验证范围

本地使用 R118 锁定源码已编译的 32 个输入执行真实合并，不重复编译 Image/模块。
本轮报告见 `DT-CHECK-R119.json`；输入来源见 `DT-COMPILE-R118-EXPANDED.json`。
八变体必须完整通过；28 条 foundry-zero 使用记录独立保留在报告中。
另外检查八段 DTB 顺序和身份、单项 DTBO 表及其板级元数据，保留旧六变体结果比较。
九项装配器测试覆盖错误匹配、哈希/版本篡改、硬件缺失、GPU 版本、禁用父节点、
寄存器值、旧镜像失效及八变体容器回读。
旧 R117/R118 适配器升级支持精确哈希白名单，拒绝覆盖未知本地改动。

完整 ROM 编译、新入口的完整内核编译及本轮真机验证尚未进行。
现有 R115 全量产物属于旧入口，不能冒充新入口的完整产物。
原厂两个温控基础 DT 组件较少，本轮补全也不能据此认定与原厂行为等价。

## 重现和接入

```sh
python3 -B kernel/compile_dt.py --entry /锁定的内核入口 \
  --workspace /单独的DT源码目录 --output /单独的DT产物目录 --sync
python3 -B kernel/source_dt.py --compiled /单独的DT产物目录 \
  --output /单独的DT镜像目录
```

主机需要 `cpp`、`dtc`、`fdtoverlay`、`fdtoverlaymerge`、`fdtput` 和 `mkdtboimg`。
合并工具可用同名参数指定；专项 CI 固定工具源码提交。

设备层的 ROM 构建接入已经存在：完成 README 的适配器合并和源码同步后，
使用 `m myron-source-dt-check` 构建/检查完整内核配套的 DT；
测试源码模式时使用 `m MYRON_DT_MODE=source <当前ROM打包目标>`。
它依赖本次入口对应的 Image/模块构建，不会把专项目录的镜像当作全量内核缓存。
保持 OEM 为默认，待匹配整包完成真机回归后再考虑切换默认值。

历史 R115/R118 报告保留用于追溯，不能把其中旧阻塞状态当作本轮结果。
