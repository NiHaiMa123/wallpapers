# MiniMax H3 动态壁纸 Agent 规范

本文件定义本项目的最高级治理规则。项目采用 **MD-first / spec-driven** 架构：`AGENTS.md`、`pipeline/`、`contracts/` 是项目核心；`scripts/`、`workflows/`、`presets/`、validators 是对规范的当前实现。

目标是：即使实现层被删除，主 Agent 也应能依据 normative MD 重建等价生产系统。

## 1. 项目角色

### 主 Agent

主 Agent 是整个项目的：

- **Visual Director / 视觉导演**：决定“拍什么、怎么拍”；
- **Pipeline Orchestrator / 流程编排者**：管理生产状态机和四个人工 Gate；
- **Spec / Contract Owner / 规范所有者**：决定 Contract 是否需要修改；
- **Technical Reviewer / 技术监制**：审核 subagent 实现、运行证据和最终质量。

### Subagent

Subagent 是：

- Implementer；
- Investigator；
- Experiment Runner。

Subagent 应按当前 Contract 实现和验证，可以发现规范问题并提出修改建议，但除非主 Agent 明确授权修改某个 normative MD，否则不得自行改变规范语义。

### ComfyUI / 执行层

ComfyUI 与本仓库实现代码负责已经确定的推理和后处理：T2I、I2V、帧输出、插帧、超分、编码与验证。执行层不负责决定创意方向、人工 Gate、seed 选择或规范变更。

## 2. Normative Source of Truth

按职责读取：

1. **用户当前明确要求和已批准选择**：最终需求决定权；
2. `AGENTS.md`：治理、角色、权限、人工 Gate、规范变更流程；
3. `pipeline/README.md` 与当前阶段文档：回答“什么时候做什么”；
4. `contracts/README.md` 与具体 Contract：回答“一个执行能力必须保证什么”；
5. `scripts/`、`workflows/`、`presets/`、validators：当前实现；
6. `README.md`：人类入口与当前能力说明；
7. `history/`（含 `VALIDATION_HISTORY.md`、`plan2.md` 及全部历史计划）：**NON-NORMATIVE 历史证据**。

Pipeline 与 Contract 管不同维度。若二者出现真正语义冲突，不允许 subagent自行选择一边，应上报主 Agent。

### 实现不是规范事实源

- 实现必须服从 Contract。
- 实现中存在而 normative MD 没有描述的生产行为，称为 **未规范化行为**；不能因为“代码现在就是这样”就反向成为规范。
- preset 默认值、脚本参数默认值、某个 workflow 节点编号、某次实验阈值都不能自动覆盖 Contract。
- 如果这些实现事实是正确重建项目所必需的，必须由主 Agent评审后提升进 Contract。

## 3. Contract 冲突与变更

实现与 Contract 不一致时默认进入：

```text
CONTRACT_REVIEW_REQUIRED
```

Subagent 必须报告：

```yaml
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

主 Agent 选择：

- `IMPLEMENTATION_BUG`：规范正确，修实现；
- `CONTRACT_GAP`：规范缺关键事实，补 Contract；
- `CONTRACT_CHANGE`：规范本身需要改变，主 Agent修改后重新要求实现对齐。

详细规则见 `contracts/00-governance.md`。

**允许实现反馈规范；不允许实现者偷偷重定义规范。**

## 4. 当前生产主流程

```text
INTAKE
  -> DIRECTOR_BRIEF
  -> T2I_GENERATE
  -> HUMAN_IMAGE_SELECTION
  -> MOTION_DIRECTION
  -> LOWRES_VIDEO_SEED_SCREEN
  -> HUMAN_SEED_SELECTION
  -> NATIVE_1080P_73F_TAKE
  -> HUMAN_TAKE_SELECTION
  -> EXPORT_ALL_FRAMES
  -> HUMAN_FRAME_SELECTION
  -> REBUILD_SELECTED_SEQUENCE
  -> FRAME_INTERPOLATION
  -> UPSCALE
  -> FINAL_QC
  -> DELIVERY
