# 04 Seed 筛选

## 目标

用最低合理成本淘汰身份、解剖、镜头和大方向错误的 seed。换主体后重新筛 seed，不沿用旧人物结论。

## 正常路线：Turbo 排名

建议先筛 5–8 个 seed，保持输入图、prompt、LoRA 和其他参数不变：

```powershell
.\scripts\run_h3_turbo_preview.ps1 `
  -Steps 4 `
  -Seed <seed> `
  -LoraStrength <strength> `
  -InputImage '<absolute-image>' `
  -PromptFile '.\prompts\generated\<prompt>.txt' `
  -Silent
```

Turbo 只用于排序。4 步优先；8 步不是 final，也不能替代标准 20 步。

## Turbo 不可用时

如果提交返回 `missing_node_type` 且指向 `MiniMaxH3TurboLoRA`：

1. 记录错误和缺失节点；
2. 不安装节点；
3. 不把失败提交算作生成样片；
4. 改用 2–3 个标准 `draft` seed 做最小对照；
5. 每个任务保持串行并单独验收。

## 排名维度

| 维度 | 判断 |
|---|---|
| 身份 | 脸、瞳色、发型、服装和比例是否保持 |
| 解剖 | 手、手指、四肢、关节是否正常 |
| 道具 | 剑、饰品和硬质前景是否弯曲或漂移 |
| 镜头 | 是否出现推拉摇移、裁切或背景重构 |
| 动作 | 方向和幅度是否符合 brief |
| 循环适配 | 标准 LoopLock 复核时能否平滑回到首帧，边界是否有顿感 |

## 单轴修改原则

- 同 seed 修改 prompt：用于判断问题是否来自提示词约束。
- 同 prompt 修改 seed：用于判断问题是否来自 seed 运动倾向。
- 不要同时改 prompt、seed、LoRA、输入图和 profile，否则比较失去意义。

## 产物

seed 排名表、淘汰理由和准备进入标准 20 步复核的 1–2 个候选。

Turbo 预览没有完成原生首尾锚定验收。候选 seed 进入标准 `draft` 时必须加 `-LoopLock`，并把它视为一次新的循环行为测试。

## 跨分辨率漂移门（2026-09-04 实战教训）

draft/低分辨率的"尾部无冻结"结论不自动适用于 1080p：0224 在 draft 筛选为 KEEP（last-ratio 1.11）后，1080p/20 步同样冻尾（last-ratio 0.03），0227 亦然。1080p 首发落地后，必须先跑 `analyze_motion_uniformity.py` 看尾部余速（last_ratio、tail/mid、末窗），合格才进 RIFE/remap/4K 重链路；不合格直接换 seed，不烧后续。

## 晋级条件

候选没有严重身份或解剖错误，镜头方向正确，动作有可能通过标准工作流复核。
