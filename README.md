# MiniMax H3 本地动态壁纸工作流

> [!CAUTION]
> **18+ / Adults Only.** 本仓库包含可选成人内容 LoRA 的本地工作流。仅供已达到法定成年年龄的用户在符合当地法律的前提下使用。未明确要求时，Agent 不自动启用成人动作 LoRA。

本项目是一套在 **RTX 5080 16GB + 32GB 系统内存**环境中持续验证的 MiniMax H3 / ComfyUI 动态壁纸制作系统。

项目重点不是“让 ComfyUI 自己全自动做完视频”，而是把制作过程分成两层：

- **Agent 层**：视觉导演、流程编排、人工确认点管理、技术 QC；
- **ComfyUI / scripts 层**：文生图、图生视频、帧导出、插帧、超分和编码执行。

当前规范入口：

- Agent 最高级规则：[`AGENTS.md`](AGENTS.md)
- 当前生产流程：[`pipeline/README.md`](pipeline/README.md)
- 历史实验与验证：[`VALIDATION_HISTORY.md`](VALIDATION_HISTORY.md)

---

## 当前生产思路

```text
视觉导演规划
  -> 文生图抽卡
  -> 用户选静态图
  -> 动作导演
  -> 低画质 I2V 筛 video seed
  -> 用户选 seed
  -> 1920×1080 / 73帧正式抽卡
  -> 用户选正式 take
  -> 导出全部帧
  -> 用户决定最终保留哪些帧
  -> 重建帧序列
  -> RIFE 插帧
  -> 超分
  -> 最终 QC
  -> 交付
```

如果用户已有并明确认可的输入图，可以跳过文生图阶段，直接从动作导演和 I2V seed 筛选开始。

## 为什么这样设计

### 1. Agent 必须先当导演

文生图不是简单扩写提示词。Agent 应先决定：

- 角色姿势、朝向和视线；
- 景别、相机高度与角度；
- 16:9 构图和视觉重心；
- 主光、轮廓光和颜色关系；
- 场景、道具和前中后景；
- 哪些区域以后要动；
- 哪些硬质结构必须锁死；
- 后续 I2V 适合出现的 2–3 个运动系统。

然后才把这个 Director Brief 转成 T2I prompt。

### 2. 低画质视频只负责找 Seed

固定输入图和 motion prompt，用低成本 I2V 批量筛 video seed。

Agent 可以先淘汰脸崩、肢体错误、镜头漂移、动作方向错误的候选，并给 seed 排名；但最终由用户决定哪个 seed 值得进入高成本 1080p 阶段。

### 3. 1080p 必须重新抽卡和人工确认

低分辨率 seed 的运动倾向不能保证在高分辨率、不同 ComfyUI 会话中完全复现。

所以选定 seed 后，正式生成目标为：

```text
1920×1080
73 frames
silent
```

内部 H3 空间尺寸、具体 profile 和 runner 参数以当前脚本/preset 校验为准。

1080p 正式 take 必须重新观看，由用户选定真正进入后期的版本。

### 4. H3 尾部降速通过人工留帧解决

MiniMax H3 首尾锚定视频常见问题之一是末尾回位时降速甚至冻结。

当前策略不是让自动指标直接删帧，而是：

1. 把用户选中的 1080p take 完整导出为连续图片；
2. MAD、光流、motion uniformity 标记可能的冻结区；
3. 用户查看完整帧列；
4. 用户明确决定最终保留/删除哪些帧；
5. Agent 严格按用户 keep list 重建序列。

自动分析是证据，不替代用户的留帧决定。

### 5. 最终才做插帧和超分

最终帧序列确定后：

```text
重建序列 -> RIFE 插帧 -> 超分 -> 编码 / QC
```

生成错误不能交给后处理修：脸、手、肢体、武器、硬质结构或背景严重重构时，应重新抽 take / seed。

