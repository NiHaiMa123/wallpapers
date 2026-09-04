# 02 文生图与人工选图

本阶段负责把 Director Brief 转成静态候选，并完成 Gate A。

执行契约：`../contracts/02-t2i.md`

## 输入

- `01` 形成的 Director Brief；
- 当前 T2I prompt；
- 当前候选数量/seed 策略。

## 阶段动作

1. 从 Director Brief 派生 T2I prompt。
2. 按 `contracts/02-t2i.md` 生成可追溯候选。
3. Agent 淘汰明显结构错误，并说明构图、姿势和 I2V 可执行性差异。
4. 保留候选、prompt、seed、hash 和 Agent recommendation。
5. 进入 Gate A，不自动晋级。

## Gate A

```text
WAITING_FOR_USER_SELECTION
```

用户选择后记录：

```yaml
selected_image:
selected_image_sha256:
selection_notes:
status: SELECTED
```

## 本阶段不重复定义

- T2I 引擎具体节点；
- 默认模型/LoRA；
- 文件命名细节；
- artifact/hash 规则。

这些分别由 `contracts/02-t2i.md` 与 `contracts/09-artifacts-and-reports.md` 维护。

## 晋级

Gate A 完成 -> `03-motion-and-seed-screen.md`。

如果当前实现无法满足 T2I Contract，不得自行降低 Contract；进入 `CONTRACT_REVIEW_REQUIRED`。