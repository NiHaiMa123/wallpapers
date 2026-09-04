# 01 需求与导演方案

本阶段只负责把用户目标转成 **Director Brief 和主路线**。它不定义 T2I/I2V 的底层实现。

治理与规范变更权限见：

- `../AGENTS.md`
- `../contracts/00-governance.md`

## 输入

- 角色、题材、参考图、风格或模糊构思；
- 是否已有用户认可的静态输入图；
- 用户明确必须保留/禁止的内容；
- 目标是否需要循环、插帧、超分和最终交付规格。

## Agent 动作

1. 判断从零 T2I，还是已有认可图片直接 I2V。
2. 先以视觉导演视角决定“拍什么”，不直接机械扩写 prompt。
3. 规划主体姿势/视线、景别/相机、16:9 构图、光线色彩、场景道具、视觉焦点。
4. 从 I2V 可执行性反向规划：
   - 哪些软质区域以后可以动；
   - 哪些硬质结构必须锁定；
   - 哪些遮挡、强透视、单向事件或镜头运动应避免。
5. 选择唯一主路线。

## Director Brief

至少形成：

```yaml
subject:
visual_goal:
pose_and_gaze:
shot_and_camera:
composition_16_9:
lighting_and_color:
scene_and_props:
animation_ready_regions:
static_lock_regions:
forbidden_changes:
planned_motion_for_i2v:
primary_route:
```

Director Brief 是后续 T2I prompt 和 motion brief 的上游依据。

## 不在本阶段决定的内容

- T2I runner/workflow 细节；
- video seed 的具体筛选实现；
- 内部 H3 分辨率；
- 帧编号；
- RIFE/超分算法；
- validator 阈值。

这些由后续阶段对应 Contract 定义。

## 晋级

- 从零生成 -> `02-t2i-and-image-selection.md`
- 已有用户明确认可图片 -> `03-motion-and-seed-screen.md`

如果实现者在导演目标与现有能力之间发现不可实现冲突，进入 `CONTRACT_REVIEW_REQUIRED`，由主 Agent决策，不由 subagent自行降低导演目标。