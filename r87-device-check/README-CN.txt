R87 完整 MCA 接管测试

先确认压缩包内有 vendor_boot_r87.img 和正常 R84 回退镜像 vendor_boot_r84.img。
手机进入 bootloader fastboot，在本文件夹运行：

fastboot flash vendor_boot vendor_boot_r87.img
fastboot reboot

这里只刷 vendor_boot，不刷 boot、dtbo 或物理 vendor_dlkm，不清数据。首次接管测试仍需实机验证充电和功率。

若无法正常开机或出现明显异常，回到 bootloader fastboot，用同包正常 R84 回退：

fastboot flash vendor_boot vendor_boot_r84.img
fastboot reboot

正常开机后，先检查亮度、声音、Wi-Fi、相机、插电是否回锁屏。用原装充电器和线观察约两分钟，记录电量、充电器型号、功率计输入功率，以及是否反复亮屏或发出充电提示音。

需要反馈时采集一次即可，免 root。开启 USB 调试并接受电脑授权；Windows 把采集文件放在 adb.exe 所在目录（或 adb 已在 PATH），双击 collect-r87.cmd，发送生成的 r87-check.txt。
Linux/macOS 在此目录运行：

adb shell sh -s < collect-r87.sh > r87-check.txt 2>&1

能使用无线 ADB 时可保持原装充电器连接后采集；电脑 USB 供电时，报告中的即时电源读数对应电脑 USB，不能作为原装快充功率。功率以你记录的功率计读数为准。

采集只读取接管状态、驱动绑定、电源原始数值、认证文件权限、batterysecret 运行状态及有界系统诊断。不会读取认证摘要或改充电/认证参数；缺失、权限不足和超时会记入报告。电压、电流保留原始单位和符号，不换算成功率。
