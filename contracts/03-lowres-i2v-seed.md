# 03 Low-resolution I2V Seed Screening Contract

## Purpose

用低成本视频生成比较不同 video seed 的运动倾向，筛出值得进入高成本 1080p 阶段的候选。

本阶段的目标是 **seed qualification**，不是最终画质定稿。

## Inputs

```yaml
selected_image:
selected_image_sha256:
motion_brief:
motion_prompt_file:
seed_set:
preview_profile:
lora_policy:
loop_intent:
```

## Required invariants

比较 seed 时必须尽量保持单轴：

- 输入图相同；
- motion prompt 相同；
- LoRA 与其他主要运动参数相同；
- 相机/循环意图相同；
- 只改变 seed。

低画质 preview 必须尽量保留与正式生产相同的 **语义约束**：固定镜头、主体锁定、允许/禁止运动、循环意图。若为了成本使用了与生产不同的采样器/Turbo/步数，必须在报告中明确标记 `screening_only`。

## Screening policy

- 建议一次 5–8 个 seed；数量可由用户或主 Agent根据成本调整。
- Agent 可以淘汰明显的身份、解剖、镜头、动作方向和硬质结构错误。
- Agent 可以给 seed 排名和推荐。
- Gate B 最终选择必须由用户完成。

如果粗筛引擎与正式生成的行为差异明显，主 Agent可以增加一个“标准低分辨率确认候选”步骤，但这属于 pipeline 决策；subagent 不得擅自把额外阶段永久写入 Contract。

## Forbidden behavior

- 把 Turbo/低成本 preview 当作最终母版；
- 因某个 seed 在低画质表现好就自动跳过 1080p 人审；
- seed 比较时同时改 prompt、LoRA、输入图等多个主要变量；
- 让自动评分代替用户 Gate B。

## Outputs

```yaml
selected_image_sha256:
motion_prompt_sha256:
preview_profile:
screening_only: true
seed_candidates:
  - seed:
    output:
    output_sha256:
    findings:
    rank:
agent_recommendation:
status: WAITING_FOR_USER_SELECTION
```

Gate B 后必须记录：

```yaml
selected_video_seed:
selected_lowres_reference:
selection_notes:
status: SELECTED
```

## Acceptance

本阶段通过的含义仅是：用户已经选择一个值得进入正式 1080p 抽卡的 seed。它不对高分辨率动作、尾部速度或最终画质作保证。