# 05 标准分级生成

所有晋级循环母版必须使用标准 20 步并传 `-LoopLock`，不使用 Turbo LoRA。

## Profile 梯度

| Profile | 规格 | 用途 |
|---|---|---|
| `draft` | 1024×576，73 帧，24fps，20 步 | 标准 seed 复核 |
| `long_draft` | 864×480，124 帧，24fps，20 步 | 长时漂移和末端检查 |
| `final` | 1344×768，124 帧，24fps，20 步 | 最终 H3 母版 |

以 `presets/minimax_h3_live2d_profiles.json` 为准。`1344×768` 只是默认 `final` 档，不是 runner 写死的唯一分辨率。原生 1080p 用同一 runner 换 `1080_smoke` / `1080_short` / `1080_probe_73` / `1080_probe_84` 等 profile，内部 `1920×1088` 再无裁切缩到 `1920×1080`；73 帧是本机已通过的需看守边界，84 帧是用户授权的下一档探针，90 帧是负对照。细节见 `09-native-1080p-and-4k.md`。

## Draft

```powershell
$inputImage = '<absolute-image>'
$promptFile = '.\prompts\generated\<prompt>.txt'
$seed = 2026090201
$loraStrength = 0

.\scripts\run_h3_live2d_profile.ps1 `
  -Profile draft `
  -Seed $seed `
  -LoraStrength $loraStrength `
  -InputImage $inputImage `
  -PromptFile $promptFile `
  -RunReport '.\reports\<unique-draft-report>.json' `
  -LoopLock `
  -Silent
```

实际观看并通过后才进入 long draft。

## Long draft

保持输入、prompt、seed、LoRA 和 silent 不变，只改 profile：

```powershell
.\scripts\run_h3_live2d_profile.ps1 `
  -Profile long_draft `
  -Seed $seed `
  -LoraStrength $loraStrength `
  -InputImage $inputImage `
  -PromptFile $promptFile `
  -RunReport '.\reports\<unique-long-draft-report>.json' `
  -LoopLock `
  -Silent
```

重点看 5.17 秒内的累积漂移、眨眼、姿态、背景、硬质物体，以及末段是否停死。

## Final

```powershell
.\scripts\run_h3_live2d_profile.ps1 `
  -Profile final `
  -Seed $seed `
  -LoraStrength $loraStrength `
  -InputImage $inputImage `
  -PromptFile $promptFile `
  -RunReport '.\reports\<unique-final-report>.json' `
  -LoopLock `
  -Silent
```

final 是昂贵且接近 32GB 内存边界的阶段。运行前重新确认队列为空、没有 Qwen/LLM、报告路径唯一，并保留 `31.0GiB` 熔断。

## 运行看守

- 只通过 `scripts/run_h3_live2d_profile.ps1` 提交。它用 `scripts/h3_build_live2d_payload.py` 组 payload；不要对变异后的工作流对象做 `ConvertTo-Json -Depth 50`，这次实跑会把 PowerShell 工作集打到 10GiB 以上且还没进队列。
- 该 runner 在成功、失败或 RAM 熔断后都会 `/free` 并等待内存下降。不要改回跑完不释放。
- 脚本返回 session 时持续轮询；长任务每 30–60 秒向用户报告一次有变化的状态。
- 记录峰值 VRAM、RAM、距离熔断的余量和释放后的 RAM/VRAM。
- 达到熔断时接受中断，不自动提高阈值重跑。
- 跨 ComfyUI 会话同 seed 可能分叉；final 必须重新验收。

## 输出整理

ComfyUI 原始输出保留不动。`-LoopLock` 输出本身就是直接首尾循环候选，复制时不要重新编码：

```text
outputs/candidates/   draft 和 seed 候选
outputs/masters/      通过验收的 LoopLock 母版
outputs/wallpapers/   同一份循环壁纸副本
reports/              runner 结构化报告
```

## 晋级条件

当前 profile 的进程成功，并且按 `06-visual-review.md` 得到 `PASS`。二者缺一不可。
