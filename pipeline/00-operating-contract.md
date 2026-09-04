# 00 执行契约

本文件是当前 pipeline 的统一入口。治理与规范变更权限以根 `AGENTS.md` 和 `../contracts/00-governance.md` 为准；runtime 细节统一见 `../contracts/01-runtime.md`。

## 工作模式

- `PLAN`：导演方案、路线、prompt、seed 策略和验收计划；不提交高占用任务。
- `DIAGNOSE`：分析已有输入、输出、reports 和实现一致性。
- `REVIEW`：审候选或审实现，不替用户越过人工 Gate。
- `EXECUTE`：运行当前最小且有意义的生产阶段。
- `IMPLEMENT`：按指定 Contract 修改 scripts/workflows/presets/tests；通常交给 subagent。
- `SPEC_REVIEW`：主 Agent处理 `CONTRACT_REVIEW_REQUIRED`，决定修实现还是修改规范。

## 当前主路线

```text
Director Brief
  -> T2I
  -> Gate A 用户选图
  -> Motion Direction
  -> Low-res Seed Screen
  -> Gate B 用户选 seed
  -> 1080p / 73f Take
  -> Gate C 用户选 take
  -> Canonical Frame Sequence
  -> Gate D 用户选 1-based keep frames
  -> Rebuild
  -> Interpolate
  -> Upscale
  -> Final QC
  -> Delivery
```

已有并被用户认可的输入图可以跳过 T2I / Gate A。

## Runtime Preflight

任何实际生成或高占用后处理在提交前都必须满足 `../contracts/01-runtime.md`。

Pipeline 不再维护端口/版本绑定、节点清单、RAM 细节副本。若实现需要的新运行事实没有写入 Runtime Contract，应进入 Contract Review，而不是只写进 runner。

## 人工 Gate

Agent 可以初筛、排序、推荐和提供自动分析证据，但不能代替用户：

- 选静态图；
- 选 video seed；
- 选正式 1080p take；
- 定最终 keep list。

人工 Gate 使用：

```text
WAITING_FOR_USER_SELECTION
SELECTED
```

## Contract Conformance

生产执行前，Agent 应知道本阶段对应哪个 Contract。

实现/运行出现以下情况时不得直接继续：

- 当前脚本默认值与 Contract 不同；
- 当前 workflow 缺少 Contract 要求的语义；
- preset 限制导致 Contract 目标无法表达；
- validator 写死历史样片规格；
- 需要新增关键实现事实才能正确重建项目。

这些情况进入：

```text
CONTRACT_REVIEW_REQUIRED
```

Subagent 只上报证据和 proposal；主 Agent作为 Spec Owner 决定：

```text
IMPLEMENTATION_BUG
CONTRACT_GAP
CONTRACT_CHANGE
```

## 全局执行规则

- 同时只跑一个生产重任务；
- 不覆盖输入、prompt、视频、canonical frame sequence、人工 manifest、报告和失败证据；
- 动态壁纸默认静音、固定镜头；
- 进程成功不等于视觉通过；
- 低画质 seed 通过不等于 1080p take 通过；
- 自动分析不等于用户选择；
- 生成结构错误回生成阶段，不交给后处理掩盖；
- Gate D 后不允许未授权自动 equalize/remap 改变用户已批准时间轴；
- 具体 artifacts/report 规则见 `../contracts/09-artifacts-and-reports.md`。

## 禁止自动扩展

没有额外授权时不执行：

- 安装新节点/模型；
- 修改 ComfyUI 实例/安装目录；
- 提高生产 RAM abort；
- 删除/覆盖历史文件；
- 切换未验证生产 workflow；
- 运行边界/负对照实验；
- subagent 自行修改 normative MD 以适配自己的实现。

## 完成契约

### 规划任务

交付 Director Brief、路线、prompt/motion 方案、seed 策略、人工 Gate、相关 Contract 和风险。

### 实现任务

交付：

```yaml
contract_implemented:
files_changed:
tests_or_evidence:
new_unstandardized_behavior: none | details
contract_review_required: false | details
conformance_result:
```

### 生产执行任务

必须能追溯：

```text
Director Brief
-> selected image
-> selected video seed
-> selected 1080p take
-> canonical frames
-> user keep list
-> interpolation
-> upscale
-> final validation
-> final output
```

## 下一阶段

从 `01-intake-and-director.md` 开始；实现某能力时先读取对应 `../contracts/*.md`。