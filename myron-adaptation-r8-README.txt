Myron QCOM 平台源码适配 r8
========================

本轮新增
--------
在已成功构建并核验的 r7 基线上，接入两项源码候选：
  mca_platform_cp_class：充电泵接口层。
  mca_platform_buckchg_class：主充电器接口层。
这两个模块负责调用硬件后端；不等于已实现充电泵/主充电器芯片驱动。
r8 是累计源码包，直接用于固定 r1 准备后的干净工作区，不要先叠加 r7。

基线
----
第 11 轮成功构建：
https://github.com/yuwenhua653/oppo_oplus_realme_sm8850/actions/runs/37871124687
提交 4f58766752088a3c6717e7644524ae63b29e4d41。
该轮完整产物 ZIP SHA256：
a9980df0e404adba40a44da870d1646a7e3b5ab7dcd549de56f8052fb4eea72f
已验证 1,171 个清单文件；576 个模块文件、574 个模块名。
原厂 623 个模块名中有 504 个同名源码候选，尚缺 119 个。
这些是 r7 实际结果，不能当作尚未目标构建的 r8 覆盖率或功能完成度。
保留 ACK/QCOM 6.12.81、KMI generation 6、4 KiB，以及 r7 的 DT 和全部已接入模块。

来源与适配
----------
新增源码固定于 unmoved21/android_kernel_xiaomi_onyx：
8276ba954d8076303a5ae0f7b15d4092d66bdff6。
原始文件、版权、Git blob SHA1、SHA256、补丁与独立原厂 ELF 证据均有记录。
本轮恢复的 47 份原厂充电相关模块 SHA256 全部匹配已保存的 stock-inventory。

CP 按原厂 45 个回调槽位重排结构，补齐真实 vout2out_uvp 透传接口，
清除与该原厂接口集不符的公开源码扩展，并修复 DT/sysfs 边界和失败清理。
Buckchg 按原厂 89 个回调槽位重排结构，补齐 8 项真实转发接口，
修正 OTG bool 类型和 USB sense 错误回调检查；详情见本轮 evidence 与补丁。
Buckchg 增加 SRCU 注销接口，后续硬件后端释放前必须调用；CP 的后端
安全替换/注销协议尚未实现，接入芯片驱动前必须补齐，本轮不支持热卸载。
不通过伪造返回值、修改原厂 CRC 或重命名不匹配模块来增加覆盖率。

保留 r7 的 hwid/miev、xiaomi_touch 框架、MCA 基础层和四个接口模块，
包括身份初始化并发修复、协议 SRCU 注销、sysfs 回滚和已有缓冲区检查。
完整来源锁定在 drivers/source-lock.json；本包文件清单在 bundle-lock.json。

明确暂缓项
----------
PD：原厂与公开源码在回调顺序、PDO 数据布局及处理逻辑上存在差异。
公开源码还额外依赖 charger_partition_get_eu_model，而原厂 PD 没有此导入。
两个简单返回 0 的函数在原厂也存在，不能单凭它们认定为公开源码独有缺陷。
BC12：依赖 PD 接口，本轮不引入未经补齐的 PD 来满足链接。
charger_partition：含实际 SCSI 读写和分区选择，不能当作普通无副作用辅助接口。
FG：导出接口和数据结构尚未完整匹配。
platform_base：包含真实 I2C/子设备创建，公开源码有分配/错误处理问题，需进一步 DT 和硬件契约核验。
FT3683：匹配的控制器源码仍缺，xiaomi_touch 框架本身不提供触控控制器实现。
详细阻塞与证据在 drivers/evidence/r8-*，不以占位实现绕过这些缺口。

构建方式
--------
上传以下 3 个文件到原仓库对应位置：
  myron-adaptation-r8.zip
  myron-adaptation-r8-README.txt
  .github/workflows/build-myron-qcom-platform.yml
原有 r1 输入及固定源码版本继续保留。
GitHub Actions 选择 stage=full、jobs=2。
源码安装前运行已有及新增主机 C 测试，展开 QCOM Kconfig 并检查 DT 映射。
目标构建后检查真实 ELF 导出、依赖、参数、强导入及同次构建符号 CRC，并执行 DT 合并检查。
full-r8-module-gaps.json/.txt 从本轮真实产物统计剩余缺口。
主机测试使用内核服务模拟，不能代替目标内核编译或手机运行验证。

当前状态
--------
本包是下一轮源码构建输入；r8 完整目标构建和手机测试仍待完成。
flashable=false，hardware_tested=false；不包含可刷 boot/vendor_boot/dtbo/dlkm 或 AK3。
没有新增充电硬件节点启用，也没有调整电压、电流、功率或温控策略参数。
新接口表必须与后续从源码构建的消费者/后端配套，不能混装原厂 KMI5 模块。
硬件后端的注册/卸载生命周期、完整充电策略和事件数据 ABI、分区装配、
加载顺序与功能等价仍需逐项完成；本轮成功不代表已脱离全部原厂模块依赖。
