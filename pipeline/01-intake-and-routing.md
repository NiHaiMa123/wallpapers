# 01 需求盘点与路由

## 输入

- 用户文字目标；
- 输入图片或文本构思；
- 是否明确要求实际生成；
- 是否要求音频、循环、时长、1080p 或 4K；
- 是否明确要求启用成人动作 LoRA。

## Agent 动作

1. 先判定任务类型：`PLAN`、`DIAGNOSE`、`REVIEW` 或 `EXECUTE`。
2. 盘点以下字段：主体身份、允许动作、禁止变化、镜头、循环语义、交付分辨率、静音/音频、LoRA 意图和时间预算。
3. 只有缺失信息会实质改变路线时才提一个简短问题；否则声明合理假设并继续。
4. 从下表选择唯一主路线，不同时启动多条生成路线。

## 路由表

| 用户目标 | 主入口 | 说明 |
|---|---|---|
| 已有图片直接做循环视频 | `scripts/run_h3_turbo_preview.ps1` → `scripts/run_h3_live2d_profile.ps1 -LoopLock` | 跳过文生图；Turbo 只粗筛 |
| 文本生成候选首图 | `scripts/run_h3_pseudo_t2i.ps1` | 五帧短包抽一帧 |
| 文本首图再生成视频 | `scripts/run_h3_text_to_live2d.ps1` | 需要快速端到端草稿时使用 |
| 原生 1080p 边界任务 | `scripts/run_h3_1080_stream.ps1` | 先读 `09-native-1080p-and-4k.md` |
| 已有非循环母版要求改成循环 | 重新运行 `scripts/run_h3_live2d_profile.ps1 -LoopLock` | 不做后期反向拼接 |
| 已有循环做 4K | `scripts/run_4k_upscale.ps1` | 默认 `temporal_safe` |

## 默认假设

- 动态壁纸默认静音。
- 已有图时，输入图决定人物外观、服装、初始姿态和构图。
- 未提出成人动作 LoRA 意图时，默认 `LoraStrength=0`。
- 未提出镜头运动时，默认固定镜头和固定焦距。
- 动态壁纸默认使用原生 `-LoopLock` 首尾锚定；提示词把所有动作设计成完整周期，回到源姿态时保持余速穿过边界，不要在末段停死。

## 产物

一份简短创意简报，至少包含：

```text
task_type:
primary_route:
input_asset:
identity_lock:
allowed_motion:
forbidden_motion:
camera:
loop_strategy:
silent:
lora_intent:
target_delivery:
```

## 晋级条件

- 主路线唯一且仓库已有验证入口；
- 用户授权范围明确；
- 不存在必须先由用户选择的实质分歧。
