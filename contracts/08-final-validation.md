# 08 Final Validation Contract

## Purpose

定义与具体历史样片无关的最终技术/视觉验收。Validator 必须参数化或从最终 run manifest 读取目标规格，不能把某个历史样片的 `24fps / 61 frames / 某个 seed` 写死成全局生产门槛。

## Inputs

```yaml
candidate:
expected_resolution:
expected_fps:
expected_frame_count:
expected_silent:
expected_codec:
expected_pixel_format:
loop_intent:
generation_and_postprocess_manifests:
```

其中 `expected_*` 来自当前生产状态和 Contract，不来自历史 validator 的默认值。

## Technical checks

至少检查：

- 可完整解码；
- 实际宽高与 expected resolution 一致；
- fps 与 expected fps 一致；
- decoded frame count 与 expected frame count 一致；
- 只有预期 stream；动态壁纸默认 silent；
- codec / pixel format 满足当前交付规格；
- PTS 存在、严格递增且 cadence 稳定；
- 无黑帧/空帧；
- 重复多轮解码结果稳定；
- faststart（MP4 适用时）；
- 最终 SHA-256；
- 上游 manifest/hash 能追溯到 selected image -> seed -> take -> keep list -> interpolation -> upscale。

## Loop checks

技术 validator 可以报告：

- last-to-first pixel/MAD difference；
- boundary motion proxy；
- repeated-cycle decode consistency。

这些指标 **不能单独判定视觉循环自然**。Loop 最终必须在正常速度连续播放中由 Agent/用户视觉审核。

## Visual QC

至少检查：

- 身份、脸、眼睛、手、肢体；
- 武器/饰品/水晶/建筑等硬质结构；
- 镜头稳定；
- 尾段节奏；
- wrap 速度突变/抽动/假溶解；
- RIFE 鬼影；
- 超分纹理爬行/halo/边缘闪烁；
- 边界亮度/色彩跳变。

## Result states

- `PASS`
- `PASS_WITH_WARNINGS`
- `REJECT`
- `BLOCKED`

Validator 的技术 PASS 不自动等于最终视觉 PASS。

## Historical thresholds

历史报告中的 MAD、PSNR、frame count、minimum cycles 等值可以作为回归参考，但除非被主 Agent明确提升进当前 Contract，否则不能作为全局固定门槛。

## Outputs

```yaml
candidate:
candidate_sha256:
expected_spec:
actual_spec:
technical_checks:
loop_metrics:
visual_qc:
known_defects:
traceability:
status:
```

## Acceptance

最终交付必须满足当前 expected spec，并同时有技术验收与正常速度视觉验收。