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
| `04-native-1080p-73f.md` | 正式 1920×1080 / 73f take、same-image first/last anchor 契约 |
| `05-frame-sequence-selection.md` | canonical 原始帧列、1-based 人工编号、keep list 契约 |
| `06-interpolation.md` | 人工定稿帧列后的纯插帧/循环 wrap 契约 |
| `07-upscale.md` | 保持已批准 fps 的时序安全/AI 超分契约 |
| `08-final-validation.md` | 参数化最终验证与交付证据契约 |
| `09-artifacts-and-reports.md` | 不覆盖、唯一命名、hash、manifest、运行报告契约 |
| `10-capability-baseline.md` | 从空环境重建所需 H3 模型能力、采样语义、合法帧长、RIFE/编码等基线 |
| `11-rebuild-manifest.md` | 删除实现后，主 Agent 从 MD 重建 scripts/workflows/presets/tests 的顺序和 DoD |

## 审计与实现状态

### `CONTRADICTION_AUDIT.md`

记录已经发现的“旧说法 vs 当前规范”冲突，并为每项指定唯一 normative source。例如：

- mirror vs same-image first/last anchor；
- `draft/long_draft/final` vs 四人工 Gate；
- 1344×768×124 “final” vs 正式 1080p/73f；
- 0-based vs 1-based human frames；
- HMNSFW 0.5 vs 默认关闭；
- 30.5 vs 31.0 GiB；
- 8188 vs 8189；
- 24fps 4K profile vs 高 fps 后处理；
- 61f/119-loop validator vs 动态 expected spec。

它是冲突索引，不取代具体 Contract。

### `CONFORMANCE_STATUS.md`

记录 **当前实现距离这些 Contract 还有哪些差距**。

它不是新的规范源，而是主 Agent 的实现审查/派工清单。一个 Contract 已经写清楚，不代表现有脚本已经符合它；在 `CONFORMANCE_STATUS.md` 尚为 `PARTIAL/NONCONFORMING/UNVERIFIED` 时，Agent 不得把实现描述成已经完成规范迁移。

## 可重建标准

一个执行 Contract 至少应写明：

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

`10-capability-baseline.md` 负责补齐“只看阶段 Contract 仍无法从零知道”的底层能力事实；`11-rebuild-manifest.md` 负责把这些 Contract 映射为一个可实施的重建顺序。

如果 Agent 在实现时发现还需要一个 Contract 中不存在的关键事实（例如新的内部尺寸约束、合法帧长、节点必需条件、编码语义），必须先进入 Contract Review，而不是把该事实只写进脚本或 preset。