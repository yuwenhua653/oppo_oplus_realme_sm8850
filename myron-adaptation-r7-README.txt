Myron QCOM 平台源码适配 r7
========================

本轮范围
--------
在 r6 全部源码候选上新增 4 个 MCA 框架/接口模块：
  mca_protocol_class、mca_protocol_qc_class、mca_platform_loadsw_class、mca_charge_interface。
保留 r6 的 xiaomi_touch 框架和 7 个 MCA 基础模块，并修复 mca_hwid 首次初始化的并发问题。
r7 为累计包，直接用于固定 r1 准备后的干净工作区；不要依次叠加 r5/r6/r7。

基线
----
已验证成功的第 10 轮提交：e23ec6180094afb098528e2f74dd4afa73010ca9。
该轮产物 ZIP SHA256：6e4d101f507c3f8ba64ac37045fd53e1ee05ce3314578507a4c20ebdaea70659。
1,147 个清单文件；564 个模块文件、562 个模块名；原厂 623 名中有 492 个同名候选。
上述数字来自第 10 轮，不能当作尚未完成目标构建的 r7 覆盖率。
保留 ACK/QCOM 6.12.81、KMI generation 6、4 KiB、现有 Myron DT 和 hwid/miev 适配。

来源和修正
----------
新增 MCA 源码固定于 unmoved21/android_kernel_xiaomi_onyx
  8276ba954d8076303a5ae0f7b15d4092d66bdff6。
原始文件保留版权、Git blob 和 SHA256；每个安装文件另有哈希。
根据 Myron 原厂 ELF 修正 protocol、QC、charge_interface 回调结构的字段顺序。
charge_interface 使用原厂已确认的 battery-status 事件 16，未擅自重排共享事件枚举。
protocol 增加有明确记录的 unregister 导出，使用 SRCU 等待回调结束；QC remove 先注销。
loadsw 修正 DT 数量/索引边界、失败清理、sysfs 空指针及错误传播、ibat 输出字段。
charge_interface 修正 sysfs 输入输出边界、无后端访问及整数解析错误传播。
mca_hwid 在同一互斥锁内完成初始化再发布，保持 40 字节布局和原有身份映射。
修复 mca_sysfs 创建链接失败时未撤销已建属性组的问题，避免失败 probe 遗留回调。
没有引入充电 IC、PD/ADSP 协议实现或电压、电流、功率、温控策略参数。

r6 内容
-------
xiaomi_touch 来自 MiCode/vendor_xiaomi_proprietary_touch-driver
  c286ab85f4982c9b5967e18405f4e2da0332ce4d。
仅背移官方 57d9a0225b031f4b444251117f3ecc9deae71128 的两个 MIEV 上报函数。
保留实际 UAPI、官方 Canoe 的 TOUCH_THP_SUPPORT / TOUCH_FOD_SUPPORT 选项。
MCA 基础层为 sysfs、event、log、parse_dts、voter、workqueue、hwid。
这些模块的来源和原有修正证据继续保留于 drivers/evidence/。

构建方式
--------
仓库根目录放置 myron-adaptation-r7.zip 和同名 README，替换随包提供的
.github/workflows/build-myron-qcom-platform.yml；原有 r1 文件和源代码固定版本保留。
GitHub Actions 选择 stage=full、jobs=2。
构建前执行实际 C 的身份/并发/缓冲区/接口测试，展开 QCOM Kconfig 并检查 DT 映射。
构建后检查真实 ELF 导出、依赖、必要导入、参数、同次构建的符号 CRC，以及 DT 合并。
full-r7-module-gaps.json/.txt 从本轮实际产物重新统计模块缺口。
主机测试使用内核服务模拟，不等于目标内核编译或手机验证。

当前边界
--------
本包是源码适配输入，flashable=false、hardware_tested=false。
不包含 boot/vendor_boot/dtbo/dlkm 或 AK3 刷包。
原厂 KMI5 模块不能混入此 KMI6 构建，没有篡改原厂 CRC 强行加载。
FT3683 控制器匹配源码仍未找到。原厂 ELF 路径含 p11u/focaltech_3683，
版本 FT3683:2025.07.17-001；其他 FT3683U/G 变体尚未证明等价。
完整事件表、PD 数据结构、各硬件后端注册/卸载生命周期、固件协议及充电行为仍待验证。
分区装配、加载顺序、驱动功能等价及完全脱离原厂模块依赖尚未完成。
