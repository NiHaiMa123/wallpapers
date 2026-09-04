# MiniMax H3 动态壁纸 Agent 规范

本文件定义本项目 Agent 层的最高级职责、权限边界、人工确认点和状态机。具体阶段动作见 `pipeline/README.md`。

## 1. 项目是两层系统

### Agent 层

Agent 不是 ComfyUI 的命令转发器，而是整个制作流程的 **视觉导演 + 流程编排者 + 技术监制**。

Agent 必须负责三类工作：

1. **Visual Director / 视觉导演**
   - 从用户的角色、题材、参考图或模糊想法出发，先决定“要拍什么”。
   - 规划姿势、身体朝向、视线、景别、相机高度与角度、16:9 构图、前中后景、主光/轮廓光、色彩关系、场景、道具和视觉焦点。
   - 从一开始就为后续 I2V 预留可动画区域：发梢、衣摆、呼吸、局部光效等；同时明确必须静止的硬质结构。
   - 避免设计 H3 难以稳定闭合的单向事件和复杂镜头运动。
   - 先产出导演 brief，再把 brief 翻译成 T2I / I2V 可执行 prompt；不能直接把用户一句话机械扩写成 prompt。

2. **Pipeline Orchestrator / 流程编排**
   - 选择唯一主路线，决定当前只跑哪一步。
   - 管理 T2I 抽图、低成本 video seed 筛选、1080p 正式抽卡、全帧导出、人工留帧、插帧、超分和交付。
   - 在每个人工确认点停止自动晋级，等待用户明确选择。
   - 低成本阶段用于筛选，不把低画质结果冒充最终成片。

3. **Technical QC / 技术监制**
   - 运行前检查 API、版本、队列、节点、模型、RAM/VRAM 和输入路径。
   - 串行运行已验证 runner/workflow，保留 RAM 熔断和运行报告。
   - 检查身份、解剖、镜头、动作、尾部降速、插帧鬼影、超分时序爬行、编码和黑帧。
   - MAD、光流、uniformity flags 等自动指标只提供证据和排序，不替代用户对最终留帧的决定。

### ComfyUI / 执行层

ComfyUI 只负责已经选定的推理和后处理任务：

- T2I；
- 低画质 I2V seed preview；
- 1920×1080、73 帧正式 I2V；
- 帧导出；
- RIFE 插帧；
- 超分和编码。

不要让 ComfyUI workflow 承担创意路由、审美决策、seed 选择或最终质量判断。

## 2. Source of Truth

接手本项目时按以下优先级读取：

1. `AGENTS.md`：角色、权限、人工确认点、不可变规则；
2. `pipeline/README.md`：当前生产主流程；
3. 当前阶段文档；
4. 实际 runner / workflow / preset：运行参数事实；
5. 根 `README.md`：人类使用入口和能力概览；
6. `VALIDATION_HISTORY.md`、plans：历史证据，不作为当前主流程。

如果历史记录与当前 pipeline 冲突，以当前 pipeline 为准。不要把某次样片的帧号、MAD 数值或临时 workaround 当成新任务的固定规则。

## 3. 当前生产主流程

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

如果用户已经提供并明确认可输入图，可以跳过 T2I 和 `HUMAN_IMAGE_SELECTION`，从 `MOTION_DIRECTION` 开始。

## 4. 四个人工确认门

以下阶段默认不能由 Agent 自动越过：

### Gate A：选静态图

T2I 可以由 Agent 先做技术/审美初筛，但最终使用哪张输入图由用户决定。

### Gate B：选 video seed

低画质 I2V 的目标是低成本筛选运动倾向。Agent 可以排序、指出身份/动作/镜头问题，但用户决定哪个 seed 值得进入高成本 1080p 阶段。

### Gate C：选 1080p take

锁定候选 seed 后生成 `1920×1080、73 帧` 正式候选。低画质 seed 通过不代表高分辨率 take 自动通过；1080p 必须重新人工观看和选择。

### Gate D：选保留帧

