# MiniMax H3 本地视频工作流

> [!CAUTION]
> **18+ / Adults Only.** 本仓库包含成人内容（NSFW LoRA，HMNSFW-AIO-V2.5）的工作流、下载器与提示词模板。仅供已达到法定成年年龄的用户在符合当地法律的前提下使用。未成年人请离开。
>
> **18+ / Adults Only.** This repository contains workflows, downloaders, and prompt templates for adult content (NSFW LoRA, HMNSFW-AIO-V2.5). Intended only for users who have reached the age of majority, in compliance with local laws.

本项目是一套已经在 **RTX 5080 16GB + 32GB 系统内存**上实跑验证的 MiniMax H3 / ComfyUI 本地工作流，覆盖：

- H3 伪文生图（5 帧短时序包抽取单帧）；
- 外部图片或 H3 首图进入 I2V；
- HMNSFW V2.5 可开关图像/运动分支；
- 精致手办、实时二游 CG 与类 Live2D 低幅微动画；
- Turbo 4/8 步 seed 预筛与标准 20 步母版；
- 静音无缝循环、1 分钟技术验证与 4K 输出；
- Qwen3.6 双语提示词导演和最多四张参考图的定向视觉提取；
- ComfyUI 0.34 原生首尾锚定与短片段原生 1080p；
- 1080p 逐帧落盘与外部流式编码，输出阶段内存与帧数解耦。

项目的调研依据、逐阶段数据、失败路线和 SHA-256 记录集中在 [VALIDATION_HISTORY.md](VALIDATION_HISTORY.md)。

## Agent 与 Pipeline 层

项目使用仓库级 `AGENTS.md` 和 `pipeline/` 作为 Agent 层：Agent 负责把创意需求转换为本地 H3 提示词、原生首尾循环设计、seed 筛选阶梯、现有 ComfyUI 运行命令和验收结果；ComfyUI 继续负责实际推理和输出。

可直接对 Codex 说：

```text
按照本项目 AGENTS.md 和 pipeline，把这张角色图制作成静音动态壁纸。先设计动作提示词并筛 seed，通过 long_draft 后再决定是否跑 final。
```

或只做方案而不生成：

```text
按照本项目 pipeline，分析这张图如何使用 LoopLock 直接完成首尾循环，只输出提示词和运行计划，不提交 ComfyUI。
```

项目级方向与安全约束位于根目录 `AGENTS.md`，完整执行入口位于 `pipeline/README.md`。其他 Agent 接手时只需从这两个文件开始，不依赖额外的自动发现机制。

## 当前结论

这套链路技术上可用，但 32GB 内存是接近下限的配置，不是宽裕配置。日常运行必须保持 ComfyUI 队列串行，并避免同时驻留其他大型扩散模型或本地 LLM。

推荐默认路线：

```text
Qwen 提示词导演（可选）
  → H3 文生图抽卡或外部输入图
  → H3 I2V 多 seed 筛选
  → 标准 20 步 LoopLock draft / long_draft / final
  → 同一输入图直接锚定首帧和末帧
  → 1 分钟循环技术验证
  → temporal_safe 4K（可选）
```

关键边界：

- 稳定主实例为 ComfyUI `0.33.1`，API 默认 `http://127.0.0.1:8188`。
- 原生任意帧锚定与 1080p 验证使用独立 ComfyUI `0.34` 测试实例，API `http://127.0.0.1:8189`；不要为了这些能力直接覆盖主实例。
- 标准稳定档是 `1024×576 × 73 帧`；`1344×768 × 124 帧`虽已跑通，但峰值内存约 30.40GiB。
- 原生 1080p 必须内部生成 `1920×1088`，再无裁剪缩放为 `1920×1080`。统一上限测试中 39、56、73 帧完整通过，90 帧在 `CreateVideo` 达到 31.11GiB 后中断；日常推荐上限为 56 帧，73 帧只作为清理后台后的边界档。
- 逐帧落盘 + 外部流式编码已跑通到 73 帧且峰值更低（30.18GiB vs 30.58GiB），但 90 帧仍然中断：瓶颈已从 `CreateVideo` 移到 `VAEDecode` + `ImageScale` 的双批次驻留。它的价值是输出阶段内存与帧数无关、失败现场可检查，不是解锁更长片段。
- 所有长任务保留 `31.0GiB` RAM 熔断；不要并发生成。
- 4K 默认使用 `temporal_safe`（Lanczos）。RealESRGAN 更锐，但实测会增加时序纹理爬行，只作为可选档。

