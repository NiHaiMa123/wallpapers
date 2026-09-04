# Deprecated：旧版原生 1080p 与 4K 扩展阶段

本文件保留路径兼容，但**不再作为生产主流程的“后置扩展”**。

当前 1080p 已提升为正式生产阶段，而不是 final 之后的附加升级：

- `04-native-1080p-take.md`：1920×1080 / 73f 正式抽卡 + Gate C；
- `05-frame-selection.md`：完整帧列 + Gate D；
- `06-interpolation-and-upscale.md`：插帧 + 超分；
- `07-final-qc-and-delivery.md`：最终 QC。

旧文件中具体 0224/0227、draw02、63–71、19.2fps、历史 RAM 探针等属于实验/历史结论，应迁移到 `VALIDATION_HISTORY.md` 或 plans，不得作为当前新任务默认参数。