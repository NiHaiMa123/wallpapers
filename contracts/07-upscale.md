# 07 Upscale Contract

## Purpose

把已经通过插帧/时序观看的候选提升到目标分辨率，同时不改变已批准时间轴。

## Inputs

```yaml
input_video:
input_sha256:
input_resolution:
input_fps:
target_resolution:
upscale_profile:
temporal_priority:
```

目标分辨率和输入 fps 必须从当前 run state 获取。Contract 不把“24fps”写死为 4K 的永久条件；实现必须支持对已批准 fps 的等时序超分，或在不支持时进入 `CONTRACT_REVIEW_REQUIRED` / `BLOCKED_CAPABILITY_MISSING`，不能偷偷改回 24fps。

## Profiles

### temporal_safe

默认生产路线。目标：只提升空间分辨率，不引入模型生成的新纹理时序。

可以使用 Lanczos 或后续经验证的等价确定性缩放器。

### ai_detail

可选路线。允许使用 RealESRGAN 等模型增加空间细节，但必须重新做人眼动态审查。

AI detail 不是默认质量必然更高；如果新增时序伪影，必须回退 `temporal_safe`。

## Required invariants

- 保持输入 fps；
- 保持输入帧顺序和帧数，除非编码容器的技术行为有明确、可验证的等价表示；
- 不进行额外插帧、删帧、时间重映射；
- 不加入音频；
- 输出尺寸必须与目标规格一致；
- 记录实际算法、模型、tile/overlap（如果适用）和编码参数；
- 输入和输出都有 SHA-256。

## Forbidden behavior

- 因当前 preset 只支持某 fps 就自动改变用户已确定 fps；
- 在超分阶段自动做 RIFE；
- 用 AI detail 修复原生成中的脸/手/结构错误；
- 因单帧更锐就忽略动态纹理爬行。

## Visual rejection conditions

- texture crawl；
- halo；
- edge shimmer；
- outline breathing；
- 局部锐度周期性变化；
- 色偏/亮度跳变；
- AI 生成细节在帧间改变身份或材质。

## Outputs

```yaml
input_sha256:
input_fps:
input_frames:
profile:
method:
model:
target_resolution:
output_fps:
output_frames:
output:
output_sha256:
run_report:
temporal_review:
```

## Acceptance

空间规格通过，时间轴保持不变，正常速度观看没有新增不可接受的时序问题。