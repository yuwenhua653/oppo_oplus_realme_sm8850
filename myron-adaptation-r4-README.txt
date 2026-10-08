Myron QCOM 平台源码适配 r4
========================

本轮目标
--------
在已成功构建的 r1 + workflow 修复基础上，补齐 Myron DT 的基础组合，
并为 hwid / miev 加入公开源码候选。本目录与原始 r1 ZIP 并存。
原始源码锁、ZIP 校验、QCOM DDK 配置、GKI 模块收集及模块替代策略继续使用。
本轮以 myron-adaptation-r4.zip 上传；工作流先校验完整 ZIP 再解压本目录。

工作流顺序
----------
1. 解压并验证原始 r1 ZIP，同步固定提交，应用原有 workflow 修复。
2. install_hooks.py 严格校验当前 build_platform.py，再安装 r4 调用点。
3. build_platform.py 先运行 r1 prepare_workspace.py，再运行 r4 源码适配。
4. Bazel 编译及收集完成后，保留原有模块依赖检查，再执行 r4 产物检查。
5. DT 实际合并和驱动产物检查全部通过，构建状态才会成功。

运行已有 Myron QCOM platform source build，选择 stage=full、jobs=2。
dtbs / soc 可用于单独诊断；analyze 只检查依赖图，不会给出编译或合并通过结论。
每次 GitHub Actions 使用新工作区。不要在 r4 已修改的源码上重跑 r1 prepare；
r1 的精确输入校验会拒绝这类混合状态，应重新同步干净的固定版本。

设备树
------
补齐 canoe-audio、canoe-camera-v2、canoe-sde 三个 SoC overlay 的输出声明，
补全 Myron 音频需要的 pinctrl provider，并修正四个缺失标签引用。
保留 Myron 扬声器原有禁用状态，不整体引入通用 MTP 板级硬件配置。
构建后使用固定版本 libfdt 的真实 overlay apply 检查 Canoe v2 + Myron 组合。
该检查只证明所列 DT 组件能够按报告中的顺序解析和合并。
它不证明 OEM dtbo.img 表、启动时 overlay 选择、驱动绑定及设备运行正确。

基础驱动
--------
hwid / miev 来自固定的公开 Onyx 内核提交，原始文件与修改记录单独保存。
模块属于移植候选，尚未在 Myron 真机验证。
hwid 的 9 个导出接口匹配名称，但候选实现依赖模块参数，原厂还使用 socinfo
和额外 sysfs 接口；不能据此认为两者语义相同，也不能直接替换手机上的 hwid。
miev 提供事件记录和字符设备实现；移植修复及其限制见 drivers 内的说明。

产物和下一步
------------
所有产物继续标记 flashable=false、hardware_tested=false。
不生成 boot/vendor_boot/dtbo/dlkm 分区安装包，也不生成自动加载全部模块的清单。
现有手机使用 KMI generation 5，当前实验树为 generation 6，不能混入原厂旧模块。

后续仍需完成精确硬件语义核对、Myron 触摸/MCA/显示事件等驱动覆盖、
其余 DT 功能差异处理、分区和加载顺序装配，然后才能进入可回退的真机测试。
当前通过的“源码构建”“符号导出”“DT 合并”都不等于已完成 OSS 化。

第 8 轮构建后的 Kconfig 修复
-------------------------
修正 hwid/miev 两个 source 引用，加入 $(KCONFIG_EXT_PREFIX)。
高通 flattener 从工作区根目录运行，原先的裸 drivers/misc 路径解析错误。
增加编译前实际配置展开检查，确认两个 config 各出现一次，再启动 Bazel。
该检查复用固定源码脚本，不改变内核配置选项或模块实现。
