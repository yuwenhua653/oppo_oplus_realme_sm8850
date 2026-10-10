Myron r12 累计源码批量接入包

目标仓库：yuwenhua653/oppo_oplus_realme_sm8850
已复核基线：Actions run 14 / 38020123306
基线提交：9a1c45032ad95fe2cce28e011f1b99314cf35e73
实际基线内核：6.12.81-android16-6-maybe-dirty-4k

本轮一次新增 22 个源码编译候选：18 个 MCA 服务 + 4 个充电/电量 IC。
这是一份累计源码更新，尚未得到本轮目标编译结果，不是可刷机包。

新增 IC：hl7603、sc8581、bq27z561、sc96281_charger。
新增 MCA 服务：
mca_adsp_glink、mca_bmd、mca_business_battery_comp、mca_business_misc_comp、
mca_connector_antiburn、mca_ibat_ocp_monitor、mca_lpd_detect、mca_path_control、
mca_pd_auth、mca_platform_base、mca_platform_wireless_class、mca_qcom_panel、
mca_qcom_subpmic_proxy、mca_strategy_class、mca_strategy_fg_class、
mca_vbat_ovp_monitor、mca_wireless_revchg、qcom_adsp_pd_protocol。

主要改动
- 加入真实来源锁定的源码、DDK 依赖、Kconfig 和模块合同；共检查 45 个适配模块，
  注册表总数 49（另 4 个沿用 r1 校验）。无空壳模块或强改 CRC。
- 修复 QTI 电池 getter 错把 MCA 私有数据当成 QTI 结构读取的问题；
  对非 QTI power_supply 返回 -ENODEV，完整保留引用释放及错误传播。
- 消除 QTI/MCA 导出重名；保留 QTI 原公共符号，MCA hboost 使用独立名称。
- 保留 r10 PD 修复和旧 ABI 合同；加入 QTI 三个公共函数的 run14 KCFI 类型门禁。
- 内置 run14 已验证的 69 个额外 DTBO 构建输出保留规则；未改变诊断合并成员/顺序。
- CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING=n，新增 IC 固件入口及无线自动升级入口默认拒绝。

使用方法
1. 解压交付包，将 repo-files 下三个文件放到原仓库对应位置：
   myron-adaptation-r12.zip
   myron-adaptation-r12-README.txt
   .github/workflows/build-myron-qcom-platform.yml
   注意显示隐藏目录 .github；内层 myron-adaptation-r12.zip 整个上传，不要解压替代它。
2. 保留原仓库 r1 文件。工作流已经引用累计 r12，不需再安装 r10/r11 或独立 retention 包。
3. 运行 Myron QCOM platform source build：branch=main、stage=full、jobs=2。
4. 结束后提供 reports 和 source-build-full 两个产物。本轮须通过严格源码预检、
   目标 ELF 导入 CRC/唯一导出检查及回调 ABI 门禁，才可开始下一轮装配评估。

已验证范围
- 250 项实际回调声明主机类型检查：IC 150 + MCA 服务 100。
- 15 项抽取最终 QTI getter 的 C 分支测试及 UBSan；已接入 CI 前置测试。
- 当前源码离线预检、旧源码保留检查，以及 run14 实际 ELF 上的增强门禁回归。
- 上述检查不等于新增模块交叉编译成功，也不证明硬件运行正确。

尚未完成
- FT3683 控制器源码缺口和 OEM 显示接入；xiaomi_touch 框架不能替代触摸控制器。
- SC96281 的 FOD/Hall/pinctrl、SC8585 的多模式 UVP、完整充电策略和 hboost 事件桥接。
- QTI getter 现在安全拒绝异类电源，但尚未提供 MCA 电池属性桥接。
- 原厂 6.12.23 模块不能直接混入新内核；r11 离线装配只对应 run14，
  本轮模块通过编译后仍需重新核对依赖和布局。本包不生成镜像或实机自动加载名单。

审查细节：drivers/evidence/r12-hardware/FINAL-INTEGRATION.zh-CN.txt
源码范围：drivers/source-lock.json 的 new_r12_modules / r12_excluded_reference_modules。
new_target_build_verified=false
hardware_tested=false
flashable=false
