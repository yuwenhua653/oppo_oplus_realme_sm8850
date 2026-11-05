# R123：真机验证完成，默认编译源码 DT

目标：红米 K90PM / myron。R123 已完成本轮真机功能验证，默认值为
`MYRON_DT_MODE=source`。本轮状态记录见 `DT-VALIDATION-R123.json`。

## 已合入的修正

- 音频：WCD 禁用标志、主 TDM pinctrl 引用、4 槽及 OEM 时钟属性。
- 相机：cam_res_mgr 所需的两个 legacy GPIO 数值。
- 振动：OEM 周期、电压和制动参数；保留原有效果波形。
- 闪光灯：LED0 单通道及 500 mA 闪光电流上限。
- FastRPC：基底合并后恢复 ADSP 1→6、CDSP 1→11 的上下文节点顺序。
  仅移动完整子树，属性字节、phandle 和其他区域保持不变；对照锁定的 DSP
  overlay 校验来源，拒绝未知顺序、缺失或新增节点。

DTS：`78c0b1cecb5cad48af8d01cd66afbb1759596190`。
内核入口：`ae506d4278722b0a02158de05e8f2918d3ece0f7`。
common 和模块源码未改动。有限 foundry-zero ID 匹配、提供者、GPU 版本及
全量构建来源检查保持启用，详见 `DT-ID-MATCHING.md`。
最终八棵合并树还须通过音频、相机 GPIO、振动和闪光灯属性检查；TDM 引用
按目标节点路径验证，不固定编译器分配的 phandle 数值。

## 构建接入

按照 `README-CN.md` 合并设备适配器并同步上述内核入口后，正常 ROM 镜像目标
自动生成并使用源码 `dtb.img`、`dtbo.img`。不再需要传入 source 参数。
`m myron-source-dt-check` 可显式运行配套完整内核的 DT 构建检查。
临时对照 OEM DT 可显式使用 `MYRON_DT_MODE=oem`；失败不会自动回退。

专项 CI 只从四个锁定源码项目编译 32 个 DT 输入，装配并校验全部八变体，
同时保存来源清单和 `fastrpc-order-proof.json`。重现方式：

```sh
python3 -B kernel/compile_dt.py --entry /锁定的内核入口 \
  --workspace /单独的DT源码目录 --output /单独的DT产物目录 --sync
python3 -B kernel/source_dt.py --compiled /单独的DT产物目录 \
  --output /单独的DT镜像目录
```

主机需要 `cpp`、`dtc`、`fdtoverlay`、`fdtoverlaymerge`、`fdtput` 和 `mkdtboimg`。
专项输出为原始构建输入，不是可刷整包。ROM 使用 `--full --build-status` 路径，
严格检查入口、DTS、构建成功状态、内核版本及产物哈希；旧 R115 全量产物不能
冒充新入口构建结果。

## 验证范围

用户于 2026-11-03 确认各项功能正常。R123 日志支持正常启动、前后相机首帧、
DSP 会话成功及手电筒开关，音频和振动此前也已确认恢复。短时采集中未观察到
相机服务重启、FastRPC 无会话错误或崩溃记录。

本次完成的是已测设备功能的 DT 适配和源码编译接入。八变体均接受构建检查，
实际设备使用 Canoe v2；不能将单机测试扩展为所有硬件变体、拍摄模式或长时间
稳定性认证。本次没有重新编译完整内核或完整 ROM。新 ROM 的模块加载时序、
Recovery 和私有运行时配置仍需配套整包验证。

## 2026-11-05 源码镜像集成回归

源码镜像启动后出现无声音。当前采集显示全部 295 个模块已加载、三个 TFA I2C 设备
已绑定，但 TFA 模块引用数为 0（正常 R123 为 3），且缺少 `modules.options`。
已确认正常 R123 加载器传入 `myron_tfa_links=1`；锁定的 `machine_dlkm` 源码默认关闭
该参数，因此本次在 vendor_dlkm 标准模块选项文件中补回它，不改 DTS、入口或源码 lock。
同时固化用户已验证可启动的 EROFS 打包配置，避免 raw ext4 模块镜像超过现有分区。
升级方法和 `m vendor_dlkmimage` 重打包命令见 `README-CN.md`。修复后的镜像尚待真机
确认声音恢复；先前 R123 独立测试包的通过记录不能替代此次源码镜像回归验证。

R115/R118/R119 历史报告保持原样，仅作为原版本证据。
