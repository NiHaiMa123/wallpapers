# 03 动作导演与低画质 Seed 筛选

本阶段的目标是：固定已选静态图，先以低成本 I2V 找到值得投资的 video seed。

## 先做动作导演

Agent 根据已选图重新做 motion brief，而不是把 T2I prompt 直接复制给视频模型。

至少定义：

```text
input_image:
identity_lock:
primary_motion_systems:
static_lock_regions:
camera_lock:
loop_intent:
forbidden_motion:
```

默认原则：

- 固定镜头和焦距；
- 只允许 2–3 个主要运动系统；
- 优先低幅呼吸、眨眼、发梢/衣摆、小范围局部光效；
- 水晶、武器、建筑、地面等硬质结构保持稳定；
- 避免持续单向飞离画面的粒子或不可闭合事件。

## 低画质 Seed Screen

1. 固定输入图、motion prompt、LoRA 和其他主要参数。
2. 只改变 video seed。
3. 使用仓库当前验证的低成本 I2V preview 路线；Turbo 可用时用于快速排序，缺失时使用小规模标准低分辨率 preview。
4. 建议一次筛 5–8 个 seed。
5. Agent 做第一轮技术/视觉排序，重点检查：
   - 身份和脸；
   - 手、肢体和道具；
   - 镜头是否漂移；
   - 动作幅度和方向；
   - 背景/硬质结构稳定性；
   - 是否值得进入高成本 1080p 抽卡。

低画质阶段 **不负责最终尾部速度和最终画质定稿**。不同分辨率和不同会话下，同 seed 可能分叉。

## Gate B：人工选 Seed

Agent 给出 seed 排名、淘汰理由和推荐，但必须进入：

```text
WAITING_FOR_USER_SELECTION
```

由用户明确指定进入原生 1080p 阶段的 seed。

记录：

```text
selected_video_seed:
lowres_reference_output:
selection_notes:
status: SELECTED
```

## 单轴原则

比较 seed 时保持其他变量不变。若需要判断 prompt 问题，另起同 seed / 单一 prompt 变量对照，不同时修改多轴。

## 晋级

完成 Gate B 后进入 `04-native-1080p-take.md`。