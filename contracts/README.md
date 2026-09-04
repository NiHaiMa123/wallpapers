# Contracts：项目可重建规范层

本目录定义 **实现必须满足的执行契约**。本项目采用 MD-first：`scripts/`、`workflows/`、`presets/`、validators 是实现，不是规范本身。

目标是：即使实现层被删除，一个具备仓库访问权限和足够执行能力的主 Agent，也应能只依据 `AGENTS.md`、`pipeline/` 与本目录重新搭建等价生产系统。

## 规范层级

不同文档负责不同问题：

1. `AGENTS.md`：治理、角色、权限、人工 Gate、规范变更权；
2. `pipeline/README.md` 与阶段文档：生产状态机，回答“什么时候做什么”；
3. `contracts/`：执行契约，回答“一个能力必须接受什么、保证什么、产出什么”；
4. `scripts/`、`workflows/`、`presets/`、validators：当前实现；
5. `README.md`：人类入口；
6. `VALIDATION_HISTORY.md`、`plans/`、`plan2.md`：历史证据，NON-NORMATIVE。

Pipeline 与 Contract 不应互相复制大量参数。Pipeline 引用 Contract；Contract 不负责决定人工 Gate 的顺序。

## 实现一致性原则

- 实现必须能追溯到一个 Contract。
- 实现拥有而 Contract 没有描述的生产行为，视为 **未规范化行为**，不能自动升级为事实源。
- Contract 与实现冲突时，subagent 不得自行修改 Contract 以“让实现通过”。
- subagent 应上报 `CONTRACT_REVIEW_REQUIRED`；主 Agent 作为 Spec Owner 判断：修实现、补 Contract，或修改 Contract 后重新实现。
- 经主 Agent 审核更新后的 Contract 立即成为新的规范事实；历史实现和历史报告不得反向覆盖它。

详见 `00-governance.md`。

## Contract 地图

| Contract | 定义 |
|---|---|
| `00-governance.md` | Spec Owner、subagent 权限、冲突处理、Contract Change Request |
| `01-runtime.md` | ComfyUI/资源/队列/熔断/运行环境契约 |
| `02-t2i.md` | Director Brief -> T2I 候选的输入输出与 Gate A 前置产物 |
| `03-lowres-i2v-seed.md` | 低成本 I2V seed 筛选契约 |
| `04-native-1080p-73f.md` | 正式 1920×1080 / 73f take 契约 |
| `05-frame-sequence-selection.md` | 原始帧列、1-based 人工编号、keep list 契约 |
| `06-interpolation.md` | 人工定稿帧列后的插帧契约 |
| `07-upscale.md` | 时序安全/AI 超分契约 |
| `08-final-validation.md` | 通用最终验证与交付证据契约 |
| `09-artifacts-and-reports.md` | 不覆盖、唯一命名、hash、manifest、运行报告契约 |

## Conformance Status

`CONFORMANCE_STATUS.md` 记录 **当前实现距离这些 Contract 还有哪些差距**。

它不是新的规范源，而是主 Agent 的实现审查/派工清单。一个 Contract 已经写清楚，不代表现有脚本已经符合它；在 `CONFORMANCE_STATUS.md` 尚为 `PARTIAL/NONCONFORMING/UNVERIFIED` 时，Agent 不得把实现描述成已经完成规范迁移。

## 可重建标准

每个执行 Contract 至少应写明：

```text
Purpose
Inputs
Required invariants
Allowed implementation freedom
Forbidden behavior
Outputs
Evidence / report schema
Failure states
Acceptance
```

如果 Agent 在实现时发现还需要一个 Contract 中不存在的关键事实（例如内部尺寸约束、编号原点、合法帧数、节点必需条件），必须先进入 Contract Review，而不是把该事实只写进脚本或 preset。