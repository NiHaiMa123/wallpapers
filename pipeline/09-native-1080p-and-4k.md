# 09 原生 1080p 与 4K

这些是母版或循环已经通过后的可选升级，不是默认首轮路线。

## 原生 1080p

H3 内部使用 `1920×1088`，再无裁切缩放为 `1920×1080`。不要直接把内部尺寸设为 1920×1080。

批量 `run_h3_live2d_profile.ps1` 支持 `-LoopLock`。先从短档验证原生首尾锚定：

```powershell
.\scripts\run_h3_live2d_profile.ps1 -Profile 1080_smoke -LoopLock -Silent -Api 'http://127.0.0.1:8188'
.\scripts\run_h3_live2d_profile.ps1 -Profile 1080_short -LoopLock -Silent -Api 'http://127.0.0.1:8188'
```

服务实例以实际在 `8188` 上应答的为准（当前为 `ComfyUI H3 0.34 Test`），不要只凭端口或安装目录猜。staging 输入必须进该实例的输入目录（当前 `D:\Comfy-Desktop\ComfyUI-Shared\input`，不是各安装目录下的 `input`）；提交报 400/`Invalid video file` 时，先读该实例 `logs/comfyui.log` 的服务端确切原因，再动输入。

现有逐帧 runner 尚未暴露 `-LoopLock` 或 `last_frame` 参数，不能作为本 pipeline 的直接循环交付入口。以下命令只保留给非循环 1080p 帧序列或未来扩展测试：

```powershell
.\scripts\run_h3_1080_stream.ps1 -Profile 1080_stream_5 -Api 'http://127.0.0.1:8188'
.\scripts\run_h3_1080_stream.ps1 -Profile 1080_stream_22 -Api 'http://127.0.0.1:8188'
```

runner 检查 ComfyUI 版本而不是相信端口。只有在 runner 和 workflow 明确增加同图末帧锚定、并重新完成短档验证后，逐帧路线才能晋级为直接循环路线。

日常原则：

- 当前 runner 与 preset 的默认 RAM 熔断统一为 `31.0GiB`；
- 5/22 帧先验证接线；
- 73 帧属于需看守档，本机 LoopLock 实测峰值约 30.46GiB（0224）/ 30.43GiB（0227），仍低于 31.0GiB 熔断；
- 84 帧是历史用户授权探针：当时 LoopLock 采样约 29.8GiB，CreateVideo 冲到 31.01GiB，被当时的 `AbortRamGiB=30.5` 打断且无成片；此处只保留历史事实，不是当前默认值，也不得以此为由抬高当前 31.0GiB 熔断重跑；
- 90 帧及以上是负对照/升级探针，不是默认菜单；
- 帧目录默认保留，验收前不删除；
- 缺帧、乱序、尺寸错误或黑帧时禁止编码。
- 不使用 `--loop-mode` 后期扩展来代替原生首尾锚定。

以 `presets/minimax_h3_1080_stream_profiles.json` 为准。

## 4K

只对已经通过循环验收的成片升级。

默认时序安全路线：

```powershell
.\scripts\run_4k_upscale.ps1 -Profile temporal_safe -InputVideo '<loop.mp4>'
```

AI 细节路线必须由用户接受纹理爬行风险：

```powershell
.\scripts\run_4k_upscale.ps1 -Profile ai_detail_default -InputVideo '<loop.mp4>'
```

验收：

```powershell
$comfyPython = 'D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe'
& $comfyPython .\scripts\validate_wallpaper_4k.py '<4k.mp4>' --audit-only --stdout-only
```

## 视觉门槛

4K 不能新增：静态纹理爬行、轮廓呼吸、halo、边缘闪烁、黑帧、色偏、亮度跳变或接缝恶化。

## 回退

- 原生 1080p 余量不足：保留最后通过的 profile，不提高熔断。
- AI 4K 出现时序问题：回到 `temporal_safe`。
- 高分辨率只增加耗时而没有明显观感收益：交付已经通过的原始循环。

## 2K 与智能插帧

本仓库中的 2K 指 `2560×1440`。已通过的 24fps 视频使用 `ai_detail_2k` 做逐帧 RealESRGAN 流式超分；已经是 60fps 的输入使用 `ai_detail_2k_60`，不要在超分脚本里同时插帧。

智能插帧使用 ComfyUI 0.34 原生 `FrameInterpolate` 与 `rife_v4.26.safetensors`，必须作为 H3 卸载后的独立任务运行。先用 5 帧冒烟验证，再处理全片。RIFE 产物路径以 run 报告 `output.images[0]` 的 filename+subfolder 为准，不要硬编码 `postprocess/`（不同版本落点不同：根目录与子目录都出现过）。送插帧的输入片不要过短：2 帧输入片曾被服务端 loader mishandle（端点对不上），用 ≥8 帧填充或直接送长片。循环视频不能只插片内相邻帧：需要把首帧临时追加到输入末端，对末帧到首帧也执行插值，输出时再去掉重复首帧。

RIFE 不能自动保证循环更顺。插帧候选必须与源片比较：

- 片尾连续帧运动量与片头运动量；
- 末帧接首帧的 MAD 相对片内平均帧间 MAD；
- 眨眼、细发、剑刃、电弧和小粒子是否出现鬼影；
- RIFE 是否真的为末帧到首帧生成有效过渡。

若 60fps 候选放大边界脉冲、末端停死或产生鬼影，按 `REJECT` 处理，不把“帧数更多”当成交付理由。回退到不插帧版本。24fps 源片若需要整体 0.8 倍速，可保持原有 73 帧不变并改为 `19.2fps`；不得通过重复帧伪造 24fps 慢放。

以下为 draw02-0211 世代的历史结论（2026-09-02），只保留为证据，不作为当前路线：本次刻晴 draw 02 的 RIFE 4.26 候选即使采用环形输入，末帧到首帧也几乎没有有效光流过渡；60fps 候选的边界变化相对片内平均由源片的约 `1.35×` 放大到约 `4.60×`，因此淘汰。当时交付路线为 RealESRGAN 2K、无插帧的 19.2fps / 0.8 倍速版本。73 帧源片从第 63 步起相邻 MAD 掉到均值的 10–20%，循环时先刹住再接回首帧。v3 只删 `64-67,69-71` 并留下冻结帧 63 和 68，末步 MAD 仍约 `0.23`（均值的 16%），观感仍像卡顿。v4 改为整段删除 `63-71`、保留 `0-62` 和末帧 `72`，让最后一步跳到锚定帧的 MAD 约 `1.59`，接近片头 `1.18` 和均值 `1.34`。原 73 帧和 v3 继续保留为证据。当前 draw02_v3 世代路线见 plan2 实战记录（65f LoopLock 直剪 → 60fps → 4K）。
