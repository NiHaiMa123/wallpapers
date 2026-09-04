> [!WARNING]
> **NON-NORMATIVE HISTORICAL EVIDENCE.** 本文件记录 2026-09-03~04 的变速/equalize/remap 实验与当时定稿，不定义当前生产主线。当前 Gate D 之后默认遵循 `../contracts/05-frame-sequence-selection.md` 与 `../contracts/06-interpolation.md`：用户 keep list 是时间轴事实，未明确授权时不自动 equalize、tail compression 或 remap。若本文证据提示当前 Contract 有问题，应提交 `CONTRACT_REVIEW_REQUIRED` 给主 Agent，而不是直接恢复本文方案。

# 变速调节链路修复计划（plan2）——✅ 2026-09-04 封版（65f 定稿交付候选）

> 来源：2026-09-03 代码评审。对象：`scripts/retime_video_no_interpolation.py`、
> `scripts/equalize_motion_speed.py`、`scripts/equalize_loop_per_frame.py`、
> `scripts/remap_rife_timeline.py`、`scripts/analyze_motion_uniformity.py`。
> 约束：遵守根 `AGENTS.md`（不覆盖既有文件、唯一文件名、RAM 熔断、串行运行）；
> 运行脚本必须用 ComfyUI 的 `.venv` python（系统 python 缺 av/torch/psutil）。

## 总目标

1. 修掉评审发现的逻辑 bug（wrap 尺度失配、越界计数、末帧保护、失真变速比）。
2. 把刻晴专用硬编码改成显式参数，让链路可用于其他视频。
3. 每一步都有可重复的验证命令和通过标准；任何一步失败就停下，不带病进入下一步。

## 步骤 1 — wrap 运动量尺度修复（`equalize_motion_speed.py`）【P0】

- **目标**：wrap 区间分到的帧数与片内区间使用同一尺度，不再系统性欠采样。
- **改动**：
  - `plan_loop_indices` 中 wrap 预算改按"路径归一化"估算（wrap_arc 除以 dense 微步 target 前，
    先乘以系数 `wrap_path_factor = wrap_coarse_arc / mean(dense_wrap_neighbor_steps)`，
    或给 wrap 独立的 `target_step_wrap`），新增 `--wrap-budget-mode` 参数保留旧行为可回退；
  - `collect_dense` 倍率反推失败时抛错，不再静默回退（`linear_count % source_frames != 0` 即报错）。
- **验证**：
  - `python -m py_compile scripts/equalize_motion_speed.py` 通过；
  - 用 reports 中 `keqing_draw02_v3_seed2026090224_1080p73_motion_eq_wrap3_RUN.json` 的同源输入重跑，
    新报告 `wrap_frames_used` 与旧值对比，变化方向符合预期（wrap 帧数增加）且输出帧数符合 `requested_frames`；
  - `analyze_motion_uniformity.py` 复测输出，`loop_wrap_jump` 不新增、tail/mid 不恶化。
- **通过标准**：编译过 + 回归输出帧数正确 + uniformity flags 不差于旧报告。
- **执行记录（2026-09-03）**：
  - 第一版（path 预算 + 绝对式 `round(wrap_total/target_step)`）：wrap 3→7 帧，但 uniformity 恶化
    （tail/mid 0.697→0.452，新增 `tail_too_slow`，cv 0.262→0.364）——未达通过标准。
  - 根因：`--keep-duration` 下 `n_out` 由时长固定，绝对式 wrap 预算不再与总预算成比例，
    wrap 被超分 3.5 倍（0.356/帧 vs 片内 1.35/帧），尾部被拖慢。
  - 追修：`plan_loop_indices` 改按比例分配 `round(n_out * wrap_total / total)`
    （非 keep-duration 时与旧式一致）。重跑命名 `*plan2_step1b*`。
  - step1b 结果：wrap 2 帧，73/73 帧，时长 3.0417s 对齐；uniformity 与旧 wrap3 成片对比
    flags 相同（`end_freeze,loop_wrap_jump`，无新增），cv 0.262→0.227、tail/mid 0.697→0.730、
    last_ratio 0.055→0.087、wrap MAD 3.269→2.992 全优。**步骤 1 通过 ✅**

