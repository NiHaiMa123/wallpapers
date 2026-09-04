# 图生视频：Gemini 执行手册

本文档用于让 Gemini 在本项目中逐条运行并审核「图片 → 73 帧 Live2D 风格循环视频」流程。

核心原则：

- 成片固定为 **24 FPS**。
- 每条候选固定为 **73 帧**，时长约 `73 / 24 = 3.0417 秒`。
- Gemini 审片时显式设置 **sampling FPS = 6**，即每 4 个源帧观察 1 帧。
- 一次只生成一个 seed；生成完立刻审核，不批量盲跑。
- 人物动作与精确闪电时序分层处理：H3 负责人像/衣发/四肢，独立合成脚本负责闪电。
- 未通过审核的候选不得命名为 `approved`。

## 1. 项目与运行环境

项目目录：

```text
D:\project\video_uncensored
```

ComfyUI API：

```text
http://127.0.0.1:8188
```

输入图片：

```text
D:\Comfy-Desktop\ComfyUI-Shared\input\keqing_gpt_reference_16x9.png
```

主要文件：

```text
scripts/run_h3_live2d_profile.ps1
scripts/experimental/add_elegant_sword_filaments.py
scripts/experimental/screen_h3_loop_candidates.py
scripts/experimental/make_video_crop_sheet.py
prompts/MINIMAX_H3_LIVE2D_CRYSTAL_LOCK_LOOP_PROMPT_V7_BODY_ONLY.md
presets/minimax_h3_live2d_profiles.json
```

H3 `draft` 配置已经固定：

```text
分辨率：1024 × 576
帧数：73
编码帧率：24 FPS
时长：约 3.04 秒
steps：20
sampler：res_multistep
scheduler：simple
LoRA strength：0.5
```

不要把 Gemini 的 `sampling FPS` 写入 H3 配置。它只控制 Gemini 看视频时抽取多少画面，不改变视频的帧数、播放速度或编码帧率。

## 2. 开始前检查

在 PowerShell 中进入项目：

```powershell
Set-Location 'D:\project\video_uncensored'
```

检查 ComfyUI：

```powershell
Invoke-RestMethod 'http://127.0.0.1:8188/system_stats'
```

确认输入图存在：

```powershell
Test-Path 'D:\Comfy-Desktop\ComfyUI-Shared\input\keqing_gpt_reference_16x9.png'
```

必须串行运行。32 GiB 内存机器上，生成时设置 `-AbortRamGiB 30.5`，禁止同时跑多个 seed。

## 3. 生成一条 24 FPS、73 帧人物底片

从一个未使用的 seed 开始。例如：

```powershell
$seed = 2026083307
$tag = "v7_seed_${seed}_s050"

& .\scripts\run_h3_live2d_profile.ps1 `
  -Profile draft `
  -Seed $seed `
  -LoraStrength 0.5 `
  -LoopLock `
  -Silent `
  -PromptFile .\prompts\MINIMAX_H3_LIVE2D_CRYSTAL_LOCK_LOOP_PROMPT_V7_BODY_ONLY.md `
  -InputImage 'keqing_gpt_reference_16x9.png' `
  -RunReport ".\artifacts\loop_vfi_probe\gemini_runs\run_${tag}.json" `
  -AbortRamGiB 30.5 `
  -Api 'http://127.0.0.1:8188'
```

成功后，视频一般位于：

```text
D:\Comfy-Desktop\ComfyUI-Shared\output\minimax_h3\
```

实际文件名记录在对应的 `run_*.json` 中。不要猜文件名，读取：

```json
output.images[0].filename
```

运行报告必须满足：

```text
status = success
frames = 73
fps = 24.0
output_width = 1024
output_height = 576
```

生成完成后可释放 ComfyUI 模型内存：

```powershell
$body = '{"unload_models":true,"free_memory":true}'
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8188/free' -ContentType 'application/json' -Body $body
```

## 4. Gemini 读取视频时必须使用 6 FPS

Gemini 官方视频接口默认通常按 1 FPS 采样。这个项目动作很短，默认值会漏掉大部分变化，因此必须显式指定：

```text
sampling FPS = 6
```

73 帧、24 FPS 的视频约 3.04 秒。按 6 FPS 审片时，Gemini 大约读取 18–19 张画面，相当于每 4 个源帧取 1 帧。

官方参考：

- https://ai.google.dev/gemini-api/docs/video-understanding
- https://ai.google.dev/gemini-api/docs/generate-content/video-understanding
- https://ai.google.dev/api/generate-content

### Python SDK 示例

本项目视频通常小于 20 MB，可以 inline 发送：