## 已安装环境

本机验证路径如下；若迁移到其他机器，需要相应修改脚本参数或配置：

| 项目 | 路径或地址 |
|---|---|
| ComfyUI 主实例 | `D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI` |
| ComfyUI 主 API | `http://127.0.0.1:8188` |
| ComfyUI 0.34 测试 API | `http://127.0.0.1:8189` |
| 共享模型 | `D:\Comfy-Desktop\ComfyUI-Shared\models` |
| 共享输入 | `D:\Comfy-Desktop\ComfyUI-Shared\input` |
| 共享输出 | `D:\Comfy-Desktop\ComfyUI-Shared\output` |
| ComfyUI Python | `D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe` |
| UI 工作流安装目录 | `D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\user\default\workflows\MiniMax H3` |

最小模型集：

| 文件 | 模型目录 | 大小 |
|---|---|---:|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `diffusion_models` | 20,970,379,616 B |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `text_encoders` | 15,687,142,551 B |
| `minimax_h3_video_vae_fp16.safetensors` | `vae` | 5,207,808,496 B |
| `minimax_h3_audio_vae_fp32.safetensors` | `vae` | 605,254,808 B |
| `HMNSFW-AIO-V2.5.safetensors` | `loras` | 86,040,232 B |

下载器位于 `scripts/download_h3_models.ps1`、`scripts/download_hmnsfw_v25.ps1` 和 `scripts/download_h3_turbo_v4.ps1`。下载器采用 `.part`、断点续传、大小与 SHA-256 双校验，不会把未完成文件暴露给 ComfyUI。

## 最快使用方式：ComfyUI 图形界面

侧栏 `MiniMax H3` 下已经安装四套 UI 工作流：

1. `00_Qwen3.6_双语H3提示词导演`：中文构思和参考图生成中英文 H3 提示词。
2. `01_H3_HMNSFW_文生图抽卡`：生成 5 帧预览并选择一张 PNG。
3. `02_H3_HMNSFW_图生视频抽卡`：固定选中的图片，反复更换 video seed。
4. `03_已选视频超分4K`：RealESRGAN 分批超分并输出 3840×2160 静音 MP4。

日常顺序：

1. 可选：在 `00` 中输入中文构思，模式选 T2I 或 I2V；先检查中文完善版，再把英文版复制到 `01` 或 `02`。
2. 在 `01` 只调整绿色区域：提示词、image seed、HMNSFW 强度和抽取帧序号。Queue 多次完成首图抽卡。
3. 在 `02` 刷新 Output 图片列表并选择最终 PNG；固定图片后反复 Queue 筛 video seed。
4. 需要 AI 4K 时，把选中的 MP4 交给 `03`。若更看重时序稳定性，改用后文的外部 `temporal_safe` 路线。
5. 每次只运行一个阶段。确认 Qwen 状态显示 `Qwen已卸载` 后再启动 H3。

UI 固定参数：

| 阶段 | 默认规格 | 建议调整 | 不建议调整 |
|---|---|---|---|
| 01 文生图 | 1024×576、5 帧、20 步 | 提示词、seed、HMNSFW `0.20–0.50`、frame `0–4` | 模型、VAE、采样器、短包长度 |
| 02 图生视频 | 1024×576、73 帧、24fps、20 步 | 输入图、动作提示、seed、HMNSFW `0.40–0.70` | 分辨率、帧数、模型链 |
| 03 AI 4K | RealESRGAN x4plus、`per_batch=1`、3840×2160 | 输入和输出名 | 增大 batch、裁剪、并发 |

## 命令行工作流

