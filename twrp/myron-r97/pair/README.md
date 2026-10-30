# R97 本地装配与 PID1 配对

这些工具接收完整 TWRP 编译的真实 `recovery.img`，在本地加入用户 R96 的准确模块，
再生成匹配的 PID1 和 `vendor_boot`。公开仓库不含这些私有模块、原厂镜像或手机日志。

编写本说明时，完整编译任务为 [40858026772](https://github.com/yuwenhua653/oppo_oplus_realme_sm8850/actions/runs/40858026772)，
完整编译已成功。原 R97 测试包实测 Android 与 REC 卡首屏。2026-10-30 的 fix1
修正新 REC 的 vendor_dlkm/etc 符号链接与 PID1 空目录要求的冲突；仅删这一记录，
原 R97 vendor_boot 和三个 REC pin 文件保持不变。新版 verify_candidate 强制检查两个
dlkm 根目录为空；prepare_recovery 仅识别并删除这条已确认的链接，其他非空布局会拒绝。
fix1 已通过真实生产 empty_dir 回归及最终镜像独立回读，仍待真机验证。
`test_injection.py` 使用 R95 构造临时测试输入验证装配链；它不编译 R97，
测试镜像不会保留，也不构成刷机包或真机测试结果。

## 输入与运行

从仓库根目录执行。需要 Linux、Python 3、cc、dpkg-deb、liblz4、OpenSSL。
`work/private/runtime` 是此前准备包中的 `prepared-runtime/`；
`work/private/vendor_boot_r96.img` 必须来自用户已确认系统正常的 R96 包。
`work/ci/recovery.img` 必须是本轮完整 CI 返回的带有
`R97-COMPILE-ONLY-NOT-FLASHABLE` 标记的镜像。

```bash
PAIR=twrp/myron-r97/pair
python3 "$PAIR/restore_toolchain.py" \
  --manifest "$PAIR/native-toolchain.json" --destination work/toolchain

python3 "$PAIR/prepare_recovery.py" \
  --candidate work/ci/recovery.img \
  --runtime work/private/runtime \
  --image-tools "$PAIR/image-tools" \
  --out work/assembled/recovery_r97.img

python3 "$PAIR/build_vendor_boot.py" \
  --vendor work/private/vendor_boot_r96.img \
  --recovery work/assembled/recovery_r97.img \
  --baseline "$PAIR/baseline-native" \
  --toolchain work/toolchain/restored-toolchain.json \
  --image-tools "$PAIR/image-tools" \
  --independent-reader "$PAIR/image-tools" \
  --out work/paired
```

输出目录必须是新目录，以免覆盖此前结果。任何校验失败都会停止。
`build_vendor_boot.py` 输出 `vendor_boot_r97.img` 及其同字节标准名称 `vendor_boot.img`；
后者用于 AVB 工具按分区名称回读。完整刷机包还需纳入 R96/R95 回滚镜像、
刷入和日志采集脚本，并核对实际机型与分区大小。

## 验证边界

- 从实际镜像解包检查 boot v4、无内嵌内核、LZ4 和唯一 CPIO 路径。
- `/init` 必须保留原 Recovery 链接 `/system/bin/init`。R96 的通用 `/init`
  3,356,672 字节 pin 保持原值；最终 ramdisk 合并关系仍需新版本真机验证。
- 126 个模块、全部加载控制文件以及 6 份公开脚本/RC 必须匹配精确 hash。
  源码编译标记只在成功本地装配时删除；缺模块或残留标记的镜像不能配对。
- 新 REC 的 `/system/bin/init`、`/system/bin/recovery`、主 init.rc 成套校验。
  旧诊断 REC 和 R95 的 pin 保留。整个 R96 normal Android 契约不变，
  `R94-MCA-TORCH-COMPAT-20261028-01` 不改为包版本号。
- 静态 AArch64 PID1 编译两次必须一致；镜像重装两次必须一致；独立解析器确认
  vendor_boot 只改变 `r36-init` 一条 CPIO 记录，DTB、bootconfig、模块和 payload 不变。
- 生产代码执行 ASan/UBSan 测试，包括串包、错误 pin、旧 REC 回滚和原 R96 挂载/失败路径。
- 静态配对通过并不表示电池、振动、解密或系统回归已完成真机验证。

只运行无需私有镜像的 native 测试：

```bash
python3 "$PAIR/test_pair.py" --baseline-native "$PAIR/baseline-native"
```

运行装配链测试需要私有 R95/R96 镜像和准确模块。这会创建并删除临时镜像，
不连接或刷写手机：

```bash
python3 "$PAIR/test_injection.py" \
  --r95-recovery work/private/recovery_r95.img \
  --r96-vendor work/private/vendor_boot_r96.img \
  --baseline-native "$PAIR/baseline-native" \
  --runtime work/private/runtime --project twrp/myron-r97 \
  --toolchain work/toolchain/restored-toolchain.json \
  --image-tools "$PAIR/image-tools" --independent-reader "$PAIR/image-tools"
```

修复原 R97 测试镜像（输入总 SHA 必须精确匹配已发布 R97）：

```bash
python3 "$PAIR/fix_boot_layout.py" --source work/private/recovery_r97.img \
  --vendor work/private/vendor_boot_r97.img --out work/fix1/recovery_r97_fix1.img
```

真实目录检查回归（只创建临时目录，无刷机）：

```bash
python3 "$PAIR/test_boot_layout.py" --native-dir "$PAIR/baseline-native" \
  --reader-dir "$PAIR" --r95-image work/private/recovery_r95.img \
  --r97-image work/private/recovery_r97.img --fixed-image work/fix1/recovery_r97_fix1.img \
  --out work/fix1/PRODUCTION-FIX1-TEST.json
```
