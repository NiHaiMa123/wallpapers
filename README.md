# MiniMax H3 本地动态壁纸工作流

> [!CAUTION]
> **18+ / Adults Only.** 仓库包含可选成人内容 LoRA 的本地能力。未明确要求时，生产规范不自动启用可选成人动作 LoRA。

本项目是一套面向本地 MiniMax H3 / ComfyUI 动态壁纸制作的 **MD-first Agent 工程**。

项目的核心不是某个 PowerShell 脚本或 ComfyUI JSON，而是能够让主 Agent 重建整套系统的规范：

```text
AGENTS.md
  项目治理 / 主 Agent / subagent / Spec Owner
        ↓
pipeline/
  生产状态机：什么时候做什么
        ↓
contracts/
  执行契约：每个能力必须保证什么
        ↓
scripts / workflows / presets / validators
  当前实现：怎么做
```

如果实现与 Contract 冲突，不是“代码现在这样所以规范也改成这样”。Subagent 必须上报 `CONTRACT_REVIEW_REQUIRED`；由主 Agent 判断是实现 BUG、Contract 缺口，还是需要受控修改 Contract。

## 入口

- **最高治理规则**：[`AGENTS.md`](AGENTS.md)
- **当前生产流程**：[`pipeline/README.md`](pipeline/README.md)
- **执行 Contract**：[`contracts/README.md`](contracts/README.md)
- **当前实现一致性差距**：[`contracts/CONFORMANCE_STATUS.md`](contracts/CONFORMANCE_STATUS.md)
- **历史实验证据**：[`history/`](history/README.md)（含 `VALIDATION_HISTORY.md`、`plan2.md` 及全部历史计划、prompt 归档）

最后一类是 **NON-NORMATIVE**。其中即使写有“定案”“默认”“推荐”，也只代表当时实验结论，不能覆盖当前 Contract。

---

## 当前生产主线

```text
视觉导演 / Director Brief
  -> 文生图
  -> Gate A 用户选静态图
  -> Motion Brief
  -> 低画质 I2V 筛 video seed
  -> Gate B 用户选 seed
  -> 正式 1920×1080 / 73f take
  -> Gate C 用户选 take
  -> canonical PNG 全帧列
  -> Gate D 用户选 1-based keep list
  -> 重建人工定稿序列
  -> 插帧
  -> 超分
  -> 参数化 Final QC
  -> 交付
```

已有用户明确认可的静态图时，可以跳过 T2I / Gate A。

## 为什么 Agent 必须先当导演

文生图不是把用户一句话扩成一长串 prompt。主 Agent 先决定：

- 姿势、身体朝向和视线；
- 景别、相机高度/角度和固定镜头；
- 16:9 构图和视觉重心；
- 主光、轮廓光和颜色关系；
- 场景、道具和前中后景；
- 哪些区域适合后续微动画；
- 哪些硬质结构必须静止；
- 后续 I2V 适合的主要运动系统。

然后才从 Director Brief 派生 T2I prompt；I2V 再单独写 motion brief。

## 四个人工 Gate

| Gate | 用户决定 | Agent 职责 |
|---|---|---|
| A | 使用哪张静态图 | 初筛结构错误、构图和 I2V 可执行性 |
| B | 哪个 video seed 进入正式阶段 | 低成本抽卡、排序、说明缺陷 |
| C | 哪个 1080p / 73f take 进入后期 | 正常速度审片、结构/时序风险分析 |
| D | 最终保留哪些帧 | 提供 canonical 全帧列和自动分析证据，严格执行用户 keep list |

Agent 不得把 `WAITING_FOR_USER_SELECTION` 当作 PASS 自动越过。

## 正式 1080p 的规范语义

当前正式 Contract 是：

```text
visible output: 1920×1080
frames:         73
fps:            24
silent:         true
camera:         locked
```

当前已知 H3 内部实现可使用 `1920×1088 -> 1920×1080`，但内部尺寸不是最终交付尺寸。完整定义见 [`contracts/04-native-1080p-73f.md`](contracts/04-native-1080p-73f.md)。

正式 take 应尽量直接保留 1920×1080 PNG 全帧序列，作为后续 Gate D 的 canonical source，而不是先压成 MP4 再拆回图片。

## 人工帧选择

所有面向用户的帧号统一 **1-based**：

```text
第一帧 = 1
73f take = 1..73
```

自动 MAD/光流/速度分析只能提示可能的慢区和尖峰。最终 keep list 由用户决定，并持久化为 human selection manifest。

完整定义见 [`contracts/05-frame-sequence-selection.md`](contracts/05-frame-sequence-selection.md)。

## 插帧与超分

Gate D 后的默认语义是：

