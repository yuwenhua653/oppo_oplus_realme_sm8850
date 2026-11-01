# R118：补齐 DT 源码缺口，继续保留刷机门禁

目标：红米 K90PM / myron。默认 `MYRON_DT_MODE=oem`。

本轮源码修复已经写入 DTS 分支：
`0d015de10a547545b053acb7df2a097996bf011d`。
内核入口锁定为 `ff31bb42e8b96c2b6017b1da2ea6841f57488737`；ACK 与模块源码提交未变。
R115 产物仍属于原锁定版本，不能冒充本次新源码的完整内核产物。

## 已修复

- 收集 v1 `canoe-camera.dtbo`，保留 v1/v2 分开选择。
- 移除 Canoe QFPROM 不存在的两个可选 GPU 熔丝引用。它们是 NVMEM 单元，不是时钟。
  锁定模块源码 `b2877f8` 的 `adreno_read_fuse()` 对 `-ENOENT` 返回 0。
- 恢复 LPASS 宏模块、时钟、SoundWire 控制器、GPIO 及寄存器定义。
- 将 SoundWire 从设备放回相应 master 下；保留 Myron TFA 功放、WSA2 震动和板级路由。
- 调整板级 overlay 次序：Myron 提供者在前，peach WLAN/BT 在后，消除合并后的前向未解析引用。
- 按硬件版本检查 GPU：v1 为 `gen8-2-0`，v2 为 `gen8-2-1`。
- 校验音频宏寄存器和震动从设备所在路径，防止只有 compatible 名称的空节点被误判通过。

## 验证范围

使用四个锁定的源码项目和真实 CPP/DTC 编译 27 个输入，不重编 Image 或内核模块。
其中 23 个未修改输入，与 R115 完整构建产物的 FDT 节点/属性逐项相同。
相机缺失产物、GPU 悬空引用已经清零。
六个可直接匹配 ID 的变体通过真实合并、提供者检查及容器回读。
诊断用临时容器会自动删除，不输出可刷镜像。
新增构建入口/源码清洁检查、实际工具版本/哈希、构建起止时间和产物哈希记录。

## 剩余阻塞

`canoep-tp.dtb` / `canoep-tp-v2.dtb` 使用 `0x1010295`，而 11 类组件列出 `0x1000295`，
共 22 条跨变体记录。原厂基础 DT 也包含前者，不能简单当作拼写错误修改。
旧高通 MSM-ID 文档说明了 foundry 为 0 的回退语义，但这还不足以证明本机 ABL 的
选择行为和当前构建脚本完全一致，因此没有自动掩码、扩大 ID 或改变发布的 8 变体集合。
生产装配器仍拒绝该完整 profile，默认原厂 DT 不变。

`audit_dt.py` 的成功退出表示诊断完成；只有报告中的 `all_variants_passed=true`
才表示整个 profile 通过静态检查。该字段目前为 false，亦不能代替真机测试。
完整 ROM 编译和本轮真机验证均未进行。

## 重现

```sh
python3 -B kernel/compile_dt.py --entry /锁定的内核入口 \
  --workspace /单独的DT源码目录 --output /单独的DT产物目录 --sync
python3 -B kernel/audit_dt.py --compiled /单独的DT产物目录 \
  --report /单独的报告目录/audit.json
```

主机需要 `cpp`、`dtc`、`fdtoverlay`、`fdtoverlaymerge`、`fdtput` 和 `mkdtboimg`。
工具可通过同名参数指定。GitHub 的 `dt-source.yml` 固定合并工具提交并上传诊断附件，
不生成刷机包，也不触发约 90 分钟的完整内核构建。

旧的 `DT-CHECK-R115.json` 是 R117 的历史失败记录；本轮结果见 `DT-CHECK-R118.json`。
