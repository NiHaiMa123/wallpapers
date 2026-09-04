# 05 全帧导出与人工留帧

本阶段解决 MiniMax H3 正式 take 的尾部降速/冻结问题。核心原则：**canonical 全帧证据 + 自动分析辅助 + 用户决定 keep list**。

执行契约：`../contracts/05-frame-sequence-selection.md`

## 输入

- Gate C 选定的正式 take；
- 与该 take 同 run 生成的 canonical PNG frame sequence；
- 可选 MAD/光流/速度分析。

## 阶段动作

1. 校验 canonical frame sequence 完整性和 manifest。
2. 向用户展示完整帧列；所有 human-facing 帧号统一按 Contract 的 1-based 规则。
3. Agent 可以标记尾部慢区、速度尖峰和 wrap 风险，但不自动形成“批准的” keep list。
4. 进入 Gate D。

如果当前 take 没有 canonical PNG 序列，只能从 MP4 拆帧，必须明确标记 `decoded_from_video`，不能把它描述为等价的无损主路径。

## Gate D

```text
WAITING_FOR_USER_SELECTION
```

用户可以给出保留范围、删除范围或明确帧号列表。Agent 负责把它规范化成 Contract 要求的 1-based human selection manifest。

示意：

```yaml
numbering: 1-based
keep_frames:
drop_frames:
source_frame_count:
approved_by_user: true
status: SELECTED
```

## 重建前检查

只按 `contracts/05-frame-sequence-selection.md` 校验：越界、重叠、顺序、编号原点和用户批准状态。

如果用户选择会造成明显位置/语义跳跃，Agent 应警告并说明影响，但不得擅自修改列表。

## 本阶段不负责

- 自动 equalize；
- 自动 tail compression；
- RIFE；
- 超分；
- 自动修改用户 keep list。

## 晋级

Gate D 完成 -> `06-interpolation-and-upscale.md`。