# 10 Capability Baseline / 可重建能力基线

## Purpose

本文件定义从空实现重建当前项目时，执行层至少需要具备哪些 **模型能力、节点语义和媒体能力**。

它不固定 PowerShell/Python 文件名、ComfyUI 节点编号或端口；这些属于实现自由。但如果缺少这里的能力，就不能宣称已经重建当前生产系统。

## 1. MiniMax H3 基础模型能力

当前生产基线使用 MiniMax H3 FL2VA。重建时至少需要以下三类权重能力：

| 能力 | 当前已验证文件 | 历史已验证 SHA-256 |
|---|---|---|
| H3 diffusion model | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a` |
| H3 text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6` |
| H3 video VAE | `minimax_h3_video_vae_fp16.safetensors` | `7c1f131492e7eddacaac9069a61b81bdd39de5cc96561e677c5eab1cdce5e522` |

生产主线默认静音，因此 **audio VAE 不是当前生产必需依赖**。若未来用户要求音频，应新增/修改 Contract，而不是因为旧 workflow 曾包含 audio VAE 就自动恢复音频链。

### Model substitution

如果未来使用字节不同但能力等价的新量化/官方权重：

- subagent 不得静默替换；
- 先报告模型差异、兼容性和回归证据；
- 主 Agent决定是实现升级还是 Contract Change。

上表 SHA 是“当前已验证基线身份”，不是声明未来只能使用这些字节。

## 2. H3 图生视频所需语义节点

实现必须能表达等价于以下能力：

```text
Load selected image
Load H3 diffusion model
Load H3 text encoder
Load H3 video VAE
Build MiniMax H3 image-to-video conditioning
Apply optional model LoRA when explicitly enabled
Select sampler / scheduler
Inject deterministic video seed
Sample latent
Decode video frames
Scale/format visible output when required
Save canonical PNG frame sequence
```

当前已验证标准采样基线：

```yaml
steps: 20
sampler: res_multistep
scheduler: simple
```

这些值是当前正式 H3 生产基线。改变正式采样算法需要主 Agent审核回归证据；低成本 screening 可以使用不同采样方式，但必须标记 `screening_only`。

## 3. H3 帧长约束

当前 H3 节点已验证的合法时序长度遵循：

```text
frames = 5 + 17k,  k >= 0
```

例如：

```text
5, 22, 39, 56, 73, 90, 107, 124, ...
```

当前正式 Contract 固定选择 `73`。如果未来 H3 节点约束改变，应由主 Agent更新本能力基线和受影响 Contract。

## 4. 正式循环生成语义

正式 1080p take 必须能表达：

```text
selected image -> first-frame anchor
same selected image -> last-frame anchor
```

也就是 `contracts/04-native-1080p-73f.md` 的：

```text
same_image_first_last_anchor
```

具体 ComfyUI 实现可以是 `last_frame` 输入、LoopLock wrapper 或等价机制，但只提供 first-frame I2V 的工作流不符合正式 take Contract。

## 5. T2I 基线能力

当前 H3 pseudo-T2I 方案利用 H3 的最短合法 5-frame 时序生成后，从结果中抽取静态候选。

重建当前能力至少需要：

```text
text prompt
-> H3 5-frame generation
-> VAE decode
-> retain full candidate evidence
-> select/extract one or more still frames as T2I candidates
```

当前基线仍使用标准 20-step `res_multistep/simple`。

Pseudo-T2I 是当前已验证实现策略，不是永远不可替换的产品语义；如果未来引入更合适的静态图模型，只要 `contracts/02-t2i.md` 保持满足，可由主 Agent受控升级。

## 6. Low-cost seed screening capability

当前可使用 Turbo 作为粗筛实现。历史已验证 Turbo 权重：

```text
minimax_h3_turbo_v4_step600_ema.safetensors
SHA-256: 5f3a626cd72c93a8b9318d6760c510bc5092d2ab13aaba1f932c5bab07a416d3
```

Turbo 不是正式母版采样器。若 Turbo 当前只能 first-frame I2V，应按 `contracts/03-lowres-i2v-seed.md` 标记：

```yaml
screening_only: true
loop_semantic_match: false
```

没有 Turbo 时，可以用标准低分辨率 H3 做 seed screening；缺 Turbo 本身不允许自动安装第三方节点。

## 7. Optional HMNSFW LoRA capability

历史已验证可选 LoRA：

```text
HMNSFW-AIO-V2.5.safetensors
SHA-256: a07732a84fd733085eb5d910f602f918fa7a3658117116927e4329f5951a9d2d
```

规范默认：

```yaml
lora_enabled: false
lora_strength: 0
```

只有当前任务明确启用时才加载。强度 0 的实现应真正 bypass 不必要的 LoRA loader，而不是仅把强度写 0 后仍强制加载模型。

## 8. Canonical frame output capability

正式 1080p take 必须支持：

```text
H3 decode
-> visible 1920x1080 image frames
-> direct PNG sequence on disk
-> contiguous manifest
```

必须能验证：

- 数量；
- 顺序；
- 分辨率；
- 可解码性；
- 黑/空帧；
- 每帧 human number 映射；
- hash/manifest。

Native ComfyUI `SaveImage` 当前已观察为 1-based 文件计数，但 **文件名实现不是 Contract**；Contract 只要求最终 human mapping 统一 1-based。

## 9. Interpolation capability

当前已验证 baseline engine：

```text
RIFE v4.26
model filename: rife_v4.26.safetensors
```

执行层必须具备：

- 加载视频或 canonical/rebuilt frame sequence；
- 相邻帧插值；
- cyclic wrap interval 插值；
- 显式 target fps；
- 输出 frame-count 可预测和验证；
- 不默认执行 timing remap。

如果使用其他 VFI，只要满足 `contracts/06-interpolation.md` 并经 conformance review 即可。

## 10. Upscale capability

至少需要一个 deterministic temporal-safe 空间缩放器。当前基线可使用 Lanczos。

可选 AI detail baseline：

```text
RealESRGAN_x4plus.pth
```

AI detail 不是生产必需能力；缺少它时 temporal-safe 路线仍可完整交付。

## 11. Media encoding capability

生产实现至少要能输出：

```yaml
container: mp4
codec: h264
pixel_format: yuv420p
silent: true
faststart: true
```

当前常用质量基线：

```yaml
crf: 18
encoder_tune: animation
```

具体 encoder preset 可以根据资源/实现调整，但必须写入 run report；如改变会影响质量门槛，应重新做 regression。

## 12. Validation capability

至少需要：

- frame-sequence validator；
- generic media/loop validator；
- SHA-256；
- normal-speed visual review；
- 可选 MAD/光流/motion-uniformity 诊断。

自动 motion analysis 是辅助能力，不是人工 Gate 替代品。

## 13. Capability vs implementation rule

以下属于能力规范，应在 MD 中存在：

- 正式模型能力类别；
- 正式采样语义；
- 合法帧长约束；
- first/last anchor；
- canonical frame sequence；
- cyclic interpolation；
- fps-preserving upscale；
- parameterized validation。

以下通常属于实现自由，不应在多个 MD 中复制：

- workflow node id（如 `6`, `17`, `20`）；
- PowerShell 函数名；
- localhost 端口；
- `D:\...` 安装路径；
- 某个临时 RunId；
- 某次样片的 MAD/PSNR；
- 某个历史输出文件名。

当主 Agent 不确定一个新发现属于哪一类时，使用 `CONTRACT_REVIEW_REQUIRED`。