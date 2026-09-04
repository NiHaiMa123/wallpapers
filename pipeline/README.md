# MiniMax H3 Agent Pipeline

本目录把根 `AGENTS.md` 的方向性规范拆成逐阶段可执行流程。每一阶段文档都回答四个问题：输入是什么、Agent 要做什么、必须产出什么、满足什么条件才能晋级。

## 主流程

```text
00 执行契约
  -> 01 需求盘点与路由
  -> 02 环境预检
  -> 03 输入图检查与提示词
  -> 04 seed 筛选
  -> 05 标准分级生成
  -> 06 视觉验收
  -> 07 原生首尾循环与技术验证
  -> 08 交付与报告
```

可选扩展：

- 原生 1080p 或 4K：读取 `09-native-1080p-and-4k.md`。
- 任一阶段失败：读取 `10-failure-recovery.md`。

## 文档地图

| 文档 | 何时读取 | 核心产物 |
|---|---|---|
| `00-operating-contract.md` | 每个任务开始时 | 工作模式、边界和完成契约 |
| `01-intake-and-routing.md` | 收到新任务时 | 创意简报和唯一主路线 |
| `02-preflight.md` | 任何实际运行前 | API、队列、版本、节点和资源结论 |
| `03-input-and-prompt.md` | I2V/T2V 提示词设计时 | 输入证据和 UTF-8 prompt 文件 |
| `04-seed-screening.md` | 首次生成或换主体后 | seed 排名和淘汰理由 |
| `05-standard-render.md` | seed 晋级时 | draft、long_draft、final 及报告 |
| `06-visual-review.md` | 每个生成阶段完成后 | PASS/REJECT/BLOCKED 结论 |
| `07-loop-and-validation.md` | LoopLock final 完成后 | 直接循环 MP4 和 validator 结果 |
| `08-delivery-and-reporting.md` | 最终交付前 | 文件索引、参数、缺陷和校验信息 |
| `09-native-1080p-and-4k.md` | 用户明确需要高分辨率时 | 1080p 帧流或 4K 成片 |
| `10-failure-recovery.md` | 发生缺节点、OOM、漂移等问题时 | 安全降级或回退动作 |

## 状态记录模板

每次阶段切换至少保留以下字段：

```text
stage:
status: PASS | REJECT | BLOCKED
input:
prompt_file:
seed:
profile:
api:
lora_strength:
silent:
output:
run_report:
visual_findings:
technical_findings:
next_stage:
```

## 最短直接图生视频路线

用户已有图片并要求跳过文生图时：

```text
检查图片
  -> 写 I2V 动作 prompt
  -> API/队列/节点预检
  -> Turbo seed 筛选；不可用则降级为小规模标准 draft 筛选
  -> 标准 LoopLock draft
  -> LoopLock long_draft
  -> LoopLock final
  -> 直接首尾循环正常速度观看
  -> validator
  -> 交付
```