## 步骤 2 — `retime_video_no_interpolation.py` 小 bug 修复【P0】（✅ 2026-09-03 通过）

- B（删末帧 72）：`ValueError: Refusing to drop last frame (72) without --allow-drop-last` 拦截 ✅
- A（`--drop-frames "0,99999"`）：告警 + `ignored_out_of_range=[99999]`，`dropped_frames=1`，
  `frames=72`，`effective_speed_ratio=1.2329=(72/19.2)/(73/24)` 自洽 ✅
- C（复刻 v3 删除列表）：`dropped=[64,65,66,67,69,70,71]`、`frames=66`、`duration=3.4375s`
  与旧报告完全一致，仅新增字段 ✅

- **目标**：报告诚实、LoopLock 安全。
- **改动**：
  - dropped 索引先与实际帧数取交集再计数，越界索引写入报告 `ignored_out_of_range` 并告警；
  - `--drop-frames` 手动指定末帧时告警（`--allow-drop-last` 显式放行才允许）；
  - 新增 `effective_speed_ratio = (frames/fps) / (src_frames/src_fps)`，保留旧 `speed_ratio` 字段。
- **验证**：
  - `py_compile` 通过；
  - 构造越界 case（`--drop-frames 0,99999`）重跑 66f v3 同源输入，`dropped_frames` 不再虚增；
  - 删末帧 case 触发告警/拦截；
  - 输出时长与 `effective_speed_ratio` 自洽。
- **通过标准**：三组 case 全部符合预期，旧合法输入行为不变（diff 旧报告仅新增字段）。

## 步骤 3 — 去硬编码：region / 阈值 / min_wrap 参数化【P1】（✅ 2026-09-03 通过）

- `equalize_motion_speed.py` `--region` 必填；显式传参重跑 step1b：输出 sha 与 step1b **完全一致**
 （`5b37a599…`），target/wrap/2 帧/73 帧全同 ✅
- `remap_rife_timeline.py`：`--tail-search-start/--tail-threshold-ratio` 参数化、`--target-fps` float 化、
  重复帧告警 + `--allow-duplicates`；旧输入重跑 `tail_start=62`、`target_frames=226`、
  `duplicates=0`、阈值 `0.28767` 与旧报告一致（`target_fps` 记为 60.0 预期内）✅
- `equalize_loop_per_frame.py`：`--min-wrap` 默认 24→0，docstring + 报告注明 global-MAD 局限 ✅
- `analyze_motion_uniformity.py`：6 个 flags 阈值参数化，默认值复测 flags/数值不变 ✅
- 残留 grep：`0.42…` 仅剩 help 示例、`0.70/0.30` 为声明式 argparse 默认、`min_wrap.*24` 无命中 ✅

- **目标**：换视频不用改代码。
- **改动**：
  - `equalize_motion_speed.py`：`--region` 无默认值（必传），`--metric` 保留默认但报告记录；
    移除 hair 默认值 `0.42,0.08,0.78,0.42`。
  - `remap_rife_timeline.py`：`--tail-search-start`（默认 0.70）、`--tail-threshold-ratio`（默认 0.30）参数化；
    `--target-fps` 改 float，支持 19.2；
    cyclic 重复帧去重或 `--allow-duplicates` 显式放行。
  - `equalize_loop_per_frame.py`：`--min-wrap` 默认改为 0（按需注入，不再强制 24 帧）；
    MAD 全局阈值允许 `--region` 限定（与 equalize 对齐）或明确记录"全局 MAD"局限。
  - `analyze_motion_uniformity.py`：flags 阈值改可传参（`--flag-cv`、`--flag-tail-fast/slow` 等），保留现默认值。
- **验证**：每个脚本 `--help` 可见新参数；旧命令加显式参数后输出与旧报告一致（bit 级允许编码差异，以帧数/flags 为准）。
- **通过标准**：零硬编码内容假设残留（grep `0.42,0.08`、`0.30`、`min_wrap.*24` 无命中默认值）。

## 步骤 4 — 大视频流式解码【P2】（✅ 2026-09-03 通过）

