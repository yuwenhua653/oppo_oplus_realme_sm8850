R78 显示亮度源码候选

本候选修复已知 HWC 逻辑亮度接口缺口，不改面板 DCS、物理量程或 DT。
已有 R65 证据：HWC max=255，算法输入10/72、输出15/29，恰等于标准背光brightness；标准背光max=16383。缺失的max_brightness_clone使用户滑块进入错误算法输入域是高可信定位，尚无专有HWC精确二进制控制流和新实机结果。

1. 精确恢复当前实际 msm_drm.ko 所对应的9个R28有效源码文件，逐一匹配既有manifest postimage哈希；保留DP aux NULL开机修复、R21/R23/R25/R27诊断/启动行为。
2. 仅在成功绑定的、真实primary panel（全局只允许一个owner）上注册，校验panel_of_node和实际选择的panel_node一致、面板名称符合Myron。不给其他显示设备硬套接口。
3. mi,max-brightness-clone存在则严格校验一个u32、值1..INT_MAX；不存在则明确采用MiCode同SM8850 popsicle-w-oss@6def61b29a39710078287416afd3b62f43729c37逻辑默认16383。该默认不是声称Myron DT显式设置，逻辑域亦不是物理DBV的别名。
4. /sys/class/mi_display/disp-DSI-0/max_brightness_clone只读；brightness_clone合法十进制写入被上限截断并缓存，向已订阅客户端发送真实BRIGHTNESS_CLONE事件，绝不执行DCS或再次缩放物理背光。
5. /dev/mi_display/disp_feature只实现精确VERSION(1.0)、primary clone事件订阅/取消订阅、read、poll及兼容32位ioctl；其他ioctl ENOTTY，其他事件 EOPNOTSUPP。不假装支持HBM、doze、FOD、panel read/write等接口。参考UAPI request=12B，event=16B，type=5。
6. 真正mi_display类及disp_feature字符设备采用原厂虚拟父子拓扑，复用现有ueventd的/dev/mi_display规则，不使用misc设备猜测节点路径。每客户端队列4096B/256条、最多32客户端；满队列丢弃新事件保持既有队列，和参考驱动一样保留缓存更新。解绑使等待者醒来、poll HUP/ERR、read/ioctl ENODEV；打开文件持kref和模块引用。移除sysfs后才释放注册持有的对象，回调不会解引用失效panel。
7. 兼容层注册失败保留已成功的显示启动、明确输出错误日志。任何后续刷机都需先检查真实编译KO、ABI/provider覆盖，然后把音频和亮度合并做一次实机验证。

本目录含完整preimage/payload、R28有效源码、应用工具、写锁、同SM8850接口参考和必要的主机回归。运行：
  python3 apply.py
  python3 tests/run_tests.py
  python3 apply.py --workspace /绝对路径/ACK工作目录
  python3 apply.py --workspace /绝对路径/ACK工作目录 --verify

主机测试编译真实候选C函数体，内核API由明确的单线程替身代替；覆盖并不替代真实内核编译、并发/设备验证。ASan/UBSan启用，当前沙箱无法读取LSan所需/proc/task，因此关闭LeakSanitizer；资源释放另有计数和打开FD解绑断言。

运行权限已有精确vendor参考：composer-service.rc在post-fs-data对两个clone节点chown system:system并chmod0664，composer服务user system；兼容层在早期bind提供相同虚拟拓扑，不额外修改权限。该参考rc尚未证明与手机当前rc字节一致，最终仍在合并实机验证中确认。

R78 fix3：内核CI已进入显示模块编译，发现旧no_llseek符号在锁定6.12内核中不存在。
生产file_operations改用NULL，保持原有不可seek语义；不使用返回假成功的noop_llseek。
删除宿主替身中掩盖错误的no_llseek宏，并把llseek字段恢复为函数指针类型。
新增回归读取锁定内核原始声明与VFS实现，检查旧初始化器编译失败、当前初始化器通过及seek返回-ESPIPE。
该回归仍为局部宿主验证，完整内核编译、ABI与实机结果以相应后续验证为准。

当前状态：源码候选，内核CI修复中、未生成可刷镜像、未操作手机；无需root。不重复R65采集。
