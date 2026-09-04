# MiniMax H3 本地动态壁纸 Agent 规范

本文件只规定 Agent 的工作方向、权限边界、状态机和交付要求。具体到每个环节的检查项、命令和产物，按 `pipeline/README.md` 及其分阶段文档执行。

## 适用范围

当请求涉及本仓库中的 MiniMax H3、ComfyUI、图生视频、文生图、Live2D 式微动画、静音动态壁纸、循环封装、原生 1080p 或 4K 交付时，使用本规范。

不要把本规范外推到 MiniMax 在线 API、其他 ComfyUI 模型或仓库中没有暴露的参考视频、参考音频能力。

## 执行入口与依据

任何接手本项目的 Agent 都按以下顺序工作：

1. 读取根 `AGENTS.md`，确定职责、权限和不可变约束。
2. 从 `pipeline/README.md` 进入流程，先读 `pipeline/00-operating-contract.md`，再读取当前阶段文档。
3. 运行前核对实际 runner、workflow 和 preset；不要只根据文档猜参数。
4. `README.md` 和验证历史用于理解背景，不替代当前脚本与 preset。

安全、授权和不可变约束以本 `AGENTS.md` 为准；具体运行参数以脚本校验和当前 preset 为事实依据；逐阶段动作和晋级条件以 `pipeline/` 为准。

## 两层职责

### Agent 层

Agent 必须负责：

- 理解用户要的是规划、诊断、生成还是交付；
- 检查输入图、构图、主体、允许动作和禁止变化；
- 选择且只选择一条主路线；
- 设计并保存 UTF-8 可执行提示词；
- 明确 seed、profile、LoRA、静音、循环和验收策略；
- 在提交前检查 API、队列、版本、节点和资源；
- 串行运行仓库脚本并看守 RAM 熔断；
- 实际观看输出，决定淘汰、重试或晋级；
- 生成并验收原生首尾循环、运行技术验证并报告已知缺陷。

### ComfyUI 层

ComfyUI 只负责已经选定的工作流推理、采样、VAE 解码、帧或视频输出。不要让 ComfyUI 图代替 Agent 的路由、提示词、seed 筛选或质量判断。

## 授权边界

- 用户只要求规划、提示词、分析、诊断或评审时，不提交 ComfyUI 任务。
- 用户明确要求“生成、制作、执行、跑工作流”时，可以从预检开始，运行当前最小且有意义的阶段。
- 下载模型、安装节点、修改 ComfyUI 安装目录、提高熔断线、删除历史输出、覆盖文件或改用未验证工作流，必须另行获得用户授权。
- 缺少可选节点时先走已验证的降级路线，不把“缺节点”自动解释为安装许可。

## 项目不变量

- 复用 `scripts/`、`workflows/`、`presets/` 和 validators；不要临时拼装未经验证的 ComfyUI 图。
- ComfyUI 队列严格串行；不要同时运行 Qwen、本地大模型、第二个 H3 任务或高占用后处理。
- 默认保留脚本的 RAM 熔断。日常 H3 任务不得高于脚本验证边界；`31.0GiB` 是当前常规长任务保护线。
- 动态壁纸默认静音；只有用户明确要求音频时才保留音频链。
- Turbo 只用于快速排序 seed；最终母版必须由标准 20 步工作流重新生成并重新验收。
- 不覆盖输入、提示词、输出、运行报告或验收证据；为每次运行使用唯一文件名。
- 不删除失败样片、帧目录或报告。失败结果是后续诊断证据。
- 进程返回成功只代表技术运行完成，不代表画面合格。
- 抽帧检查不能替代正常速度连续观看。

## 默认状态机

执行请求默认按以下状态推进：

```text
INTAKE
  -> ROUTE
  -> INPUT_INSPECTION
  -> PROMPT
  -> PREFLIGHT
  -> SEED_SCREEN
  -> LOOPLOCK_DRAFT_20_STEP
  -> LOOPLOCK_LONG_DRAFT
  -> LOOPLOCK_FINAL_20_STEP
  -> DIRECT_LOOP_REVIEW
  -> TECH_VALIDATION
  -> DELIVERY
```

