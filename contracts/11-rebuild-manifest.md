# 11 Rebuild Manifest / 从 MD 重建实现

## Purpose

本文件回答：**如果 `scripts/`、`workflows/`、`presets/`、validators 都不存在，主 Agent 应按什么顺序重新搭建当前项目？**

这里定义需要重建的模块和验收边界，不要求复刻旧文件名或旧代码结构。

## 0. 重建前读取顺序

```text
AGENTS.md
-> pipeline/README.md
-> contracts/README.md
-> contracts/00-governance.md
-> contracts/10-capability-baseline.md
-> 本文件
-> 当前阶段对应 Contract
```

`history/`（含 `VALIDATION_HISTORY.md`）只在需要历史证据/回归基线时读取。

## 1. Runtime foundation

实现一个公共 runtime layer，至少负责：

```text
resolve API endpoint
read actual ComfyUI version
query queue/system stats/object info
check required capabilities
resolve/publish input files
SHA-256
unique RunId/output allocation
RAM abort/watchdog
interrupt/free/release
structured run report
```

验收：`contracts/01-runtime.md`、`09-artifacts-and-reports.md`。

不要先复制旧 runner；先建立所有生成任务共享的 runtime contract adapter。

## 2. H3 workflow builder

从 `contracts/10-capability-baseline.md` 重建标准 H3 graph/payload builder，能够参数化：

```yaml
input_image:
prompt:
width:
height:
frames:
steps: 20
sampler: res_multistep
scheduler: simple
seed:
lora_enabled:
lora_strength:
first_anchor:
last_anchor:
silent:
output_mode: video | canonical_frames
```

正式生产必须支持 `first_anchor == last_anchor == selected image`。

验收：构造出的 payload 能通过 ComfyUI node validation，且参数可以从 report 反向验证。

## 3. T2I production module

实现：

```text
Director Brief
-> versioned T2I prompt file
-> H3 pseudo-T2I 5-frame run
-> candidate still extraction
-> candidate manifest/report
-> Gate A artifacts
```

最低要求：

- prompt file + SHA；
- seed；
- 候选图 hash；
- 不自动越过 Gate A。

验收：`contracts/02-t2i.md`。

## 4. Low-res seed-screen module

实现一个批量但串行的 seed screening runner：

```text
selected image
+ fixed motion prompt
+ seed set
-> low-cost previews
-> per-seed report
-> comparison manifest
```

允许 Turbo 粗筛，但必须记录 `screening_only` 和 `loop_semantic_match`。

生产 wrapper 默认不启用可选成人动作 LoRA。

验收：`contracts/03-lowres-i2v-seed.md`。

## 5. Formal 1080p / 73f production module

这是正式 I2V 核心。实现必须一次完成：

```text
selected image
+ selected seed
+ motion prompt
+ same-image first/last anchor
-> H3 internal 1920x1088
-> visible 1920x1080
-> 73 canonical PNG frames
-> preview MP4
-> frame manifest
-> run report
```

正式 production entry 不应要求 Agent 记住额外的 `-LoopLock` 才正确；正式入口本身就必须符合 Contract。

验收：`contracts/04-native-1080p-73f.md`。

## 6. Canonical frame validator + Human Gate D module

实现：

1. 校验 canonical PNG 数量/顺序/尺寸/hash；
2. 创建 1-based human frame manifest；
3. 生成供用户查看的帧列/联系表等 review artifact；
4. 接受用户 keep/drop 表达；
5. 规范化成 `approved_by_user: true` 的 1-based selection manifest。

任何 0-based index 只能存在于内部实现边界之后。

验收：`contracts/05-frame-sequence-selection.md`。

## 7. Rebuild selected sequence

实现一个 **以 canonical PNG + human selection manifest 为唯一输入** 的重建器。

必须：

- 只复制/读取 keep frames；
- 不从压缩 MP4 重新解码作为主路径；
- 不自动 equalize；
- 不自动改变 fps；
- 输出 rebuilt sequence manifest/hash；
- 能做 dry-run 显示 1-based -> internal mapping。

