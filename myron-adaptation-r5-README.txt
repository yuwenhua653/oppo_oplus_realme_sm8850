Myron QCOM 平台源码适配 r5
========================

基线与本轮目标
--------------
基于第 9 轮成功的提交 01538529e2f52d9a91a60650b7aa40094e2ab137。
保留 ACK/QCOM 6.12.81、原有 Myron DT 合并修正、miev 和所有 r1 修复。
本轮修正 hwid 的机型识别，并在每次 full 构建后生成批量驱动缺口报告。

hwid 适配
---------
使用 socinfo_get_id() + 启动参数 project，按原厂证据识别 SoC 660 的项目；4 对应 myron。
移除未被原厂启动参数使用的 project_name。硬件版本、ADC 继续由启动参数提供。
保留九个导出接口；DDK 接入 socinfo 依赖和头文件；Kconfig 依赖 QCOM_SOCINFO。
新增模块门禁防止 socinfo 变成配置关闭时的空实现，并检查四个 uint 参数契约。
/sys/hwid 生命周期缺少真机观测，本轮不新增持久 sysfs 节点。详见 drivers/README.zh-CN.txt。

批量驱动核对
------------
coverage/stock-inventory.json 记录 623 个原厂模块名、617 个已加载名及加载集合。
不含序列号、系统指纹或原始手机日志。此前缺少的原始文件已由 vendor_boot 补齐。
每轮 full 编译后从真实产物及选用策略重新计算候选覆盖、依赖差异、硬件分组和加载阶段缺口。
报告 full-r5-module-gaps.json / .txt 自动进入 Actions reports 和编译产物目录。
同名候选不代表原厂功能等价；缺名也不等于网上无源码或必须照搬原厂拆分方式。
normal/recovery 加载集合只作参考，不直接生成自动加载清单或假定原厂顺序。

操作
----
上传 myron-adaptation-r5.zip 和对应 build-myron-qcom-platform.yml。
运行 Myron QCOM platform source build，选择 stage=full、jobs=2。
r5 直接应用于固定 r1 准备后的干净工作区，不是在 r4 已修改目录上叠加。
工作流先校验 ZIP/所有 payload，再安装精确哈希保护的 build_platform 调用点。
随后依次执行主机 hwid 检查、源码适配、真实 Kconfig 展开、DT 输出映射检查、
Bazel 编译、模块依赖检查、DT 实际合并、hwid/miev CRC 检查和批量差距报告。
保留原 r4 ZIP，旧构建仍可追溯；本次工作流只使用 r5 包。

验证边界与下一批
----------------
本包始终 flashable=false、hardware_tested=false，不生成 boot/vendor_boot/dtbo/dlkm 或 AK3。
实验树 KMI generation 6，手机当前使用 generation 5；原厂旧模块不能混装。
新的 hwid 是待真机验证的适配，socinfo readiness、sysfs 和所有消费者行为尚未证实。
下一批按报告推进触摸与显示通知接口、MCA 与充电温控等源码覆盖，再做分区与加载依赖装配。
编译通过、导出匹配、DT 合并、同名覆盖均不等于整机 OSS 化完成。
