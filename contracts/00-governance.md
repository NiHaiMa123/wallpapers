# 00 Contract Governance / 规范治理

本文件定义谁有权修改规范，以及实现发现规范问题时如何反馈。

## 1. 角色

### 用户

用户拥有最终需求决定权。用户在当前会话中的明确选择、限制和批准优先于仓库中的旧假设。

### 主 Agent / Spec Owner

主 Agent 同时承担：

- Visual Director；
- Pipeline Orchestrator；
- **Spec / Contract Owner**；
- Technical Reviewer。

主 Agent 可以修改 `AGENTS.md`、`pipeline/` 与 `contracts/`，但必须基于用户目标、现有证据和整体一致性，不得为了让某个局部实现“看起来通过”而随意降低规范。

### Subagent / Implementer

Subagent 负责：

- 按当前 Contract 实现；
- 做局部实验和诊断；
- 保留证据；
- 发现 Contract 的遗漏、错误或不可实现约束；
- 提出 Contract Change Request。

除非主 Agent 的任务明确授权它修改某个规范文件，否则 subagent **不得自行修改 normative MD 的语义**。

## 2. 冲突处理

当实现与 Contract 不一致时，默认状态不是“自动以代码为准”，也不是“永远以旧 Contract 为准”，而是：

```text
CONTRACT_REVIEW_REQUIRED
```

主 Agent 必须判断以下三类之一：

### A. IMPLEMENTATION_BUG

Contract 正确，实现偏离规范。

处理：修实现；Contract 不变。

### B. CONTRACT_GAP

Contract 方向正确，但缺少实现必需的事实或边界。

例如：内部尺寸必须满足模型的整除约束、人工帧号需要明确 1-based、某节点是必需能力。

处理：主 Agent 补 Contract，再让实现对齐。

### C. CONTRACT_CHANGE

证据表明现有 Contract 的设计目标本身不可行、低效或与用户新决策冲突。

处理：主 Agent修改 Contract，记录理由和影响范围，再重新实现/复核所有受影响阶段。

## 3. Contract Change Request 格式

Subagent 遇到规范冲突时至少上报：

```yaml
status: CONTRACT_REVIEW_REQUIRED
contract_file:
contract_clause:
expected:
observed:
evidence:
impact:
proposal:
alternatives:
implementation_changed: false
```

`implementation_changed` 默认必须为 `false`。如果为了诊断做了实验性修改，要明确标成 experiment，不能冒充生产实现。

## 4. 规范变更后的传播

主 Agent 修改 Contract 后必须检查：

- `AGENTS.md` 是否有重复规则需要同步/删除；
- `pipeline/` 是否仍与新 Contract 兼容；
- 其他 Contract 是否引用同一事实；
- scripts/workflows/presets/validators 是否需要重建或修改；
- tests 是否需要更新；
- README 是否只需更新人类入口说明；
- 历史文档不改写历史事实，只增加“已被当前 Contract 取代”的说明。

## 5. 禁止的规范漂移

以下行为禁止：

- subagent 因为实现困难直接降低目标分辨率/FPS/质量门槛；
- subagent 删除人工 Gate 以便自动跑完；
- 实现中的默认值反向成为规范默认值而没有 Contract Review；
- 根据单个历史样片的阈值给所有任务设全局门槛；
- 用 README、plan、历史报告覆盖当前 pipeline/contract；
- 为了兼容旧脚本，让新 Contract 保留已经废弃的状态机。

## 6. 历史证据的正确用途

`VALIDATION_HISTORY.md`、`plans/`、`plan2.md` 可以用于：

- 证明某个技术约束曾经出现；
- 提供性能/失败证据；
- 提出新的 Contract Review；
- 设计回归测试。

它们不能直接定义当前生产路线。历史结论与当前 Contract 冲突时，历史结论保持原样作为当时事实，但当前执行遵循 Contract。

## 7. Definition of Done for Spec Change

规范修改只有在以下条件满足时才算完成：

1. 变更写入唯一 normative 位置；
2. 其他 normative MD 不再保存冲突副本；
3. 受影响 pipeline 已引用新 Contract；
4. 已列出实现需要做的 conformance work；
5. 历史文档被明确标为 NON-NORMATIVE；
6. 未经验证的实现状态不得被写成“已完成”。