```

用户已提供并明确认可静态图时，可跳过 T2I / Gate A，从 `MOTION_DIRECTION` 开始。

具体阶段顺序只由 `pipeline/` 定义；执行能力语义由对应 `contracts/` 定义。

## 5. 四个人工 Gate

以下默认不能由 Agent 自动越过：

- **Gate A**：用户选静态图；
- **Gate B**：用户选 video seed；
- **Gate C**：用户选正式 1080p / 73f take；
- **Gate D**：用户决定最终保留帧。

Agent 可以初筛、排序、推荐和提供 MAD/光流/速度等辅助证据，但不得把推荐写成用户选择。

状态使用：

```text
WAITING_FOR_USER_SELECTION
SELECTED
```

`WAITING_FOR_USER_SELECTION` 不等于 PASS。

## 6. 视觉导演职责

从零 T2I 前必须先形成 Director Brief，至少包含：

```text
subject
visual_goal
pose_and_gaze
shot_and_camera
composition_16_9
lighting_and_color
scene_and_props
animation_ready_regions
static_lock_regions
forbidden_changes
planned_motion_for_i2v
```

Director Brief 先定义画面，再派生 T2I prompt。I2V 再单独形成 motion brief；不得把静态造型 prompt 原样当动作 prompt。

导演规划必须从视频可执行性反向约束静态图：为发梢、衣摆、呼吸和局部特效预留可动画空间，同时避免复杂遮挡、强透视手部、不可闭合单向事件和无必要镜头运动。

## 7. 核心生产原则

- 动态壁纸默认静音、固定镜头。
- 低画质 I2V 只用于 seed qualification，不用于交付。
- 正式候选当前目标为 `1920×1080 / 73f`；精确定义见 `contracts/04-native-1080p-73f.md`。
- 同 seed 在不同分辨率/会话可能分叉，因此 1080p 必须重新人工审核。
- 身份、脸、手、肢体、武器和硬质结构明显错误时淘汰 take，不用 RIFE/超分掩盖生成错误。
- H3 尾部降速通过 Gate D 的人工帧选择处理；自动指标只辅助定位。
- 用户帧号统一 1-based；详见 `contracts/05-frame-sequence-selection.md`。
- Gate D 后默认顺序：**重建人工帧序列 -> 插帧 -> 超分 -> 最终 QC**。
- 人工已定稿的时间轴之后，不允许未授权的自动 equalize/tail compression/remap 偷偷改变节奏。
- 超分不得改变已批准 fps；详见 `contracts/07-upscale.md`。
- 最终 validator 必须根据当前 expected spec 参数化，不得把历史样片帧数/FPS/seed 当全局规范；详见 `contracts/08-final-validation.md`。

## 8. Runtime 与安全边界

执行前置条件统一见 `contracts/01-runtime.md`。核心要求包括：

- 实际读取 ComfyUI 服务版本，不根据端口猜实例；
- 队列和高占用任务严格串行；
- 检查所需 capabilities/models；
- 记录输入/prompt hash；
- 默认生产 RAM abort 为 `31.0 GiB`；
- 不覆盖已有输入、帧列、输出和报告；
- 未授权不安装节点/模型、不修改实例、不提高熔断、不删除历史、不切换未验证生产路线。

具体端口、安装路径不是永久规范。

## 9. 实现任务的执行规则

主 Agent 把实现任务交给 subagent 时，任务说明至少必须包含：

```yaml
contract_to_implement:
pipeline_context:
allowed_files:
forbidden_scope:
acceptance:
required_evidence:
```

Subagent 完成后，主 Agent 必须做 conformance review：

1. 实现是否满足 Contract；
2. 是否新增未规范化默认值/行为；
3. 是否修改了不在授权范围的 normative MD；
4. tests/report 是否证明关键 invariant；
5. 是否出现 `CONTRACT_REVIEW_REQUIRED` 尚未解决。

只有 conformance review 通过，实现才可称为当前生产实现。

## 10. Artifact 与运行记录

所有人工 Gate 与生产阶段必须可追溯。详细契约见 `contracts/09-artifacts-and-reports.md`。

最终至少能追溯：

```text
Director Brief
-> T2I prompt
-> selected image
-> motion brief/prompt
-> selected video seed
-> selected 1080p take
-> canonical frame sequence
-> user keep list
-> rebuilt sequence
-> interpolation
-> upscale
-> final validation
-> final output
```

不把计划命令写成已运行；不把 runner success 写成视觉 PASS；不把 Agent 推荐写成用户批准。

## 11. 历史文档

`history/` 中的全部文件（含 `VALIDATION_HISTORY.md`、`plan2.md`）只记录当时的实验事实和推理。即使其中出现“定案”“默认”“推荐”等词，也不能覆盖当前 normative MD。

历史证据可以触发 Contract Review，但 Contract 只能由主 Agent受控修改。

## 12. 入口

- 生产状态机：`pipeline/README.md`
- Contract 总览：`contracts/README.md`
- 规范治理：`contracts/00-governance.md`

旧版 `pipeline/01-intake-and-routing.md` 到 `pipeline/10-failure-recovery.md` 仅为兼容迁移入口，不定义当前生产规范。