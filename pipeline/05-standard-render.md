# Deprecated：旧版标准分级生成

本文件属于旧版 `draft -> long_draft -> final` 状态机，**不再定义当前生产流程**。

当前生产路线不再要求按 `draft -> long_draft -> final` 晋级。现在的主逻辑是：

```text
低画质 seed screen
-> 用户选 seed
-> 1920×1080 / 73f 正式抽卡
-> 用户选 take
```

对应文档：

- `03-motion-and-seed-screen.md`
- `04-native-1080p-take.md`

历史 profile 仍可用于实验或诊断，但不得自动恢复为生产主状态机。