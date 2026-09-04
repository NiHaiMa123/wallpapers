# 04 原生 1080p / 73f 正式抽卡

本阶段在 Gate B 已选定 video seed 后生成正式高成本 take，并完成 Gate C。

执行契约：`../contracts/04-native-1080p-73f.md`

## 输入

- Gate A 选定静态图；
- motion brief / motion prompt；
- Gate B 选定 seed；
- 当前 LoRA / loop intent；
- runtime state。

## 阶段动作

1. 按 `contracts/01-runtime.md` 做执行前检查。
2. 按 `contracts/04-native-1080p-73f.md` 生成正式 take。
3. 同 seed 可以有多个正式 take，但每个都必须独立记录。
4. Agent 对每个 take 做正常速度观看和结构初审。
5. 保留正式 take 对应的 canonical PNG frame sequence；不要等 Gate C 后再从有损 MP4 重新拆一份作为唯一源。
6. 向用户展示正式候选和差异说明。

## Gate C

```text
WAITING_FOR_USER_SELECTION
```

用户选择后记录：

```yaml
selected_take:
selected_take_sha256:
selected_frame_sequence_dir:
selection_notes:
status: SELECTED
```

## 淘汰规则

身份、脸、手、肢体、武器、硬质结构或镜头出现严重生成错误时淘汰该 take；不交给后续 RIFE、删帧或超分修复。

尾部降速/冻结如果主体质量仍可接受，不必在本阶段自动修；进入 Gate D 的人工帧选择。

## 本阶段不重复定义

- H3 内部空间尺寸；
- visible output 尺寸转换；
- frame-sequence 命名；
- loop anchor 的实现方式；
- runner/profile 名称。

这些由 `contracts/04-native-1080p-73f.md` 定义语义，由实现自行满足。

## 晋级

Gate C 完成 -> `05-frame-selection.md`。

实现如果只有 `probe/smoke` 入口、无法满足正式 take Contract，属于 implementation conformance 问题，不得把实验 profile 语义反写进 pipeline。