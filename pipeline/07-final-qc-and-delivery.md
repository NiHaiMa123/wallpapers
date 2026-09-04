# 07 最终 QC 与交付

本阶段只验收已经完成“Gate D -> 重建 -> 插帧 -> 超分”的最终候选。

执行契约：

- `../contracts/08-final-validation.md`
- `../contracts/09-artifacts-and-reports.md`

## Expected Spec

最终 QC 开始前必须先从当前 run state 明确：

```yaml
expected_resolution:
expected_fps:
expected_frame_count:
expected_silent:
expected_codec:
expected_pixel_format:
loop_intent:
```

Validator 必须对这份 expected spec 验证；不得使用某个历史样片写死的 24fps、61 frames、seed 或固定循环次数作为全局规范。

## 正常速度视觉 QC

至少连续观看多个循环，检查：

- 身份、脸、眼睛、手、肢体；
- 武器/饰品/水晶/建筑等硬质结构；
- 镜头稳定；
- 尾段节奏；
- wrap 抽动、速度突变或假溶解；
- RIFE 鬼影；
- 超分纹理爬行、halo、轮廓呼吸、边缘闪烁；
- 边界亮度/色彩跳变。

## 技术 QC

按 `contracts/08-final-validation.md` 做参数化验证，包括可解码性、尺寸/fps/帧数、PTS、stream、黑帧、faststart、hash 和多轮解码稳定性。

技术 validator 可以报告 boundary MAD 等指标，但不能替代正常速度视觉判断。

## 判定

- `PASS`
- `PASS_WITH_WARNINGS`
- `REJECT`
- `BLOCKED`
- 如 validator 本身无法表达当前 Contract：`CONTRACT_REVIEW_REQUIRED`

## 交付追溯

最终交付必须满足 `contracts/09-artifacts-and-reports.md`，至少追溯到：

```text
Director Brief
-> selected image
-> selected seed
-> selected 1080p take
-> canonical frame sequence
-> user keep list
-> rebuilt sequence
-> interpolation
-> upscale
-> final validation
-> final output
```

## 回退

若失败，回到最近能够真正改变缺陷的阶段，而不是降低 validator 门槛让旧实现通过。

- 生成结构问题 -> 04 或更早；
- keep-list 时序问题 -> 05；
- RIFE 问题 -> 06 的 interpolation；
- upscale 问题 -> 06 的 upscale；
- validator implementation mismatch -> Contract Review / 修 validator。

## 完成标准

用户可以直接找到最终文件，并能通过 manifests/reports 还原它来自哪次导演方案、哪张图、哪个 seed、哪个 take、哪些人工保留帧以及哪些后处理。