建议测试：

```text
keep first frame
keep last frame
keep 1-63,73
single gap
multiple ranges
out of range
empty list
duplicate input
unordered user expression
```

验收：`contracts/05-frame-sequence-selection.md`、`09-artifacts-and-reports.md`。

## 8. Pure cyclic interpolation module

实现：

```text
human-approved rebuilt sequence
+ source fps
+ explicit target fps
-> dense cyclic interpolation
-> target-fps output
```

默认不能进入 `equalize_motion_speed` / `remap_rife_timeline` 等自动时序修正逻辑。

RIFE v4.26 是当前 baseline engine；具体 wrapper 可替换。

必须有 frame-count expectation test 和 wrap test。

验收：`contracts/06-interpolation.md`。

## 9. FPS-preserving upscale module

实现空间超分器：

```text
input video at approved fps
-> target resolution
-> same fps
-> same temporal ordering
```

至少实现 `temporal_safe`。AI detail 为可选模块。

不得用“当前 preset 没有 60fps”作为自动降到 24fps 的理由；profile 应从输入/target spec 参数化生成或选择。

验收：`contracts/07-upscale.md`。

## 10. Generic final validator

实现一个从 expected spec/manifest 驱动的 validator：

```text
candidate + expected spec
-> media probe
-> frame/PTS/stream checks
-> repeated decode
-> loop metrics
-> traceability checks
-> validation report
```

禁止硬编码某个历史样片的：

- 61 frames；
- 24fps（除非该 run expected fps 就是 24）；
- 119 cycles；
- 固定 seed；
- 单一 MAD 门槛作为视觉 PASS。

验收：`contracts/08-final-validation.md`。

## 11. Preset / workflow generation policy

`presets/*.json` 和 `workflows/*.json` 在 MD-first 架构中属于 **实现配置/编译产物**。

主 Agent可以选择：

- 手工维护但用 tests 验证 Contract；
- 从一个结构化 source config 自动生成；
- 由 workflow builder 动态构造，不保存大量静态 JSON。

无论哪种方式，都不能让同一个生产事实只存在 preset 而 Contract 没有。

适合留在 preset 的内容：

- 具体 encoder preset；
- tile/overlap；
- 实验档参数；
- implementation-specific model path/name；
- smoke test 档位。

必须回到 Contract 的内容：

- 生产目标 1080p/73f；
- same-image first/last anchor；
- user 1-based frame numbering；
- Gate D 后默认不自动 remap；
- upscale 保持 fps；
- validator 参数化。

## 12. Tests required before declaring reconstruction complete

至少建立：

```text
runtime preflight tests
payload/graph invariant tests
same-image first/last anchor test
formal 1080p profile contract test
canonical frame sequence numbering test
1-based keep-list mapping tests
pure interpolation no-retime test
cyclic wrap interpolation test
fps-preserving upscale test
generic validator variable-fps/frame-count tests
artifact no-overwrite + traceability tests
```

测试不一定全部需要跑高成本 H3；能静态验证的 Contract 应优先静态/单元测试，高成本路径再用 smoke/integration test。

## 13. Reconstruction completion definition

只有满足以下条件，主 Agent才能声明“实现层已从 MD 重建完成”：

1. `CONFORMANCE_STATUS.md` 中生产相关项均为 `CONFORMING` 或主 Agent明确接受的 `UNVERIFIED` 风险；
2. 每个 pipeline stage 都有可执行 production entry；
3. 每个 production entry 都能追溯到对应 Contract；
4. 四个人工 Gate 均能持久化用户决定；
5. formal 1080p take 天然满足 first/last anchor + canonical frames，不依赖 Agent记住隐藏开关；
6. Gate D 后没有隐藏自动时序修改；
7. upscale 保持 approved fps；
8. final validator 接受动态 expected spec；
9. 所有关键实现差异有 tests/evidence；
10. 历史实验工具仍可保留，但不会被误当 production default。