```text
用户已批准的时间轴
  -> 插帧，只增加中间状态
  -> 超分，只改变空间分辨率
```

因此：

- 默认插帧不能偷偷执行自动 tail compression/equalize/remap；
- target fps 必须显式记录；
- 循环插帧必须处理最后保留帧到第一保留帧的 wrap interval；
- 超分必须保持已经批准的 fps；
- AI detail 新增纹理爬行/halo/边缘闪烁时回退 temporal-safe。

见 [`contracts/06-interpolation.md`](contracts/06-interpolation.md) 与 [`contracts/07-upscale.md`](contracts/07-upscale.md)。

## Final QC

最终 validator 必须从当前 run state / manifest 读取 expected resolution、fps、frame count 等目标，不能把某个历史样片的 `24fps / 61 frames / 固定 seed` 当作全局门槛。

技术 PASS 也不能替代正常速度连续观看。

见 [`contracts/08-final-validation.md`](contracts/08-final-validation.md)。

---

## 主 Agent 与 Subagent

主 Agent 是 **Spec Owner**。

Subagent 的典型任务是：

```yaml
contract_to_implement:
pipeline_context:
allowed_files:
acceptance:
required_evidence:
```

实现遇到规范冲突时，Subagent 应上报：

```text
CONTRACT_REVIEW_REQUIRED
```

主 Agent 再判断：

```text
IMPLEMENTATION_BUG
CONTRACT_GAP
CONTRACT_CHANGE
```

详细治理见 [`contracts/00-governance.md`](contracts/00-governance.md)。

---

## 当前实现并未完全迁移完成

规范层已经按新生产路线收敛，但现有 scripts/workflows/presets 仍包含历史实现和旧默认。

当前已登记的主要 conformance gaps 包括：

- 正式 1080p 能力仍分散在 `live2d_profile` 和 streaming runner；
- canonical PNG + 1-based keep-list rebuild 还没有完整生产入口；
- 历史 RIFE remap/equalize 路线需要与默认纯插帧路径隔离；
- 当前部分 4K profile 对 fps 有历史固定限制；
- 部分 final validator 仍带固定样片规格；
- 部分 I2V runner 仍有 `LoraStrength=0.5` 的历史默认；
- 旧 profile 名仍含 `draft/final/probe`。

完整、可派工的列表见 [`contracts/CONFORMANCE_STATUS.md`](contracts/CONFORMANCE_STATUS.md)。

因此当前正确的开发方式是：**先读 Contract，再修实现；不能为了迁就旧实现把新 pipeline 改回去。**

---

## Runtime 边界

统一见 [`contracts/01-runtime.md`](contracts/01-runtime.md)。当前核心原则：

- 实际读取 ComfyUI 版本，不根据 8188/8189 猜实例；
- 高占用任务和队列严格串行；
- 默认生产 RAM abort 为 `31.0 GiB`；
- 未授权不自动安装节点/模型、不修改实例、不提高熔断；
- 输入、prompt、canonical frames、人工 manifest、输出和报告不覆盖。

端口、安装路径和某次机器的峰值属于环境/历史事实，不是永久规范。

---

## 项目结构

```text
AGENTS.md                         最高治理、Spec Owner、人工 Gate
README.md                         人类入口
pipeline/                         当前生产状态机
contracts/                        可重建执行规范 + conformance 状态
scripts/                          当前生产 runner/分析/后处理实现
scripts/experimental/             NON-PRODUCTION 历史实验/诊断工具（入库作证据）
workflows/                        当前生产 ComfyUI 实现（API + UI）
workflows/experimental/           NON-PRODUCTION 历史实验工作流（入库作证据）
presets/                          当前实现参数集合
tests/                            实现一致性/回归测试
prompts/                          可复用提示词模板
comfyui_custom_nodes/             Qwen3.6 双语导演自定义节点
config/                           机器配置模板（*.example.yaml 入库；*.local.yaml 本机）
assets/                           占位图等静态资源
history/                          NON-NORMATIVE 历史文档/计划/prompt 归档（含 VALIDATION_HISTORY.md）
inputs/、outputs/、artifacts/、
reports/、logs/、tmp/             运行输入与产物证据（不入库）
```

## 给 Agent 的建议入口

从零制作：

```text
按 AGENTS.md、pipeline 和 contracts 执行。先做 Director Brief；到四个人工 Gate 都停下来让我选择。实现与 Contract 冲突时不要自行改规范，上报主 Agent 做 Contract Review。
```

开发/重构：

```text
先读 contracts/CONFORMANCE_STATUS.md，选择一个 gap。按对应 Contract 实现，不改 pipeline 目标；发现 Contract 本身有问题则上报 CONTRACT_REVIEW_REQUIRED。
```