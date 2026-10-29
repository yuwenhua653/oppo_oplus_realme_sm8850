# myron R97 TWRP 源码适配

基于 `lingqiqi5211/twrp_device_xiaomi_sm8850` 的 `twrp-16.0`，固定提交
`907b78a804f5a47c4ccd66da0e5dd776cefc077d`。TWRP 核心固定为
`TWRP-Test/android_bootable_recovery` 的
`8a58fc3b586b8a908337fa87529cfbbb119ec7bb`，该版包含 input FF 振动后备实现。

本修改只面向当前 myron / 6.12.81 R96 自编译内核运行时，不是多机型通刷树。
用户已确认 R96 系统正常；本轮 REC 源码尚未经完整 TWRP 编译和实机验证。

## 修改内容

- 用 R96 的准确字节准备显示、触摸、qcom_hv_haptics、ADSP 和完整 46 项 MCA 模块。
  逐文件验证全部 295 项输入，再选出 126 项依赖闭包；其中 19 项为新增 UI 加载，
  57 项为新增硬件加载，其余由 vendor_boot 首阶段提供。
- 先启动显示/触摸和 REC，随后独立初始化电池与 ADSP。失败写入 `/tmp/r97-*.log`。
- 停用原厂模块扫描、OEM 振动 HAL 和 touch raw 报告服务；使用 TWRP 自带 input FF。
  模块存在不等于物理振动已验证。
- 不再写死 remoteproc1；按名称、固件、DT 和规范路径定位 ADSP，只允许一次 offline→start。
  去掉原厂 boot_adsp/ssr 强制重启流程。
- Health 服务等待实际 battery 节点、驱动归属、present 和合法容量；不伪造电量。
- 保留 R96 的系统运行时身份 `R94-MCA-TORCH-COMPAT-20261028-01`；不修改系统 MCA helper。

## 准备与应用

需要 Linux Python 3、git、e2fsprogs/debugfs、binutils/readelf、liblz4 和 make。
在正常的 TWRP 16 源码目录中，把设备树检出到 `device/xiaomi/sm8850`，
把核心检出到 `bootable/recovery`，分别使用上面的固定提交。
保留现有本地修改，建议使用独立源码目录。

从此前 R96 包解压 `vendor_boot_r96.img`。其 SHA256 必须为：

`40c62b7f726b011c59149cb9c22ec24a60beafddf4f6ed702506de29ccd03eb3`

在本适配源码目录执行：

```sh
python3 prepare_runtime.py --vendor-boot /path/vendor_boot_r96.img --out /path/r97-runtime
python3 validate_source.py --runtime /path/r97-runtime
python3 test_runtime.py
python3 apply.py --device /path/twrp/device/xiaomi/sm8850 --recovery /path/twrp/bootable/recovery --runtime /path/r97-runtime
```

脚本在写入前核对原文件 Git blob SHA；输入被改过或重复应用会拒绝。
下载包如包含 `prepared-runtime/`，可使用该目录代替重新提取，应用时仍会校验模块字节。

然后在 TWRP 源码根目录运行本目录的 `build-candidate.sh`。
使用 `repo manifest -r` 留存实际完整源码版本；本包仅固定直接改动的两份仓库，
不宣称整个 Android manifest 的所有远端分支已冻结。

## 编译后必须配套处理

R96 PID1 严格校验 `/init`、`/system/bin/recovery` 和主 init.rc。
本源码新编译的 REC 会改变这些字节。**不能直接把新 recovery.img 配现有 R96 刷入。**
编译后需根据真实产物生成配套的 recovery 专用 pin，重新编译 PID1 并打包 vendor_boot，
保留正常 Android 的 init/payload/module/build-id 契约；再进行独立解包回读与正常/REC
分支回归测试后才能发布刷机包。不能跳过 hash 检查，也不能把系统运行时标识改成 R97。

当前交付为源码修改和准备脚本，不含已通过发布校验的 R97 recovery/vendor_boot 镜像。
源码 CI 只运行 shell/Make/加载控制流测试，**成功不代表完整 TWRP 编译成功**。

## 日志

REC 中读取 `/tmp/r97-ui.log`、`r97-hardware.log`、`r97-battery.log`、`r97-adsp.log`，
以及 `getprop sys.r97.battery.ready`、`getprop twrp.adsp.ready`、`/proc/bus/input/devices`。
对 GUI、电池显示、振动、解密、USB 以及重启后 Android 电池/手电筒逐项实机确认。

公开源码不包含用户手机日志、原厂镜像或认证信息。准备模块时只读取用户已有的 R96 镜像。
