# 06 Interpolation Contract

## Purpose

在用户 Gate D 已经批准最终 keep list 后，提高帧密度/播放流畅度，同时保持用户已经确定的时间语义，不再偷偷做自动删帧或尾段重定时。

## Inputs

```yaml
source_frame_manifest:
human_selection_manifest:
rebuilt_sequence:
source_fps:
target_fps:
loop_intent:
interpolation_engine:
```

`target_fps` 必须在当前 run state 中明确记录；实现不得依赖脚本隐藏默认值决定最终交付 FPS。

## Required invariants

- 只处理 Gate D 已批准的帧序列；
- 不重新加入用户已删除帧；
- 不擅自删除用户保留帧；
- 不改变用户 keep list 的顺序；
- 默认不自动改变片内节奏；
- 插帧只生成相邻保留帧之间的中间状态；
- 循环任务必须处理最后保留帧到第一保留帧的 wrap interval，不能只处理片内相邻帧；
- source、target fps、输入帧数、输出帧数和循环处理方式必须写入报告。

## Timing policy

人工 Gate D 已经承担主要时序编辑。因此生产默认是：

```text
human-approved timing -> interpolation only
```

`equalize`、自动 tail compression、自动 arc-length remap、全局 speed factor 等属于 **可选实验/诊断策略**，除非用户或主 Agent在当前任务明确批准，否则不得混入默认插帧 Contract。

如果需要整体变速，必须作为独立显式参数/阶段记录，不能伪装成插帧本身。

## Cyclic frame-count semantics

实现必须明确说明自己的 cyclic 输出定义，并提供可计算的期望帧数。不得依赖某个 RIFE 工具的默认行为而不在 Contract/报告中说明。

对于任意引擎，至少保证：

- wrap interpolation 不复制一个额外首帧造成周期停顿；
- 首尾接缝的插值帧不被误当成普通片尾冻结；
- 输出按固定 target fps 编码。

具体引擎若有不同 frame-count 公式，应在实现子 Contract 或报告中显式记录。

## Visual rejection conditions

出现以下问题时插帧候选不能自动 PASS：

- 脸/眼睛鬼影；
- 手、武器、细线结构双影或分叉；
- 电弧/粒子生成错误；
- wrap 接缝变成溶解；
- 新增明显 micro-freeze；
- 插帧使用户已修正的尾部节奏再次变差。

## Outputs

```yaml
source_sequence_sha256_or_manifest:
source_frame_count:
source_fps:
target_fps:
engine:
model:
cyclic:
wrap_policy:
expected_output_frames:
actual_output_frames:
output:
output_sha256:
run_report:
visual_findings:
```

## Acceptance

- 输出帧数/target fps 与记录一致；
- 没有隐式 timing remap；
- wrap 被明确处理；
- 正常速度观看无不可接受鬼影/假溶解；
- 失败时可以无损回退到人工定稿的未插帧序列。