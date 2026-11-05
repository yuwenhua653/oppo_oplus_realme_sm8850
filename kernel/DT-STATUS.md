# 原生 Kbuild DT 接入状态

目标是 Redmi K90PM / myron。原始 R123 DTS 的真机功能验证记录仍保留在
DT-VALIDATION-R123.json；该记录不能替代当前原生内核的真机测试。

原生 DTS 分支 b84c303a85a8f8b73d7fa3d4df37b57a601dd5b1 保留 R123 的
DTS 内容，只增加原生构建选择。32 个输入通过 Kbuild dtbs 编译，并与同工具链的
参考输入逐字节一致。音频、相机 GPIO、振动和闪光灯修正均保留。

设备使用标准 kernel.mk 的 DT 镜像 hook，消费原生 dtbs 产物。镜像装配继续保留
八个基底的原顺序、板级 overlay、两条有限 foundry-zero 匹配，以及 ADSP 1→6、
CDSP 1→11 的 FastRPC 子节点顺序修正。仅移动完整子树，不改变属性或 phandle。
合并后的八个变体逐一接受提供者及关键属性检查。

不再提供 MYRON_DT_MODE 切换或 myron-source-dt-check 构建目标；正常的
m dtbimage dtboimage 即走上述源码流程。详细编译方式见 README-CN.md。
完整 ROM、最终 AVB/分区打包及新内核真机测试仍需完成。
