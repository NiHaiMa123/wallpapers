# 03 动作导演与低画质 Seed 筛选

本阶段负责：根据已选静态图形成 motion brief，用低成本 I2V 比较 video seed，并完成 Gate B。

执行契约：`../contracts/03-lowres-i2v-seed.md`

## Motion Brief

至少定义：

```yaml
input_image:
identity_lock:
primary_motion_systems:
static_lock_regions:
camera_lock:
loop_intent:
forbidden_motion:
```

Motion Brief 必须针对视频运动重新设计，不把 T2I prompt 原样复制过来。

## Seed Screen

按 Contract 执行：

- 固定输入图、motion prompt、LoRA/主要运动语义；
- 比较 seed 时保持单轴；
- 使用低成本路线筛选，明确标记 `screening_only`；
- Agent 可以淘汰明显身份/解剖/镜头/硬质结构错误并排序；
- 低画质结果不承担最终尾部速度和最终画质保证。

如粗筛执行器与正式生成语义差异明显，是否增加标准低分辨率确认由主 Agent决定，不能由 subagent偷偷永久增加/删除 pipeline 阶段。

## Gate B

```text
WAITING_FOR_USER_SELECTION
```

用户选定后记录：

```yaml
selected_video_seed:
selected_lowres_reference:
selection_notes:
status: SELECTED
```

## 本阶段不重复定义

- Turbo 具体节点；
- 固定 steps/profile 名称；
- 正式 1080p 内部尺寸；
- 最终 Loop/RIFE 时序算法。

这些属于实现或后续 Contract。

## 晋级

Gate B 完成 -> `04-native-1080p-take.md`。

如果当前低清实现无法表达生产需要的循环/锁定语义，应上报 Contract Review，不得用脚本现状反向修改本阶段目标。