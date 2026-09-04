# 05 Frame Sequence & Human Selection Contract

## Purpose

把 Gate C 选定的正式 1080p take 转成 **用户可直接检查的完整原始帧列**，并建立唯一、无歧义的人工 keep list。

本 Contract 是解决 H3 尾部降速/冻结问题的核心人工编辑契约。

## Canonical source

Gate D 的 canonical source 是正式 take 对应的 **1920×1080 PNG frame sequence**，不是再次从压缩 MP4 解码得到的二次帧列。

如果当前实现只能从视频拆帧，必须在报告中标记来源为 `decoded_from_video`；该实现不应被描述为无损 canonical path。

## Human frame numbering

所有面向用户展示、讨论和保存的帧号统一使用：

```text
1-based numbering
first frame = 1
last frame  = N
```

对于当前正式 73f take：

```text
1..73
```

实现内部可以使用 0-based index，但必须在边界显式转换；任何 CLI/API 直接把用户的 1-based 帧号当作 0-based index 都是实现 BUG。

## Required invariants

- 原始全帧目录不可修改、覆盖、重排或删除；
- 每个帧文件可唯一映射到 human frame number；
- 保留原始时间顺序；
- Agent 可以提供 MAD、光流、速度曲线和风险区间；
- 自动分析只能提出建议，不得生成“已批准” keep list；
- 最终 keep/drop 决定必须来自用户 Gate D；
- 用户没有明确修改时，不自动均速、不自动删尾、不自动加速、不自动复制帧。

## Frame manifest

在进入 Gate D 前必须生成或等价记录：

```yaml
source_take:
source_take_sha256:
frame_dir:
frame_count:
numbering: 1-based
frames:
  - human_frame: 1
    file:
    sha256:
  - ...
```

## Gate D input

Agent 应向用户提供完整帧列，并可附：

```yaml
analysis:
  possible_slow_regions:
  possible_spikes:
  boundary_change:
  notes:
```

但不能把分析建议写入 `approved_keep_frames`。

## User selection forms

用户可以使用：

```text
保留 1-63,73
删除 64-72
保留 1,3,5,...
明确帧号列表
```

实现必须把用户表达规范化为一个 1-based manifest，例如：

```yaml
numbering: 1-based
keep_frames: [1,2,3,...,63,73]
drop_frames: [64,65,66,67,68,69,70,71,72]
source_frame_count: 73
approved_by_user: true
```

## Validation before rebuild

- 所有帧号在 `1..N`；
- keep 与 drop 不重叠；
- keep list 非空；
- 顺序严格按原始 human frame number；
- 不存在隐式 0-based 转换错误；
- 若用户选择会造成明显语义/位置跳跃，Agent 应警告并展示影响，但不得自行更改列表。

## Outputs

```yaml
frame_manifest:
human_selection_manifest:
keep_frames:
drop_frames:
analysis_reference:
user_selection_notes:
status: SELECTED
```

## Acceptance

只有 `approved_by_user: true` 的 1-based keep list 才能进入插帧/超分主线。