```python
from pathlib import Path

from google import genai
from google.genai import types

VIDEO = Path(r"D:\path\to\candidate.mp4")
MODEL = "models/gemini-3.5-flash"  # 换成当前账号可用的 Gemini 模型

review_prompt = """
这是一个 73 帧、24 FPS、约 3.04 秒的 Live2D 风格循环候选。
你正在以 6 FPS 采样观察它，即大约每 4 个源帧观察一次。
请按本文档的审核标准逐项审查，不要仅总结内容。
输出 PASS 或 FAIL、失败时间点、失败类别和下一步建议。
"""

client = genai.Client()
video_bytes = VIDEO.read_bytes()

response = client.models.generate_content(
    model=MODEL,
    contents=types.Content(
        parts=[
            types.Part(
                inline_data=types.Blob(
                    data=video_bytes,
                    mime_type="video/mp4",
                ),
                video_metadata=types.VideoMetadata(fps=6),
            ),
            types.Part(text=review_prompt),
        ]
    ),
)

print(response.text)
```

关键字段是：

```python
video_metadata=types.VideoMetadata(fps=6)
```

### JavaScript / REST 字段名

JavaScript 或 REST 中使用驼峰形式：

```json
{
  "videoMetadata": {
    "fps": 6
  }
}
```

Google 的新 API 参考已经把 `VideoMetadata` 标记为 deprecated，并建议迁移到 `processing_options`；但当前官方视频理解指南仍使用 `VideoMetadata(fps=...)` 演示自定义采样率。如果安装的 SDK 拒绝 `video_metadata`：

1. 先查看当前 `google-genai` SDK 的 `processing_options` 视频采样字段。
2. 如果当前 SDK 仍支持兼容接口，继续使用 `types.VideoMetadata(fps=6)`。
3. 不得悄悄回退到默认 1 FPS。
4. 实在无法设置时，用下方的 6 FPS 图片序列作为回退，不要只让 Gemini 看默认采样的视频。

### 6 FPS 图片序列回退

如果 Gemini 所在环境不能传 `videoMetadata.fps`，从 24 FPS 视频每 4 帧提取一张：

```powershell
ffmpeg -i 'D:\path\to\candidate.mp4' -vf fps=6 'D:\path\to\review_frames\frame_%03d.png'
```

然后按文件名顺序将这些图片交给 Gemini。不要把 6 FPS 代理视频再按默认 1 FPS 提交，否则仍然只会看到约 3 张图。

## 5. 人物底片审核标准

Gemini 每次只审核一条视频，并返回结构化结果：

```json
{
  "decision": "PASS 或 FAIL",
  "hard_failures": [],
  "motion": {
    "pelvis_root": "",
    "upper_body": "",
    "head": "",
    "hands_arms": "",
    "left_right_legs": "",
    "hair_cloth": ""
  },
  "scene_lock": {
    "crystal": "",
    "petals": "",
    "camera": ""
  },
  "face": "",
  "timestamps": [],
  "next_action": ""
}
```

### 动作目标

- 骨盆是稳定根节点，不发生明显平移。
- 胸肩有小幅呼吸和不到约 1° 的倾斜。
- 头部延迟跟随上身并轻微回弹，不能完全冻结，也不能大幅甩动。
- 手腕、手掌、肘部有 2–4 px 级的小变化，手指形态和持剑关系保持正确。
- 左右腿是两条独立的轻微运动链：大腿从髋部小角度变化，膝部和小腿稍后跟随，脚继承腿链末端运动。
- 两腿不能刚性粘成一个整体，也不能迈步、踢腿或破坏交叉腿轮廓。
- 发梢、丝带、透明袖片、裙摆晚于主运动响应，不应与身体同拍。
- 眼睛保持自然睁开，不能出现长闭眼。

### 场景锁定目标

- 底座和前景紫色水晶带位置、轮廓、透明度结构稳定。
- 不生成或移动花瓣。
- 摄像机固定，无缩放、摇移、旋转、裁切变化。
- 人物身份、服装、手指、剑形不漂移。
- 人物底片阶段不得出现明亮光团、整根光剑或大面积闪电。输入图原本存在的微弱紫色剑纹可以保留。

### 硬失败

出现任意一项立即 `FAIL`：

- 全身一起平移或大幅摆动。
- 骨盆漂移、腿部迈步或交叉轮廓散开。
- 头和上半身完全静止。
- 手完全冻结，或者手指/握持关系损坏。
- 腿完全冻结，或者两腿像一张刚性贴图一起移动。
- 长闭眼、脸部变形或眼睛颜色改变。
- 水晶带摆动、变形或消失。
- 花瓣飞行或新增粒子。
- 剑弯曲、人物肢体重复、明显残影。

### Seed 决策

- 如果只是随机形态失败，保持提示词不变，seed 加 1 再生成一条。
- 同一种失败连续出现两次，才修改提示词。
- 每次修改提示词都另存为新版本，禁止覆盖已验证版本。
- 一条底片通过后立即停止抽 seed，进入独立电丝合成。

## 6. 为通过的底片添加可控电丝

运行：

```powershell
$python = 'D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI H3 0.34 Test\ComfyUI\.venv\Scripts\python.exe'
$inputVideo = 'D:\path\to\passed_body_plate.mp4'
$outputVideo = 'D:\project\video_uncensored\outputs\h3_aesthetic_iterations\candidate_custom_filaments.mp4'
$effectReport = 'D:\project\video_uncensored\artifacts\loop_vfi_probe\gemini_runs\candidate_custom_filaments.json'

& $python .\scripts\experimental\add_elegant_sword_filaments.py `
  $inputVideo `
  $outputVideo `
  --report $effectReport
