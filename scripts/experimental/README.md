# scripts/experimental — NON-PRODUCTION

> [!WARNING]
> 本目录中的脚本 **不是当前生产入口**。它们是历史实验、诊断工具和特定任务的一次性实现，保留作为 NON-NORMATIVE 证据和复用素材。

当前生产入口在 `../`（scripts 根目录）的 runner 中，由 `pipeline/` 与 `contracts/` 定义。任何 Agent 不得把本目录脚本当作生产路线执行；引用其中工具属于实验/诊断行为，须遵守根 `AGENTS.md` 的授权边界。

## 文件清单

| 脚本 | 历史用途 |
|---|---|
| `add_elegant_sword_filaments.py` | 在固定剑刃旁合成受控行进闪电（keqing 雷电特效实验） |
| `analyze_4k_upscale.py` | 测量 4K 候选的保真度、锐度、时序残差与循环边界 |
| `analyze_h3_motion_aesthetics.py` | 测量固定 keqing 片段的运动层级与剑雷节奏 |
| `analyze_h3_t2i_batch.py` | 测量 H3 伪 T2I 五帧包的一致性 |
| `analyze_text_to_live2d.py` | 验证 H3 伪 T2I 静帧直通 H3 Live2D 视频的链路 |
| `build_keqing_vfi_keyframes.py` | 为 RIFE 验证构建保守 1080p 循环关键帧（已废弃镜像路线） |
| `build_seamless_wallpaper.py` | 从短片构建静音 H.264 循环（镜像拼接时代产物；`loop_common.playback_indices` 的历史消费者） |
| `compare_h3_frames_to_video.py` | 证明只改输出阶段不改变渲染帧（逐帧落盘 vs CreateVideo 对照） |
| `compare_h3_performance.py` | 固定条件 H3 渲染对比 + 拼接 contact sheet |
| `diag_rife_pair.py` | 最小闭环 RIFE 成对诊断 |
| `make_video_comparison_sheet.py` | 每视频一行的 seed 对比 contact sheet |
| `make_video_crop_sheet.py` | 从等距帧生成放大裁切表 |
| `replace_last_with_first.py` | 复制首帧到末帧消除循环接缝外观跳变（已被 same-image anchor 取代） |
| `resample_video_to_fps.py` | 最近邻选帧重采样到目标 FPS |
| `run_h3_generate.py` | 通用 ComfyUI payload 提交器（已被 profile runner 取代） |
| `run_h3_window_probe.py` | 双窗口 MiniMax H3 续写探针（记忆/上下文实验） |
| `run_krea2_identity_edit.ps1` | Krea2 Identity Edit 脸部保真编辑（实验结论：重画人物，路线停止） |
| `screen_h3_loop_candidates.py` | 为无缝循环母版排序 H3 seed 候选 |

## 依赖说明

- `build_seamless_wallpaper.py` 自行把 `scripts/`（本目录上一级）加入 `sys.path` 后 import `scripts/loop_common.py`，任意工作目录下可直接运行；
- `run_h3_generate.py` 读取仓库根的 `workflows/minimax_h3_live2d_figurine_api.json` 与 `presets/minimax_h3_live2d_profiles.json`，默认 prompt 指向 `history/prompts/` 下的历史 V7 模板；
- `run_h3_window_probe.py` 把 artifacts 写到仓库根 `artifacts/loop_vfi_probe/`（其 `COMFY_OUTPUT` 常量仍是当时本机的 ComfyUI 输出目录，属于历史机器路径，换机需显式修改）；
- `run_krea2_identity_edit.ps1`、`build_keqing_vfi_keyframes.py` 内联构造 payload / 输入，不依赖仓库相对路径；
- 其余脚本无跨目录 import 或仓库相对路径，可独立运行。

## 为什么保留

这些脚本是 `history/` 中各实验记录的直接证据，其中多个（帧测量、contact sheet、对比工具）在后续诊断中可复用。删除它们会让历史文档引用的实现不可考。