以下命令均在项目根目录运行。

### 1. 外部图片生成微动画

先用 Turbo 4 步筛 5–8 个 seed：

```powershell
.\scripts\run_h3_turbo_preview.ps1 -Steps 4 -Seed 2026082904 -InputImage 'D:\pics\character.png'
```

排名靠前的 seed 用标准 20 步复核，再检查长时行为：

```powershell
.\scripts\run_h3_live2d_profile.ps1 -Profile draft -Seed 2026082904 -InputImage 'D:\pics\character.png' -LoopLock -Silent
.\scripts\run_h3_live2d_profile.ps1 -Profile long_draft -Seed 2026082904 -InputImage 'D:\pics\character.png' -LoopLock -Silent
```

只有在眨眼、姿态和末帧状态都通过后才跑昂贵母版：

```powershell
.\scripts\run_h3_live2d_profile.ps1 -Profile final -Seed 2026082904 -InputImage 'D:\pics\character.png' -LoopLock -Silent
```

常用参数：

- `-LoraStrength 0.5`：运动 LoRA；传 `0` 完全关闭。
- `-PromptFile .\prompts\my_motion.txt`：从 UTF-8 文本读取动作提示词。
- `-LoopLock`：同一张图直接锚定首尾；动态壁纸从标准 draft 到 final 都保持开启。
- `-Silent`：不加载音频链，动态壁纸和高分辨率任务建议开启。
- `-AbortRamGiB 31.0`：达到阈值时请求中断。
- `-Api http://127.0.0.1:8189`：显式切换到 0.34 测试实例。

输入图既可传 ComfyUI input 内的相对文件名，也可传任意绝对路径。外部文件会安全发布到 input 目录：同名同哈希复用，同名不同哈希拒绝覆盖。支持 `.png`、`.jpg`、`.jpeg`、`.webp`、`.bmp`。尽量提供接近 16:9 的图片；竖图居中裁切会损失大量构图。

### 2. H3 文生首图

MiniMax H3 的“文生图”不是原生单图扩散，而是生成最短 5 帧包再抽帧：

```powershell
.\scripts\run_h3_pseudo_t2i.ps1
.\scripts\run_h3_pseudo_t2i.ps1 -Seed 2026083010 -FrameIndex 0
.\scripts\run_h3_pseudo_t2i.ps1 -Seed 2026083013 -ImageLoraStrength 0.3 -OutputTag lora030
```

`FrameIndex` 只能是 `0–4`。宽高必须是 32 的倍数。图像 HMNSFW 默认是 `0`，强度为 0 时真正绕过 LoRA。

### 3. 文本直接生成 Live2D 视频

```powershell
.\scripts\run_h3_text_to_live2d.ps1
.\scripts\run_h3_text_to_live2d.ps1 -ImageSeed 2026083003 -VideoSeed 2026082904 -FrameIndex 0
```

可用 `-ImagePrompt` 和 `-MotionPrompt` 分开控制首图与动作，用 `-ImageLoraStrength` 和 `-MotionLoraStrength` 分开控制两阶段 LoRA。默认图像 LoRA 为 0、运动 LoRA 为 0.5。

### 4. 制作静音首尾循环

动态壁纸不再通过后期反向片段或交叉融合闭环。标准 `draft`、`long_draft` 和 `final` 直接传 `-LoopLock`，同一输入图同时锚定首帧和末帧；runner 输出本身就是循环候选。

提示词必须让呼吸、发丝、布料和光效在片内完成完整周期。最后 15% 回到源姿态附近，但保持与片头同量级的余速穿过边界，不要在末段停死。落花、烟雾和飞行粒子应冻结、原位变化或沿小范围闭合轨迹运动，避免在播放边界突然跳回起点。

首尾画面相似不代表速度连续。完成生成后仍需在播放器重复模式下正常速度观看边界；用户要求技术验证时再运行：

```powershell
$comfyPython = 'D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe'
& $comfyPython .\scripts\validate_wallpaper_loop.py '<looplock-output.mp4>' --minutes 1
```

### 5. 4K 输出