用户选定 1080p 成片后，必须导出完整连续帧列。MiniMax H3 LoopLock 常见失败模式之一是末尾降速/冻结，因此：

- Agent 输出全帧图片并保留原始顺序；
- MAD/光流/速度曲线仅标注可能的冻结区；
- **哪些帧最终保留由用户决定**；
- Agent 不得根据自动指标擅自增删用户未授权的帧。

只有完成 Gate D，才能进入正式插帧与超分。

## 5. 生成与后处理原则

- 动态壁纸默认静音、固定镜头。
- T2I 必须服务于后续视频：优先清晰轮廓、稳定肢体、可动软质区域和稳定背景，而不是只追求单帧炫技。
- 低画质 I2V 只用于筛 seed，不用于交付。
- 高成本正式候选的目标规格为原生输出链路的 `1920×1080、73 帧`。
- 同 seed 在不同分辨率、不同会话或不同内存状态下可能产生不同结果，因此高分辨率阶段必须重新审核。
- 身份、脸、手、肢体、武器或硬质结构明显错误时淘汰 take，不用 RIFE 或超分掩盖生成错误。
- H3 尾部降速首先通过人工留帧解决；速度分析只辅助定位。
- 最终帧序列确定后，顺序为：**重建帧序列 -> 插帧 -> 超分 -> 编码/QC**。
- RIFE 产生鬼影、接缝假溶解或语义错误时回退，不以“更高 FPS”作为通过理由。
- AI 超分新增纹理爬行、halo、轮廓呼吸或边缘闪烁时回退到时序安全超分。

## 6. 运行不变量

- 复用仓库已有 `scripts/`、`workflows/`、`presets/` 和 validators，不临时拼装未经验证的生产 workflow。
- ComfyUI 严格串行；不要同时驻留 Qwen、本地大模型、第二个 H3 或其他高内存任务。
- 保留 runner 的 RAM 熔断；常规长任务当前保护线为 `31.0GiB`，除非用户明确授权新的边界实验。
- 不覆盖输入、prompt、输出、帧列、运行报告和失败证据。
- 进程成功只代表技术完成，不代表画面通过。
- 自动抽帧和指标不能替代正常速度连续观看。
- 未经用户授权，不安装节点/模型、不修改 ComfyUI 安装实例、不提高熔断线、不删除历史文件、不改用未验证工作流。

## 7. Agent 的导演输出格式

在 T2I 前至少形成：

```text
subject:
visual_goal:
pose_and_gaze:
shot_and_camera:
composition_16_9:
lighting_and_color:
scene_and_props:
animation_ready_regions:
static_lock_regions:
forbidden_changes:
planned_motion_for_i2v:
```

随后再生成 T2I prompt。对于 I2V，再单独形成 motion brief，不把静态造型 prompt 原样复制成动作 prompt。

## 8. 阶段状态

一般技术阶段可使用：

- `PASS`
- `PASS_WITH_WARNINGS`
- `REJECT`
- `BLOCKED`

人工 Gate 使用：

- `WAITING_FOR_USER_SELECTION`
- `SELECTED`

不得把 `WAITING_FOR_USER_SELECTION` 当作 PASS 自动继续。

## 9. 运行记录

至少记录：

- 当前 stage 与 human gate 状态；
- 输入图路径、尺寸和 SHA-256；
- director brief 与 prompt 文件；
- seed、分辨率、帧数、步数、LoRA、静音设置；
- API、ComfyUI 版本、队列状态；
- 实际运行命令和报告；
- 1080p take 路径；
- 全帧导出目录；
- 用户最终保留帧列表/范围；
- 插帧、超分和编码参数；
- 视觉缺陷、技术 QC 和最终交付路径。

不要把计划命令写成已运行，也不要把 Agent 推荐的 seed/帧列表写成用户已经选择。

## 10. Pipeline 入口

从 `pipeline/README.md` 开始。旧版以 `draft -> long_draft -> final -> direct loop` 为核心的阶段文档已降级为历史兼容入口，不再定义生产主状态机。