每一阶段只有三种结果：`PASS`、`REJECT`、`BLOCKED`。只有 `PASS` 可以晋级；`REJECT` 必须回到最近能改变问题的阶段；`BLOCKED` 必须记录具体阻碍和安全降级路线。

用户可以明确限制只运行某一阶段。除非用户明确接受风险，否则不得跳过一个仍有未解决质量问题的便宜阶段，直接运行昂贵 final。

## 默认决策

- 已有输入图且用户要求直接图生视频：跳过文生图，走外部图片 I2V 路线。
- 没有成人动作 LoRA 意图：默认 `-LoraStrength 0`，提示词中不写 `hmmotion`。
- LoRA 强度大于 0：提示词必须以 `hmmotion` 开头，并在报告中记录强度。
- 稳定优先的壁纸：固定镜头，只允许 2–3 个相容的低幅运动系统。
- 动态壁纸默认使用 `-LoopLock`，让同一输入图直接锚定首帧和末帧；从标准 `draft` 开始直到 `final` 都保持该模式。
- 不使用后期正放与反向拼接。落花、烟雾、飞行粒子等单向事件必须改成局部闭合轨迹、原位明暗变化或完全静止。
- 首尾画面相同不等于速度连续。LoopLock 把首尾都钉在源图上，末端不要停死；片头片尾保持同量级余速穿过边界，并在正常速度循环播放中检查顿感。
- 4K 默认 `temporal_safe`；只有动态观看确认 AI 超分没有纹理爬行时才选 AI detail。
- 原生 1080p 直接循环先用支持 `-LoopLock` 的批量短档验证；当前逐帧 runner 未暴露 `last_frame`，扩展并重新验证前不能用于循环交付。

## 晋级门槛

- Turbo：只看构图、身份和大方向，不能定稿。
- Draft：必须是标准 20 步，并确认 Turbo 排名在标准模型下仍成立。
- Long draft：检查长时漂移、末帧状态、背景重构和动作累积。
- Final：必须重新观看，不能继承 long draft 的结论。
- Loop：必须同时通过正常速度连续观看和技术 validator。
- 4K：必须确认没有新增纹理爬行、光晕呼吸、边缘闪烁、黑帧或色阶变化。

身份、脸、手、肢体、剑或道具出现明显错误时直接淘汰 seed；不要用插帧、交叉融合或超分掩盖生成错误。

## 运行记录

执行时至少记录：

- 输入图绝对路径、尺寸和 SHA-256；
- 提示词文件路径和 SHA-256；
- API、ComfyUI 版本和队列状态；
- 实际运行命令、profile、seed、步数、LoRA、静音、LoopLock；
- prompt ID、输出路径、运行报告路径；
- 耗时、峰值 VRAM、峰值 RAM 和是否接近熔断；
- 视觉结论、已知缺陷、技术验证结果和下一步。

不要把计划运行的命令写成已经完成的事实。

## 交付契约

规划请求交付：创意简报、主路线、可执行提示词、seed 梯度、预计命令、验收条件和风险。

执行请求交付：实际成片、母版、提示词、运行报告、关键参数、视觉结论、validator 结果、已知缺陷和未执行的可选升级。

## Pipeline 索引

从 `pipeline/README.md` 开始。Agent 根据当前状态读取对应章节：

- `pipeline/00-operating-contract.md`
- `pipeline/01-intake-and-routing.md`
- `pipeline/02-preflight.md`
- `pipeline/03-input-and-prompt.md`
- `pipeline/04-seed-screening.md`
- `pipeline/05-standard-render.md`
- `pipeline/06-visual-review.md`
- `pipeline/07-loop-and-validation.md`
- `pipeline/08-delivery-and-reporting.md`
- `pipeline/09-native-1080p-and-4k.md`
- `pipeline/10-failure-recovery.md`
