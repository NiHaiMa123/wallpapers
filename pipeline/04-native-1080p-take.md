# 04 原生 1080p / 73帧正式抽卡

本阶段在用户已经选定 video seed 后，运行高成本正式候选，并重新做人审。

## 目标规格

正式候选目标为：

```text
1920×1080
73 frames
silent
```

H3 内部空间尺寸如 runner 需要采用 `1920×1088 -> 1920×1080`，以当前已验证 runner / preset 为准，不在文档中硬编码替代实际脚本校验。

## 运行前

必须重新做 runtime preflight：

- API 可达；
- 实际 ComfyUI 版本正确，不只相信端口名；
- 队列为空；
- required nodes 存在；
- 输入图路径/哈希正确；
- Qwen、LLM 和其他 H3 已卸载；
- RAM/VRAM 有足够余量；
- 保留 runner 的 RAM 熔断；
- 输出与报告使用唯一名称。

## 正式抽卡

锁定：

- 用户选定静态图；
- motion prompt；
- 用户选定 video seed；
- LoRA 和主要 motion 参数；
- 固定镜头；
- 目标 1080p / 73f profile。

允许因为跨会话非确定性出现多个正式 take；这些 take 共享 seed，但仍需要分别审核。

## Agent 初审

每个 take 至少检查：

- 身份、脸、瞳色、发型、服装；
- 手、四肢、武器和硬质结构；
- 镜头漂移和背景重构；
- 动作幅度；
- 明显尾部冻结/降速；
- 是否存在值得进入逐帧人工剪选的成片。

MAD / 光流 / motion uniformity 可用于标记风险，但这一阶段不能因为低画质 seed 之前通过就自动 PASS。

## Gate C：人工选 1080p Take

Agent 提供正式候选和简短差异说明，然后进入：

```text
WAITING_FOR_USER_SELECTION
```

用户明确选定一个 take 后记录：

```text
selected_take:
selected_seed:
resolution: 1920x1080
frames: 73
selected_take_sha256:
selection_notes:
status: SELECTED
```

## 淘汰规则

身份、解剖、武器、硬质结构或镜头出现严重错误时直接淘汰该 take。不要依赖后续 RIFE、裁帧或超分修复语义/结构错误。

## 晋级

完成 Gate C 后进入 `05-frame-selection.md`。