# MiniMax H3 Agent Pipeline

本目录定义当前生产流程。项目分为两层：

- **Agent 层**：视觉导演、流程编排、人工 Gate 管理、技术 QC；
- **ComfyUI / scripts 层**：按既定方案执行生成、插帧、超分和编码。

当前目标不是全自动闭环，而是 **Agent 主导规划 + ComfyUI 执行 + 用户在关键审美节点做最终选择**。

## 主流程

```text
00 执行契约
  -> 01 需求与导演方案
  -> 02 文生图与人工选图
  -> 03 动作导演与低画质 seed 筛选
  -> 04 1080p / 73帧正式抽卡与人工选片
  -> 05 全帧导出与人工留帧
  -> 06 插帧、超分与成片重建
  -> 07 最终 QC 与交付
```

任一阶段发生环境、资源或生成故障时读取 `08-failure-recovery.md`。

如果用户已提供并明确认可静态输入图，可跳过第 02 阶段，从第 03 阶段开始。

## 为什么必须保留人工 Gate

本项目已经确认两个不能靠低成本自动指标替代的问题：

1. 低画质 seed 的运动倾向不能保证在原生 1080p 中完全复现；因此选 seed 后仍要重新抽 1080p take 并人工确认。
2. MiniMax H3 首尾锚定视频常出现末尾降速/冻结；速度分析可以定位问题，但最终保留哪些帧由用户决定。

所以当前生产流程包含四个不可自动越过的人工确认点：

```text
Gate A  选静态图
Gate B  选 video seed
Gate C  选 1080p take
Gate D  选最终保留帧
```

## 文档地图

| 文档 | 作用 | 核心产物 |
|---|---|---|
| `00-operating-contract.md` | 全局执行规则 | 模式、权限、状态、人工 Gate 规则 |
| `01-intake-and-director.md` | 把用户需求转成导演方案 | director brief、主路线 |
| `02-t2i-and-image-selection.md` | 文生图和静态图确认 | T2I prompt、候选图、用户选图 |
| `03-motion-and-seed-screen.md` | 设计动作并低成本找 seed | motion brief、seed 排名、用户选 seed |
| `04-native-1080p-take.md` | 锁定 seed 后抽 1080p 73f | 正式候选、用户选 take |
| `05-frame-selection.md` | 导出全部帧并人工定留删 | 全帧目录、最终 keep list |
| `06-interpolation-and-upscale.md` | 按 keep list 重建、插帧、超分 | 最终高帧率/高分辨率候选 |
| `07-final-qc-and-delivery.md` | 正常速度观看、技术 QC、交付 | 最终文件与复现记录 |
| `08-failure-recovery.md` | 故障分类和回退 | 安全降级路线 |

## 状态模板

每次阶段切换至少记录：

```text
stage:
status: PASS | PASS_WITH_WARNINGS | REJECT | BLOCKED | WAITING_FOR_USER_SELECTION | SELECTED
input:
director_brief:
prompt_file:
seed:
resolution:
frames:
api:
output:
run_report:
visual_findings:
technical_findings:
human_selection:
next_stage:
```

## 最短已有图片路线

```text
检查已认可输入图
  -> 动作导演 / motion brief
  -> 低画质 I2V seed 抽卡
  -> 用户选 seed
  -> 1920×1080 / 73f 正式抽卡
  -> 用户选 take
  -> 导出全部 73 帧
  -> 用户选保留帧
  -> 重建帧序列
  -> RIFE 插帧
  -> 超分
  -> 最终 QC
  -> 交付
```

## 重要原则

- Agent 先做导演方案，再写 prompt；不是 prompt 扩写器。
- 低画质阶段只负责找值得投资的 seed，不承担最终画质验收。
- 1080p 阶段必须重新人工审核。
- 全帧自动指标只提供参考；最终 keep list 由用户决定。
- 身份、解剖、武器、硬质结构等生成错误通过重新抽卡解决，不交给 RIFE/超分修。
- 最终顺序固定为：**人工留帧 -> 重建序列 -> 插帧 -> 超分 -> QC/交付**。

## 旧文档

旧版 `01-intake-and-routing.md` 到 `10-failure-recovery.md` 曾围绕 `draft -> long_draft -> final -> direct loop` 构建。它们保留为兼容入口，但不再定义当前主生产流程；打开后应按其中的迁移提示进入本 README 对应的新阶段文档。