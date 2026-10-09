Myron r9 批量源码适配包

本包为累计版本，在 r8 的完整构建基线上一次加入 8 个构建目标。
目标仓库：yuwenhua653/oppo_oplus_realme_sm8850
r8 基线提交：7cb1fb0a98a8102262237a6bdcfb8f0d01fc4ab6
r8 已验证构建：37886500082

本轮新增
1. mca_protocol_pd_class：51 回调、16 字节 PDO、原厂过滤与功率映射、多口、notifier、注册/注销。
2. mca_platform_bc12_class：双端口 BC1.2 接口和注销生命周期。
3. mca_platform_fg_ic_ops：原厂 67 导出、66 回调、536 字节结构及 2 个角色，新增 SRCU 注销。
4. mca_qcom_smem：原厂 SMEM item 0x51、36 字节映射、偏移 32 的真实状态读取。
5. mca_charge_mievent：61 个原厂事件、53 条插拔限流规则、8 条计时规则。
6. ir_spi：匹配原厂 raw SPI/LIRC 接口的红外源码，修复缓冲区并发及移除后的文件生命周期。
7. stm_st54se_gpio：匹配原厂 ST54SE GPIO 控制；probe 初始化、多 open、SET(0) 不操作、release 不改变 GPIO。
8. tls：ACK ARM64 GKI TLS 模块配置、模块输出清单与构建产物校验。

8 项中有 7 项加入 Xiaomi/QCOM DDK，共 23 个模块受严格导出、导入 CRC 等契约校验。
TLS 在 common GKI 树中启用，另行校验实际配置、ELF、ULP alias 和签名尾标记。
签名尾标记检查不代表密码学验签；全量模块依赖检查不代表硬件兼容。

共同修复
- 修正 adapter_power_cap 的 min_voltage/max_voltage 字段顺序，并重编译本轮全部源码消费者。
- sysfs create_files 失败时只回滚本次已创建项，新增配套 remove_files；使用设备引用并避免持锁等待回调。
- 修正 PD notifier 注册前的初始化顺序，避免覆盖已发生的通知状态。
- FG reboot 阈值完整传递 u8，不能根据相同 KCFI 标识错误转换为 bool。

证据和验证
- 新增接口按原厂 ELF 的导出、回调槽、类型标识及必要的实际指令交叉核验。
- 主机测试编译真实候选 C，模拟内核服务，覆盖错误路径、边界、并发和资源清理。
- 独立审查复核 PD 功率/PDO 行为、FG、SMEM 和事件表、IR/ST54 行为。
- 所有外部源码固定仓库/提交/blob/SHA；安装脚本拒绝未知源码状态，验证整包 SHA 后再解压。
- r9 的目标内核编译尚未运行，只有 GitHub Actions 完整构建成功后才能确认其 DDK/内核集成。
- host-tests 和静态二进制合同均不等于手机实测。

设备树绑定核验
TEE 共享内存桥在此高通版本中由 qcom_scm_probe 初始化，不依赖旧的独立 DT alias。
r9 全量构建后将检查实际 SCM ELF 的初始化调用及固定源码，避免把仅存在导出符号误当成功实现。
Novatek 显示接入和两个 bark 节点仍有真实实现缺口；binding audit 成功只代表证据核对完成，binding_complete 保持 false。

尚未补齐
Wireless 平台类已记录 66 槽/528 字节布局，但仍有无法证明的类型与参数差异；未纳入候选。
面板通知类缺少匹配的 HBM 事件链和安全注销机制；未纳入候选。
FG/充电芯片、充电策略、ADSP 协议、FT3683 触控、完整 NFC、其他 OEM 服务等仍需继续适配。
mtdoops 原厂版带额外 OEM 依赖，不能仅打开 ACK 配置冒充；gpio_mi_t1 仍待行为及生命周期修复。
sysfs remove_files 只用于成功创建事务的所有者；整个 mca_sysfs 类的热卸载/重载生命周期未在本轮完成。
不得把本包的新源码模块与旧版原厂二进制模块混用，或修改 vermagic/CRC 伪装兼容。

使用方法
上传 myron-adaptation-r9.zip、myron-adaptation-r9-README.txt 和
.github/workflows/build-myron-qcom-platform.yml 到原仓库相应位置。
保留原有 r1 集成文件；r9 已包含此前累计适配，不需要在 CI 里叠加安装 r8。
运行 Myron QCOM platform source build，选择 main、stage=full、jobs=2。
构建后检查 full-r9-status、driver-contracts、module-gaps、dt-merge、binding-audit、tls 报告。

flashable=false
hardware_tested=false
本包没有完成 boot/vendor_boot/DTBO/DLKM 的整机装配，不是直接刷入手机的安装包。
