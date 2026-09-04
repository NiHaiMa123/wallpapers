# History — NON-NORMATIVE Historical Evidence

> [!WARNING]
> 本目录中的文件是阶段性计划、实验方案和当时的“定案”记录，**不是当前生产规范**。

本目录是全项目唯一的 NON-NORMATIVE 历史归档点。当前规范入口见 [../AGENTS.md](../AGENTS.md)、[../pipeline/README.md](../pipeline/README.md)、[../contracts/README.md](../contracts/README.md)。

## 目录内容

| 文件 / 子目录 | 内容 |
|---|---|
| `VALIDATION_HISTORY.md` | 历史调研、逐阶段验证数据、失败路线与 SHA-256 证据索引 |
| `plan2.md` | 变速/equalize/remap 链路修复与 65f 定稿记录（2026-09-04 封版） |
| `plan.md`、`plan_v2.md` | 早期循环视频与 VFI 验证计划 |
| `H3_1080_LOOP_STRATEGY_NOTES.md` | 镜像回放循环方案的当时定案（已被 same-image anchor 取代） |
| `H3_1080_STREAMING_OUTPUT_PLAN.md` | 1080p 逐帧流式输出实施计划（已执行完毕） |
| `图生视频_Gemini执行手册.md` | 旧 Gemini 执行手册（镜像路线时代） |
| `帧数速度表.md` | run60k 逐帧 MAD 手记 |
| `local-notes/` | 其他一次性本地笔记 |
| `prompts/` | 历史 prompt 迭代史（CRYSTAL_LOCK V1–V7、FIGURINE V8–V10、keqing 系列与 generated 版本） |

## 解释规则

本目录中出现以下措辞时：

```text
定案
默认
推荐
锁定
必须
当前上限
```

只表示 **该文档创建/执行时的结论**。它们不能覆盖当前 Contract。

例如：

- `H3_1080_LOOP_STRATEGY_NOTES.md` 曾把镜像回放写成“已定案”；当前生产主线不再由该结论定义。
- `H3_1080_STREAMING_OUTPUT_PLAN.md` 记录了特定日期、机器、ComfyUI 实例和 RAM 边界；这些数据可以作为实现证据，但端口/阈值/runner 语义不能自动升级为当前规范。

## 正确用途

历史文档可以用于：

- 理解某个实现为什么存在；
- 找失败/性能证据；
- 设计 regression test；
- 对当前 Contract 提出 `CONTRACT_REVIEW_REQUIRED`。

错误用途：

- 直接根据历史文档改 pipeline；
- subagent 根据“旧定案”覆盖当前 Contract；
- 把某次机器上限写成永久生产目标；
- 把历史 workaround 恢复成默认路径。

如果历史证据确实证明当前 Contract 有问题，按 [../contracts/00-governance.md](../contracts/00-governance.md) 上报，由主 Agent 修改 Contract。
