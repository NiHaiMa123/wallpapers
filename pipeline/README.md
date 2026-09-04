# MiniMax H3 Agent Pipeline

本目录只定义 **生产状态机**：什么时候做什么、什么时候必须停下来让用户选择、失败回到哪里。

执行能力的精确定义不在 pipeline 中重复维护，统一引用 `../contracts/`。

## 架构边界

```text
AGENTS.md
  治理 / 角色 / Spec Owner / Gate 权限
        ↓
pipeline/
  生产顺序：WHEN
        ↓
contracts/
  执行契约：WHAT MUST HOLD
        ↓
scripts / workflows / presets / validators
  当前实现：HOW
```

如果实现与 Contract 冲突，进入 `CONTRACT_REVIEW_REQUIRED`，由主 Agent判断修实现还是修改 Contract。Subagent 不得自行让实现反向覆盖规范。

## 当前主流程

```text
00 执行契约
  -> 01 需求与导演方案
  -> 02 文生图与人工选图
  -> 03 动作导演与低画质 seed 筛选
  -> 04 1080p / 73帧正式抽卡与人工选片
  -> 05 全帧导出与人工留帧
  -> 06 重建、插帧与超分
  -> 07 最终 QC 与交付
```

故障和回退见 `08-failure-recovery.md`。

用户已有并明确认可的静态图时，可跳过 02 / Gate A，从 03 开始。

## 四个人工 Gate

```text
Gate A  用户选静态图
Gate B  用户选 video seed
Gate C  用户选 1080p / 73f take
Gate D  用户选最终保留帧
```

人工 Gate 状态为：

```text
WAITING_FOR_USER_SELECTION
SELECTED
```

不得把 `WAITING_FOR_USER_SELECTION` 自动当作 PASS。

## 阶段 -> Contract 映射

| Pipeline | 主要职责 | 必读 Contract |
|---|---|---|
| `00-operating-contract.md` | 工作模式、Gate、执行边界 | `contracts/00-governance.md`, `01-runtime.md`, `09-artifacts-and-reports.md` |
| `01-intake-and-director.md` | Director Brief、路线 | `contracts/00-governance.md` |
| `02-t2i-and-image-selection.md` | T2I + Gate A | `contracts/02-t2i.md` |
| `03-motion-and-seed-screen.md` | motion brief + 低清 seed + Gate B | `contracts/03-lowres-i2v-seed.md` |
| `04-native-1080p-take.md` | 正式 1080p/73f + Gate C | `contracts/04-native-1080p-73f.md` |
| `05-frame-selection.md` | canonical 帧列 + Gate D | `contracts/05-frame-sequence-selection.md` |
| `06-interpolation-and-upscale.md` | 重建、插帧、超分 | `contracts/06-interpolation.md`, `07-upscale.md` |
| `07-final-qc-and-delivery.md` | 最终验证和交付 | `contracts/08-final-validation.md`, `09-artifacts-and-reports.md` |
| `08-failure-recovery.md` | 回退/规范冲突 | `contracts/00-governance.md`, `01-runtime.md` |

## 状态模板

每次阶段切换至少记录：

```yaml
stage:
status: PASS | PASS_WITH_WARNINGS | REJECT | BLOCKED | WAITING_FOR_USER_SELECTION | SELECTED | CONTRACT_REVIEW_REQUIRED
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
contract_review:
next_stage:
```

## 最短已有图片路线

```text
检查已认可输入图
  -> Motion Brief
  -> 低画质 I2V seed 筛选
  -> Gate B 用户选 seed
  -> 1920×1080 / 73f 正式 take
  -> Gate C 用户选 take
  -> 使用该 take 的 canonical PNG 全帧列
  -> Gate D 用户选 1-based keep list
  -> 重建人工帧序列
  -> 插帧
  -> 超分
  -> 最终 QC
  -> 交付
```

## Pipeline 不负责保存的事实

以下内容不要在多个阶段文件里各写一份：

- 内部 1920×1088 与可见 1920×1080 的关系；
- 人工帧号 1-based；
- 插帧是否允许自动 remap；
- 超分是否必须保持 fps；
- validator 是否参数化；
- RAM/队列/API 运行契约；
- artifact/hash/report 规则。

这些统一由 `contracts/` 定义。Pipeline 只引用，不复制，避免多 Agent 修改后产生第二个 source of truth。

## 历史文档

旧版 `01-intake-and-routing.md` 到 `10-failure-recovery.md` 仅保留路径兼容与迁移提示。`../plans/`、`../plan2.md`、`../VALIDATION_HISTORY.md` 是 NON-NORMATIVE 历史证据；其中即使写有“定案/默认/推荐”，也不能改变本 Pipeline。