```

合成脚本读取源视频的 24 FPS，并保持：

```text
输出帧数：73
输出帧率：24 FPS
输出分辨率：1024 × 576
```

默认电丝时序：

```text
第 1 束：帧 8–18
第 2 束：帧 30–40
第 3 束：帧 52–62
边界暗场：帧 0–7、63–72
```

每束由：

- 1 根主丝；
- 2 根更短、更弱的伴随丝；
- 不同长度、起点、折角与收尖；
- 约 10 帧的连续位移；
- 刀尖到达后立即消失；
- 无驻留、无光球、无大电弧、无整根包剑。

默认剑坐标只适用于当前固定构图：

```text
guard = (590, 178)
tip   = (145, 300)
```

如果新 seed 的剑发生可见位移，必须从视频帧重新确认坐标，再传入：

```powershell
--guard X Y --tip X Y
```

不要通过增加 bloom 或亮度来弥补坐标错误。

## 7. Gemini 终审电丝视频

再次让 Gemini 以：

```text
videoMetadata.fps = 6
```

读取合成后的 24 FPS 视频。

终审提示词：

```text
这是一个 73 帧、24 FPS、约 3.04 秒的 Live2D 循环视频。
你必须以 sampling FPS=6 观察，大约每 4 个源帧查看一次。

请重点确认：
1. 骨盆稳定，但胸肩、头、手、左右腿均有小幅且不同相位的运动。
2. 两腿保持交叉轮廓，膝下与脚端有继承式跟随，不是脚单独乱动。
3. 每束电丝沿剑连续前进，不在刀尖停住。
4. 电丝是一根主丝加两根短伴随丝，不得成为平行导轨、光剑、光环或光团。
5. 三束之间有安静暗场，帧 63–72 没有新增电丝。
6. 电丝不穿过脸、手、身体，不脱离剑的邻近区域。
7. 底座水晶和花瓣保持稳定。
8. 首尾回环没有曝光跳变或特效边界跳变。

输出 PASS 或 FAIL，并给出失败时间点。任何刀尖驻留、整根光剑、人物根部漂移或水晶形变都必须判 FAIL。
```

6 FPS 对约 10 帧长的电丝通过过程通常能看到 2–3 个采样画面。它适合审查流向与停滞；首尾精确帧仍需结合本地边界检查。

## 8. 本地技术检查

终审前运行回环筛查：

```powershell
$python = 'D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI H3 0.34 Test\ComfyUI\.venv\Scripts\python.exe'
$video = 'D:\path\to\candidate_custom_filaments.mp4'
$report = 'D:\project\video_uncensored\artifacts\loop_vfi_probe\gemini_runs\candidate_loop.json'

& $python .\scripts\experimental\screen_h3_loop_candidates.py `
  $video `
  --loop-mode return `
  --report $report
```

重点读取：

```text
frames：必须为 73
fps：必须为 24
endpoint_full_mad：越低越好，用于候选间比较
foreground_crystal_step_mad：越低越好
eye_openness_at_last_frame：应接近首帧
```

生成精确帧接触表：

```powershell
& $python .\scripts\experimental\make_video_crop_sheet.py `
  $video `
  '.\artifacts\loop_vfi_probe\gemini_runs\candidate_sword_sheet.jpg' `
  --box 0.10 0.25 0.66 0.55 `
  --indexes 0 8 10 12 14 16 18 30 32 34 36 38 40 52 54 56 58 60 62 66 72 `
  --columns 7 `
  --cell-width 360
```

这张表用于补充 6 FPS 视频采样，确认：

- 三束电丝的逐帧位置确实向刀尖推进；
- 第 18、40、62 帧附近正常消失；
- 第 0 和第 72 帧不存在新增电丝。

## 9. 通过与交付

只有 Gemini 视觉终审和本地技术检查都通过，才复制为：

```text
outputs/h3_aesthetic_iterations/approved_<版本>_seed_<seed>_live2d_filaments.mp4
```

同时保留：

```text
人物底片 run report
人物提示词版本
电丝合成 report
Gemini 审核 JSON/文本
loop screening report
剑区接触表
最终 approved 视频
```

## 10. 已验证参考结果

当前已通过自审的参考视频：

```text
D:\project\video_uncensored\outputs\h3_aesthetic_iterations\approved_v7_seed_2026083306_live2d_filaments.mp4
```

对应文件：

```text
prompts/MINIMAX_H3_LIVE2D_CRYSTAL_LOCK_LOOP_PROMPT_V7_BODY_ONLY.md
scripts/experimental/add_elegant_sword_filaments.py
artifacts/loop_vfi_probe/aesthetic_iterations/approved_v7_seed_2026083306_review.md
artifacts/loop_vfi_probe/aesthetic_iterations/v7_3306_custom_v3_loop.json
```

Gemini 应先读取这条参考视频并以 6 FPS 建立审美基准，再审核新候选。不要把参考视频当成需要重新生成的输入。
