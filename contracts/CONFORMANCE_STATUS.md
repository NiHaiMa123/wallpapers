# Implementation Conformance Status

本文件记录 **当前实现与 normative MD Contract 的一致性状态**。它不是新的规范来源；目标行为仍由各 Contract 定义。

主 Agent 在给 subagent 分派实现任务前应先看本文件，并在实现/验证完成后更新状态。

状态：

- `CONFORMING`：已有证据表明当前生产实现满足 Contract；
- `PARTIAL`：部分能力存在，但还有明确缺口；
- `NONCONFORMING`：现有默认/入口与 Contract 冲突；
- `UNVERIFIED`：可能满足，但缺 conformance evidence。

## 当前已知差异（2026-09-04）

### C-001 正式 1080p / 73f 入口语义分裂 — PARTIAL

Contract：`04-native-1080p-73f.md`

现状：

- `run_h3_live2d_profile.ps1` 能表达 1080p/73f + 可选 LoopLock，但 profile 名仍是历史 `1080_probe_73`，默认 profile 是 `draft`；
- `run_h3_1080_stream.ps1` 更适合 canonical PNG frame sequence、RunId、watchdog 和外部编码，但当前 workflow 没有正式 loop/last-frame anchor 语义；
- 生产能力被两个实验时代 runner 分拆，没有一个“不可误用”的正式入口。

目标：由 subagent 按 Contract 收敛为一个明确 production entry，并提供 conformance tests。

### C-002 Gate D canonical keep-list rebuild — NONCONFORMING

Contract：`05-frame-sequence-selection.md`

现状：

- 正式需求是 canonical PNG -> 1-based human keep list -> rebuild；
- 现有 `retime_video_no_interpolation.py` 主要从压缩视频解码，并将 `--drop-frames` 解释为 0-based Python index；
- 用户侧帧号是 1-based，缺少正式转换/manifest 层。

目标：实现以 canonical PNG 为源的 1-based keep-list rebuild，并对 1/73、范围、越界、顺序做测试。

### C-003 插帧后的时间轴纯净性 — PARTIAL

Contract：`06-interpolation.md`

现状：

- `run_rife_video_interpolation.py` 已有 RIFE/cyclic 能力；
- 仓库同时存在 `remap_rife_timeline.py`、`equalize_*` 等历史自动重定时路径；
- 缺一个明确 production wrapper/manifest，保证 Gate D 后默认只插帧、不自动 tail compression/remap。

目标：建立纯插帧 production path；历史 remap/equalize 保留为显式可选实验/诊断，不作为默认。

### C-004 高 fps -> 4K Contract — NONCONFORMING

Contract：`07-upscale.md`

现状：

- `run_4k_upscale.ps1` 严格要求输入 fps 等于 profile fps；
- 当前 4K `temporal_safe` / `ai_detail_default` profile 主要写死 24fps；
- 60fps 只有部分 2K profile；
- 因此人工定稿后插到 60fps 再做 4K 的主线不能由现有默认 profile 无歧义完成。

目标：让空间超分保持输入已批准 fps，或提供等价参数化 profile，不允许自动降回 24fps。

### C-005 Final validator 被历史样片规格污染 — NONCONFORMING

Contract：`08-final-validation.md`

现状：

- `validate_wallpaper_4k.py` acceptance / check 名称含固定 `24fps`、`61 frames`、固定最低循环等历史样片门槛；
- 人工 keep list 后 frame count 本来就是变量；插帧后 fps 也可能变化。

目标：validator 从 current expected spec / final manifest 读取尺寸、fps、frame count 等参数。历史阈值只做 regression profile。

### C-006 可选 HMNSFW LoRA 默认值 — NONCONFORMING

相关：`AGENTS.md`、T2I/I2V contracts

现状：

- 部分 I2V runner 默认 `LoraStrength = 0.5`；
- 当前项目规则是未明确启用可选成人动作 LoRA 时不能自动启用。

目标：生产入口默认不启用可选成人动作 LoRA；显式启用时记录参数和 prompt 语义。

### C-007 T2I 可追溯 prompt/report — PARTIAL

Contract：`02-t2i.md`, `09-artifacts-and-reports.md`

现状：

- pseudo-T2I runner 可接受 prompt 字符串/seed；
- 但生产 Contract 希望 Director Brief、prompt file/hash、候选和 run report 完整追溯。

目标：补正式 T2I wrapper/report 或证明现有路径已等价满足 Contract。

### C-008 旧 runner/profile 命名仍含 draft/final/probe — PARTIAL

规范层已经移除旧 `draft -> long_draft -> final` 生产状态机，但实现文件仍保留这些历史 profile 名。

这本身不要求删除历史能力，但主 Agent不能把它们当新 pipeline 的默认入口。若继续保留，应区分 `legacy/experimental` 与 `production`。

## 历史文档冲突已被规范层隔离

以下旧结论目前 **不是实现 bug，而是历史证据**：

- `plans/H3_1080_LOOP_STRATEGY_NOTES.md` 的“镜像回放已定案”；
- 旧 crossfade / 61-frame / 119-loop validator 方案；
- `plan2.md` 的 equalize/remap 定稿链；
- `VALIDATION_HISTORY.md` 中不同日期的 RAM 边界/默认值。

这些文档已经被 `AGENTS.md` 明确降级为 NON-NORMATIVE。它们可以为 Contract Review 提供证据，但不得直接恢复为当前生产规则。

## 更新规则

Subagent 完成实现后不能自行把状态改成 `CONFORMING`，除非主 Agent明确授权其同时做 conformance review。

主 Agent确认时应记录：

```yaml
item:
status:
implementation_files:
tests:
evidence:
reviewed_by: main_agent
review_date:
remaining_risks:
```
