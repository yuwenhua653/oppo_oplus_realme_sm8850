Myron r15 — 新增 charger_partition 存储提供者

基线：仓库提交 9005a1002c2358550c7ece8014bd42e855f256f3 的 r13 源码包。
这是一个实际新增源码模块。DDK 注册数 49 → 50，受管理模块数 45 → 46，
前置新增模块编译列表 22 → 23。源级数量不等于已经生成的新 .ko 数量。

为什么先做它
原先排除的 11 个服务中，charger_partition 是另外 10 个策略/业务模块的
直接或间接依赖。原实现使用 drivers/scsi/sd.h 私有布局、固定分区号、
直接 SCSI 命令和启动重置逻辑，无法直接作为当前内核的可靠提供者。

本次实现
- 使用固定 ACK 6.12 源码已有且 r13 vmlinux.symvers 实际导出的公开 block API。
- 保留现有公共头不变及其 19 个导出函数，包括原有 hcsd 拼写；没有空返回实现。
- 真正读取现存记录，真正执行完整块读改写与 fsync；保留未修改字段及剩余字节。
- 同一任务配对 alloc/read/write/dealloc；其他任务不能借用全局缓冲区。
- 短读、短写、刷盘失败向上传递。结果不明的写操作使后端停止后续 I/O；
  不在错误后自动清除持久 busy 标志，不伪报成功。
- module/task 引用保证活动事务有效；设备移除后借出的静态缓冲区直到 dealloc
  仍然有效，后续磁盘访问返回错误。
- 仅接受显式路径及匹配的 GPT UUID、charger 分区名、4096 逻辑块、足够容量、
  指定版本及已初始化的有效头。没有猜测这些参数的值，没有创建或格式化分区。
- 默认只读；读取不会切换磁盘上的 availability 字段。allow_writes 默认 false，
  参数不能在运行中通过 sysfs 改写。设置为 true 也不代表已完成原厂协议确认。

仍然未完成
1. 尚无 Myron 实际分区 UUID、头部版本和数据样本的对照，Onyx 结构布局只作为
   当前接口的已知源码格式，并未证明与手机上的格式相同。
2. availability 字段不是跨处理器的原子锁。Linux 的独占打开和写入限制不能阻止
   ADSP/UEFI 直接访问存储。真机允许写入前必须另行确认固件互斥/一致性机制。
3. 此模块提供存储 API。原厂政策 sysfs、启动复位和策略事件广播未迁入；
   不能声称原厂 charger_partition 的全部行为等价。
4. 原有 compatible 字符串保留并生成 OF 别名，但没有添加/启用 DT 节点，
   没有确认设备 probe、init 集成或原厂加载顺序。
5. 另外 10 个策略/业务模块继续排除。特别是它们的读取失败处理、策略默认值
   和接口注销还需要真正适配，不能只靠此模块出现就批量启用。

验证入口
python3 drivers/tests/r15-partition/run_partition.py drivers/payload
python3 fastcheck_r12.py --reports /tmp/myron-r15-fastchecks

主机测试编译完整生产 C 文件，在模拟内核 I/O 边界下运行，包含真实并发竞争和
UBSan；它不是手机内核运行，也不代替目标编译。
CI soc/full 将真实编译 charger_partition DDK target。收集后先执行原有完整驱动
合同验证，再运行 drivers/verify_partition.py，要求恰好一个新模块、19 个导出、
准确参数/别名、同次构建 CRC、独占导出提供者。旧 r13 产物会明确失败。

集成边界
本包基于已在仓库中的 r13，未混入单独交付的 r14 加载依赖修复附加包。
历史 assembly/ 草案保留原状；离线装配应继续使用此前已交付的 r13 五模块刷新
清单。本次新模块没有合格的完整构建二进制前，不加入分区复制映射。
未生成 modules.load、分区镜像或刷机包。flashable=false。

本次实际结果：30 组主机行为检查通过；完整生产 C 已使用固定 ACK 源码和真实内核头，
以 Clang 18.1.3、-Werror 编译为 AArch64 .o。19 个导出和 25 个核心导入名称均已核对。
这是目标文件检查；CI 使用 Android Clang 19，配置差异已记录。没有生成最终 .ko，
没有完成本次全量 DDK 构建或最终 CRC 验证。
