# Deprecated：旧版原生首尾循环与验证

本文件属于旧版以 `LoopLock` 原生闭环为核心的状态机，**不再定义当前生产主流程**。

当前策略：

- 原生 1080p take 先由用户选片；
- 完整导出帧列；
- MiniMax H3 常见尾部降速/冻结通过 Gate D 由用户决定最终保留帧；
- MAD / 光流 / uniformity 只提供辅助证据；
- keep list 确定后再插帧、超分和最终 QC。

对应文档：

- `04-native-1080p-take.md`
- `05-frame-selection.md`
- `06-interpolation-and-upscale.md`
- `07-final-qc-and-delivery.md`

旧文档中的具体帧号、MAD 数值和某次样片 workaround 只属于历史证据，不得迁移为新任务的固定规则。