RIFE 出现鬼影、接缝假溶解时回退；AI 超分新增纹理爬行、halo、轮廓呼吸或边缘闪烁时回退到时序安全路线。

---

## 四个人工确认点

| Gate | 用户决定什么 | Agent 可以做什么 |
|---|---|---|
| A | 使用哪张静态图 | 初筛结构错误、分析构图、给推荐 |
| B | 哪个 video seed 进入 1080p | 批量低成本抽卡、排序、指出缺陷 |
| C | 哪个 1080p / 73f take 进入后期 | 技术检查、正常速度观看、速度风险分析 |
| D | 最终保留哪些帧 | 导出完整帧列、提供 MAD/光流参考、执行用户 keep list |

Agent 不得把 `WAITING_FOR_USER_SELECTION` 当作 PASS 自动越过。

---

## ComfyUI 层负责什么

ComfyUI 是执行器，不是导演。

当前能力包括：

- H3 伪文生图 / T2I；
- 外部图片进入 H3 I2V；
- 低成本 seed preview；
- 原生 1080p 短视频；
- LoopLock 首尾锚定；
- 帧序列输出；
- RIFE / FrameInterpolate；
- 2K / 4K 超分；
- 静音视频输出。

具体命令、节点和 profile 以当前 `scripts/`、`workflows/`、`presets/` 为事实依据。文档不把某个端口永久绑定到某个 ComfyUI 版本；运行前必须读取实际服务版本。

---

## 资源与运行边界

- ComfyUI 队列严格串行。
- H3 运行时不要同时驻留 Qwen、本地大模型、第二个 H3 或其他高内存任务。
- 常规长任务保留 runner 的 `31.0GiB` RAM 熔断；不要因为接近 32GB 仍能运行就自动抬高阈值。
- 动态壁纸默认静音。
- 不覆盖输入、prompt、输出、全帧目录和运行报告。
- 失败样片和报告保留作为诊断证据。
- 进程退出成功不代表画面合格。

本机共享路径和实际 ComfyUI 端口可能随实例切换而变化。Agent 应通过 runner、配置和 API 实际响应确认，不根据 README 中的旧端口说明猜测服务身份。

---

## 推荐目录

```text
inputs/imported/       输入副本
prompts/generated/     Director Brief 转出的执行提示词
outputs/candidates/    T2I / seed / 1080p 候选
outputs/images/        选定 take 的完整帧列
outputs/masters/       用户确认后的中间母版
outputs/wallpapers/    最终成片
outputs/review/        抽帧、拼图和视觉证据
artifacts/             MAD、光流、RIFE 等诊断产物
reports/               runner 和最终 QC 报告
```

---

## 给 Agent 的最短指令示例

从零制作：

```text
按照 AGENTS.md 和当前 pipeline 制作一张动态壁纸。先以导演视角设计画面和后续可动画区域，再做文生图。到每个人工 Gate 都停下来让我选择，不要自动越过。
```

已有图片：

```text
这张图已经确定。按照当前 pipeline 做动作导演，然后低画质筛 video seed；让我选 seed 后再跑 1920×1080、73帧正式候选。选片后导出全部帧让我决定保留帧，最后再插帧和超分。
```

---

## 项目结构

```text
AGENTS.md                         Agent 角色、权限、人工 Gate 和状态机
pipeline/                         当前生产流程
README.md                         人类入口与当前工作方式
VALIDATION_HISTORY.md             历史验证、失败路线和实验数据
scripts/                          运行、分析、插帧、超分和验收工具
workflows/                        ComfyUI API / UI 工作流
presets/                          生成与后处理 profile
prompts/                          可复用和生成的提示词
comfyui_custom_nodes/             项目自定义节点
plans/                            阶段性实验计划
outputs/、artifacts/、reports/    产物和证据
```

旧版 `pipeline/01-intake-and-routing.md` 到 `pipeline/10-failure-recovery.md` 只保留路径兼容和迁移提示，不再定义当前生产主状态机。