默认时序安全路线：

```powershell
.\scripts\run_4k_upscale.ps1 -Profile temporal_safe -InputVideo '<循环输出.mp4>'
```

可选 AI 细节路线：

```powershell
.\scripts\run_4k_upscale.ps1 -Profile ai_detail_default -InputVideo '<循环输出.mp4>'
```

若输入文件名不符合 `{identity}_{width}x{height}_{fps}fps_LOOP_SILENT.mp4`，必须同时传 `-OutputVideo`。验收：

```powershell
$comfyPython = 'D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe'
& $comfyPython .\scripts\validate_wallpaper_4k.py '<4K.mp4>' --audit-only --stdout-only
```

`temporal_safe` 是保守默认。RealESRGAN 路线实测仅增加约 8.3% 结构锐度，却带来约 1.35 倍静态纹理爬行和 1.51 倍时序残差。

### 6. 原生短片 1080p

只在 0.34 测试实例上运行，关闭音频并保留内存熔断：

```powershell
.\scripts\run_h3_live2d_profile.ps1 -Profile 1080_smoke -Seed 2026083022 -InputImage 'D:\pics\character.png' -Silent -Api 'http://127.0.0.1:8189'
.\scripts\run_h3_live2d_profile.ps1 -Profile 1080_short -Seed 2026083022 -InputImage 'D:\pics\character.png' -Silent -Api 'http://127.0.0.1:8189'
.\scripts\run_h3_live2d_profile.ps1 -Profile 1080_probe_39 -Seed 2026083022 -InputImage 'D:\pics\character.png' -Silent -Api 'http://127.0.0.1:8189'
.\scripts\run_h3_live2d_profile.ps1 -Profile 1080_probe_56 -Seed 2026083022 -InputImage 'D:\pics\character.png' -Silent -Api 'http://127.0.0.1:8189'
```

脚本内部生成 1920×1088，再缩放为 1920×1080。实测档位：

| 档位 | 时长 | 结果 | 峰值 RAM | 用途 |
|---|---:|---|---:|---|
| 22 帧 | 0.92 秒 | 通过 | 29.69GiB（旧监控） | 快速短片 |
| 39 帧 | 1.63 秒 | 通过 | 30.08GiB | 有后台程序时的保守档 |
| 56 帧 | 2.33 秒 | 通过 | 30.43GiB | 当前日常推荐上限 |
| 73 帧 | 3.04 秒 | 通过 | 30.58GiB | 物理内存边界档；运行前释放缓存并关闭后台 |
| 90 帧 | 3.75 秒 | 中断 | 31.11GiB | `CreateVideo` 整批编码达到物理上限，不使用 |

39/56/73 帧均完整解码且黑帧为 0。73 帧测试使用 `-AbortRamGiB 31.0` 才完整结束，只剩约 0.53GiB 物理余量，不应作为无人值守默认。90 帧的扩散、VAE 解码和 1920×1080 缩放已经执行完，最终在 `CreateVideo` 整批编码时触发熔断；因此瓶颈是输出节点的批量帧缓冲，不是 H3 采样或显存。

需要复现实验时可加 `-RunReport .\artifacts\my_run.json` 保存结构化耗时和峰值。`1080_probe_90` 仅保留为负对照，不建议再次运行。

### 7. 原生 1080p 逐帧输出与流式编码

整批 `CreateVideo` 会在末端一次性持有全部帧。这条路线改成节点 20 `SaveImage` 按运行 ID 逐帧写 PNG，释放模型后再由外部编码器顺序读图：

```powershell
.\scripts\run_h3_1080_stream.ps1 -Profile 1080_stream_22 -Api 'http://127.0.0.1:8188'
.\scripts\run_h3_1080_stream.ps1 -Profile 1080_stream_73 -Api 'http://127.0.0.1:8188'
```

运行器会自己完成：`/free` 释放模型并记录空闲基线 → 提交 → 拉起独立熔断守护 → 分阶段采样内存 → 校验帧序列 → 再次 `/free` → 流式编码 → 按余量分级 → 写统一运行报告。`-Api` 需指向 0.34 实例；脚本校验 `comfyui_version` 而不是端口，端口对不上会直接拒绝而不是跑错实例。

