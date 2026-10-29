R97 Recovery 电池 / 振动测试包 — myron
打包日期：{{PACKAGE_DATE}}
构建记录：{{BUILD_URL}}
源码提交：{{SOURCE_COMMIT}}
镜像校验记录：{{IMAGE_VALIDATION_FILE}}

适用范围
仅用于本对话中当前 R96 系统已正常、使用 6.12.81 自编译内核的 myron。
设备树基于 lingqiqi5211/twrp_device_xiaomi_sm8850 的 twrp-16.0。
本包包含配套的 recovery_r97.img 与 vendor_boot_r97.img；实机功能尚待本轮验证。
系统沿用 R96 的模块和 R94-MCA-TORCH-COMPAT-20261028-01 运行时标识。
日志中保留该 R94 标识是预期行为，不代表刷错版本。

刷入
1. 完整解压，在本包目录打开终端，只连接这一台手机。
2. 进入 bootloader fastboot，而不是 fastbootd。确认当前槽位后，全程保持该槽位。
3. 依次执行。每一条必须显示 OKAY，出现 FAILED 时立即停止，不继续下一条：

fastboot flash vendor_boot vendor_boot_r97.img
fastboot flash recovery recovery_r97.img
fastboot reboot recovery

两张镜像必须配套刷入；不要单独将新 recovery 配现有 R96 vendor_boot 使用。
沿用当前 boot，不刷 boot、init_boot、dtbo 或 vbmeta，不切换槽位，不格式化 Data。
如果一张镜像刷写失败，不要重启到系统或 REC；保持 bootloader 并使用下面的成对回退。

验证顺序
1. 等待主菜单 / DLC 内容加载，检查显示、触摸、滑动与返回操作。
2. 记录 REC 显示的电量百分比。轻触菜单，检查原有触摸振动是否恢复；若设置中
   振动被关闭，先通过界面打开，再测试。模块存在不等于振动已经正常。
3. REC 内双击 CAPTURE-RECOVERY-R97.cmd，保留 results 中生成的 TXT。
4. 从 REC 菜单重启到 Android，确认系统能正常启动、电量百分比正常。
5. 手动检查手电筒、相机和原有快充，然后双击 CHECK-SYSTEM-R97.cmd。
6. 回传两份 TXT，并说明“菜单/DLC、触摸、REC 电量、振动、系统电量、手电筒、快充”的结果。

界面、电量与振动测试不需要刷 ZIP、格式化或恢复备份；本轮结果不能代替解密、备份恢复、
刷 ZIP 或 fastbootd 的独立验证。若解密失败，先记录界面提示，不用格式化 Data 排查。

日志采集
adb.exe 可放本目录、上级目录或 PATH，同时保留 AdbWinApi.dll、AdbWinUsbApi.dll。
采集只读，不需要手机已有 root，不执行 adb root，不加载/卸载模块、不重启设备，
不改充电、电池或振动硬件状态。每段有超时限制；无法读取或权限不足会保留部分结果。
REC 脚本需在 Recovery 中运行；系统脚本需进入 Android 并允许 USB 调试后运行。
CHECK-SYSTEM-R97.cmd 复用已验证的 R96 系统采集器，因此日志文件名仍以 r96-battery 开头。
日志可能包含设备及操作信息，请仅用于本次排查，不公开上传到源码仓库。

回退到本轮之前已确认正常的组合
进入 bootloader fastboot，在本目录依次执行；每条成功后再继续：

fastboot flash recovery rollback/recovery_r95.img
fastboot flash vendor_boot rollback/vendor_boot_r96.img
fastboot reboot

这会恢复 R95 的可显示 REC 界面和 R96 的正常系统；REC 电池/振动仍保持此前状态。
回退文件不是存在系统回归问题的 vendor_boot_r95.img。不要混用该旧 vendor_boot。
若 REC 无法启动或 ADB 不通，直接使用 bootloader 成对回退，无需等待日志采集。

离线验证与实机状态
{{VALIDATION_SUMMARY}}
尚未替你刷机或在设备上验证 R97；请以本轮实际结果为准。
