# 00 执行契约

本文件是当前 pipeline 的统一入口。具体角色定义以根 `AGENTS.md` 为准。

## 工作模式

- `PLAN`：只做导演方案、路线、prompt、seed 策略和验收计划，不提交 ComfyUI。
- `DIAGNOSE`：分析已有输入、输出和报告，不自动扩展成新生成任务。
- `REVIEW`：检查候选并给出技术/视觉结论，不替用户越过人工 Gate。
- `EXECUTE`：运行当前最小且有意义的生产阶段。

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
  -> Export All Frames
  -> Gate D 用户选 keep frames
  -> Rebuild
  -> Interpolate
  -> Upscale
  -> Final QC
  -> Delivery
```

已有并被用户认可的输入图可以跳过 T2I / Gate A。

## 人工 Gate 契约

人工 Gate 的状态不是 `PASS`，而是：

```text
WAITING_FOR_USER_SELECTION
SELECTED
```

Agent 可以：

- 初筛明显错误候选；
- 排序；
- 给推荐；
- 提供 MAD/光流/速度等辅助证据。

Agent 不可以：

- 自己代替用户最终选静态图；
- 自己代替用户最终选 video seed；
- 自己代替用户最终选 1080p take；
- 根据自动速度指标擅自决定最终留删帧。

## 全局执行规则

- 同一时刻只跑一个生产任务。
- 复用已验证 runner/workflow/preset，不临时拼装生产工作流。
- 默认静音和固定镜头。
- 常规长任务保留 `31.0GiB` RAM 熔断。
- 不覆盖输入、prompt、视频、帧列、报告或失败证据。
- 进程成功不等于视觉通过。
- 低画质 seed 通过不等于 1080p take 通过。
- 自动分析不等于用户留帧决定。
- 身份/解剖/硬质结构生成错误回到生成阶段，不交给插帧或超分修复。

## 禁止自动扩展

没有用户额外授权时，不执行：

- 下载模型或安装节点；
- 修改 ComfyUI 实例/安装目录；
- 提高 RAM 熔断；
- 删除或覆盖历史文件；
- 切换到仓库未验证的工作流；
- 运行负对照或高风险边界实验。

## 完成契约

### 规划任务

交付：Director Brief、主路线、T2I/I2V prompt 方案、seed 筛选策略、人工 Gate、风险。

### 执行任务

交付必须能追溯：

```text
Director Brief
-> selected image
-> selected video seed
-> selected 1080p take
-> user keep list
-> interpolation
-> upscale
-> final QC
-> final output
```

不得把 Agent 推荐写成用户已选择，也不得把未执行的命令写成已完成。

## 下一阶段

从 `01-intake-and-director.md` 开始。