| 档位 | 帧 | 生成峰值 RAM | 编码峰值 | 余量 | 结果 |
|---|---:|---:|---:|---:|---|
| `1080_stream_5` | 5 | 29.06GiB | 9.26GiB | 2.05GiB | 通过 |
| `1080_stream_22` | 22 | 29.11GiB | 9.72GiB | 2.00GiB | 通过 |
| `1080_stream_73` | 73 | 30.18GiB | 6.94GiB | 0.93GiB | 通过，需看守 |
| `1080_stream_90` | 90 | 31.02GiB | — | 0.09GiB | 中断，无帧落盘 |

编码阶段峰值随机器基线波动而非随帧数上升（73 帧时进程 RSS 仅 0.48GiB，全程增长 0.231GiB）。帧目录默认保留在 ComfyUI 输出目录下的 `minimax_h3_1080_stream\<run-id>\`，人工验收成片后再删。

单独重跑校验或编码：

```powershell
$comfyPython = 'D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe'
& $comfyPython .\scripts\validate_h3_frame_sequence.py '<帧目录>' --expected-frames 73
& $comfyPython .\scripts\encode_h3_frame_sequence.py '<帧目录>' '<输出.mp4>' --expected-frames 73
```

两个脚本都拒绝覆盖已存在的目标；帧序列有缺号、乱序、尺寸错误或黑帧时编码不会启动。

## Qwen3.6 提示词导演

自定义节点位于 `comfyui_custom_nodes/ComfyUI-Qwen-H3-Bilingual`，复用 LM Studio 中已有的 Qwen3.6 GGUF，不复制主权重。执行流程会先释放 ComfyUI 缓存，按需加载 Qwen，生成严格的中文检查版和英文执行版，最后在 `finally` 中卸载模型。

最多可选四张参考图。每张图只有在“真实图片 + 非空说明”同时满足时才送入模型；清空说明即可禁用该图。推荐把说明限定为某一类属性，例如：

- `只参考背景布局、暖色光源和景深，不参考人物。`
- `只参考服装材质和黑金配色，不参考姿势和身份。`
- `只参考16:9构图和留白，不参考主体。`

当前稳定默认是 `gpu_offload=0.20`、`vision_gpu_offload_cap=0.20`、最长边 1024、单并发。不要在 32GB 机器上盲目传入四张 2048px 图片。状态框必须显示实际参考图数量、GPU 卸载比例和 `Qwen已卸载`。

## 提示词经验

I2V 的角色外观、服装和初始姿态来自输入图；动作提示词负责“怎么动”和“什么不能变”。有效结构是：

1. 使用 HMNSFW 时以 `hmmotion` 开头。
2. 明确成年人、主体材质、场景和初始状态。
3. 锁定连续镜头、构图、焦距与背景。
4. 逐项锚定头、躯干、肩、髋、手臂、腿和脚。
5. 只允许 2–3 个低幅动作，例如一次快速眨眼、轻呼吸、发梢轻摆。
6. 明确保留脸、瞳色、发型、服装、比例、材质、轮廓和配件。
7. 排除嘴部、手部、肢体、姿态和镜头的大幅变化，以及 morphing、额外手指和文字。

不要使用 `dynamic motion`、`cinematic camera`、`dramatic movement` 等泛化动词。动作项越多，H3 越容易重构主体。换人物后应优先重新筛 seed，而不是持续堆叠提示词或提高 LoRA 强度。

可复用模板位于 `prompts/MINIMAX_H3_LIVE2D_FIGURINE_PROMPT.md`；1080p 验证提示位于 `prompts/MINIMAX_H3_1080P_FEASIBILITY_PROMPT.md`。

## 常见故障

| 现象 | 原因与处理 |
|---|---|
| 直接设置 1920×1080 时形状错误 | H3 空间 patch 要求宽高按 32 对齐；用 1920×1088 生成后缩放，不是 OOM。 |
| RAM 接近 31GB | 立即停止并串行重跑；关闭音频、Qwen 和其他模型，保留 31.0GiB 熔断。 |
| 强度 0 仍经过 LoRA 后读取失败 | 0 强度必须真正绕过 loader；当前两个 T2I 运行器已修复。 |
| Turbo 很快但末帧漂移较高 | Turbo 只用来排序 seed；标准 20 步复核后再决定母版。 |
| 闭眼持续到结尾 | 换 video seed，并写 `one quick blink lasting only a few frames`；先过 `long_draft` 再跑 final。 |
| 手工关键帧看起来像图层平移 | 不要靠 RIFE 修复错误关键帧；改用 0.34 原生 `MiniMaxH3AddGuide` 或重新生成关键帧。 |
| 复制工作流后同 seed 换了结果 | 检查 `ImageScale` 节点 17 的 `crop`：1080p 档位必须是 `disabled`，基础工作流默认是 `center`。首帧不同会让同一 seed 走出不同轨迹。旧成片内嵌 workflow 元数据可用来逐节点 diff。 |
| 同 seed 跨会话结果不一致 | 预期行为。同会话重跑是 bit 级一致的，跨会话会因内存压力驱动的权重卸载差异分叉；母版需重新人工复核，不要假定与旧样片相同。 |
| RealESRGAN 出现纹理爬行/轮廓呼吸 | 切回 `temporal_safe`；AI 档只在人工动态观看确认后使用。 |
| Qwen 加载失败或占满内存 | 保持 20% GPU 卸载，确认其他 LM Studio 模型已卸载，完成后检查 `lms ps --json` 为 `[]`。 |
| UI 报 missing node | 确认主实例、自定义节点安装路径和 UI JSON 同步；0.34 测试实例未整批迁移旧插件。 |

## 项目结构

```text
README.md                         日常使用、默认参数与故障处理
VALIDATION_HISTORY.md             调研、阶段验证、失败路线与证据索引
plans/                            尚未完成或刚执行完的改造计划与结果
workflows/                        API 工作流
workflows/ui/                     ComfyUI 0.4 图形工作流源文件
presets/                          Live2D、T2I、性能、4K 与 1080p 流式档位
scripts/                          下载、运行、循环、超分和验收工具
tests/                            Qwen 节点与参考图过滤测试
prompts/                          可复用提示词
comfyui_custom_nodes/             Qwen3.6 双语导演自定义节点
outputs/、artifacts/              项目内归档样片、抽帧与指标
backups/                          历史冻结点，仅供回溯
vendor_audit/                     第三方 Turbo 节点审计副本
```

## 尚未完成

- 4K 默认样片仍需要用户进行一次正常速度、连续循环的人工动态观看。
- 1080p 逐帧流式的 5/22/73 帧成片同样需要一次人工动态观看确认。
- 每张新输入图都需要按 Turbo → draft → long_draft → final 的顺序重新筛 seed。
- 成人内容链路已验证，但现有测试 video seed 的主体前移较明显，不能直接作为循环壁纸母版。
- 原生闭环测试的身份和瞳色稳定，但闭眼阶段偏长，需要换 seed 或收紧眨眼提示。
- 原生 1080p 已确认到 73 帧，两条输出路线都在 90 帧中断。要突破必须处理解码+缩放阶段的双批次驻留：时间维分块解码、把 `1088→1080` 缩放移出 ComfyUI，或降低内部生成分辨率。取舍见 [H3 1080p 流式输出实施计划](plans/H3_1080_STREAMING_OUTPUT_PLAN.md) 第 10.11 节。
- 1080p 循环壁纸已改为原生首尾锚定。批量 profile 可用 `-LoopLock` 做短档验证；当前逐帧 runner 尚未暴露 `last_frame`，在扩展并重新验证前不能作为直接循环交付入口。
- 项目所有外部编码脚本都不写色彩标签，而 ComfyUI `SaveVideo` 会写 BT.709 limited-range。要统一需同时改 4K 两条与 1080p 流式一条。