- `equalize_loop_per_frame.py` 重写为三遍流式：pass0 量 MAD（仅标量累积）→ pass1 生成 dense 落盘
  temp（steps 在 raw 像素上量，与旧版同源）→ pass2 从 temp 选帧出片；常驻仅首/末/上一/当前数帧；
  temp 成功失败都删除；新增 `--dense-crf`（12）、`--max-dense-frames`（20000）+ 落盘量打印。
- 回归（257f@90fps）：dense=292、extras 9/26、wrap kept 7、输出 244 帧，`selected` 与旧报告
  **244/244 完全一致**；uniformity flags 一致（`end_freeze,loop_wrap_jump`），windows/cv/tail 基本相同；
  内存打印 `1.69 GiB if resident; spilling to temp` ✅
- 诚实记录两处偏差：① `measure_mapping` 未改——它本来就只存 480 宽缩略图（~150MB/300 帧），
  不是真凶；② pixel 级 stats 有漂移（`rgb_last_to_first` 0.42→2.02，temp crf12 + 终编 crf10 双重压缩），
  motion 级统计一致——这是 spill 的固有代价，可用 `--dense-crf` 调。

- **目标**：4K / 长视频不爆内存。
- **改动**：
  - `measure_mapping` 改两遍流式：第一遍按需解码采样（只保留 small gray/rgb），不再常驻全量；
  - `equalize_loop_per_frame.densify` 改边算边写（分段 encode），`dense` 不再全放内存；
  - 新增 `--flow-width` 下限校验与内存预估打印（预估 > 8GiB 直接拒绝并提示分段）。
- **验证**：1080p 回归输出帧数/flags 不变；用 4K 输入试跑 through（或至少内存预估路径可达）。
- **通过标准**：回归一致 + 内存占用随帧数呈常数/线性流式特征（不再一次性 N 帧常驻）。

## 执行纪律

- 每步独立 commit 意向（是否 commit 由用户定），产物文件名唯一，旧报告只读。
- 每步结束汇报：改了什么、验证命令、输出 diff 结论、是否达到通过标准。
- 任一步未达标准即停，修好之前不进下一步。

## 实战记录 run60（2026-09-03）：直出 1080p73 → 匀速 → 60fps

- 输入：`keqing_draw02_v3_seed2026090224_looplock_1080p_73f_wallpaper.mp4`（73f@24fps，基线
  cv 0.505、tail/mid 0.44，`end_freeze,tail_too_slow,loop_wrap_jump`）。
- equalize（复用同源 RIFE 4x cyclic + wrap16）：输出与 step1b sha 一致，确定性 ✅。
- ComfyUI RIFE 4x（serving 实例输入目录是 `ComfyUI-Shared\input`，不是安装目录下的 input；
  输出落 `output/` 根而非 `postprocess/`——路径必须读报告，不硬编码，已同步到 pipeline/07）：
  289f@96fps，峰值 RAM 19.76GiB。
- remap 60fps（speed 1.0、tail factor 1.0）：181f@60fps，3.0167s，duplicates 0；
  发现无尾部时 `source_tail_step_mean_mad` 写 NaN（非法 JSON）→ 已修为 null，重跑 `run60b` 验证 ✅。
- 终测：flags `end_freeze,loop_wrap_jump`，cv 0.319、tail/mid 0.74；validator `passed=true`
 （20/20 cycles，pts/black/checksum 全 0）。画面语义待用户审核。
- 用户拒收（末尾顿感 + 尾部变色）。变色根因：wrap RIFE 段整体比源片暗 ~7%（G），
  末尾两帧取自该段 → 新增 `scripts/match_segment_brightness.py`（ref 段均值/方差对齐），已验证对齐。
- 顿感根因：LoopLock 首尾同图，模型进站减速是结构性的（0224/0227 双 seed 同症状），
  后期只能删不能造。用户授权 B 方案：删 176–179（4 帧）留锚点 180 → 177f@60fps 2.95s，
  末步 0.598（均值 109%/片头 84%）。终测 cv 0.285、tail/mid 0.84、last_ratio 0.20（仍 <0.40 线）、
  wrap 2.80，validator 通过。`end_freeze` flag 仍报，体感由用户终审。
