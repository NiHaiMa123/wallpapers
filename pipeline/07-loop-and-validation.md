# 07 原生首尾循环与验证

本流程不再把普通母版做后期反向拼接。循环由标准 H3 runner 在生成阶段通过 `-LoopLock` 直接完成，同一输入图同时锚定首帧和末帧。

## 输入资格

进入本阶段的候选必须来自：

```text
run_h3_live2d_profile.ps1 -Profile <profile> -LoopLock
```

如果已有视频生成时没有使用 `-LoopLock`，不要把它后期改造成当前 pipeline 的循环成片；返回 `05-standard-render.md`，用相同输入、prompt 和候选 seed 重新运行。

## 直接循环要求

- 首帧和末帧由同一输入图锚定；
- 人物姿态、视线、手、道具、发丝附着点、服装、背景和光照回到起点；
- 动作在一个片段内完成完整周期；
- 最后 15% 回到源姿态附近，但保持与片头同量级的余速穿过边界，禁止末段停死；
- 花瓣、烟雾和粒子不得单向离开后在边界瞬移回起点；
- 不添加后期反向段，不通过重复端点延长时长。

## 正常速度边界观看

在播放器中开启重复播放，连续观看多个完整循环，重点看：

- 末帧接回首帧是否有停顿、抽动或速度突变；
- 呼吸、头发、布料和光效是否完成完整周期；
- 落花、烟雾、粒子和反射是否在边界突然重置；
- 首尾附近是否出现闭眼、表情改变、亮度跳变或背景重构；
- 硬质道具和身体姿态是否为了收敛而扭曲。

片内速度是否均匀，用 `scripts/analyze_motion_uniformity.py` 锁定发丝/水晶区域，看光流幅度和颜色偏移的时间曲线。变异系数高、尾段/中段比明显偏离 1、末步过低或接缝 MAD 远高于中位速度，都表示节奏不匀。flags 阈值可用 `--flag-cv/--flag-tail-fast/--flag-tail-slow/--flag-last-ratio/--flag-spike/--flag-wrap` 覆盖，默认值按壁纸 idle 标定；实际使用的阈值会记入报告 `flag_thresholds`，判读结论必须以报告为准。

要把原片调成接近匀速且 FPS 不变：先对源片做环形 RIFE 得到密采样，再用 `scripts/equalize_motion_speed.py` 按锁定区域的累计光流等弧长重采样。`--region` 必填，必须框住本片的主体运动区；变化小的区间会被删帧（加快），变化大的区间会吃到插帧（放慢）。接缝视为「末帧→首帧」这一段大变化：`--loop --wrap-rife-video` 对 last+first 做单独 RIFE，再按接缝路径运动量分配过渡帧（默认 `--wrap-budget-mode path`；`--keep-duration` 下按比例分配，保证接缝与片内同尺度）。报告中的 `wrap_micro_sum`、`wrap_final_hop`、`wrap_coarse_last_to_first` 用于核对接缝预算是否合理。RIFE 产物路径以 run 报告 `output.images[0]` 的 filename+subfolder 为准，不要硬编码 `postprocess/`（不同版本落点不同）。若 RIFE 在接缝上只做出溶解/鬼影而不是真实位移，接缝 MAD 不会下降，应回退到无接缝插值的匀速版。没有外部 RIFE 可用时，可用 `scripts/equalize_loop_per_frame.py`（自带光流内插、三遍流式、dense 落盘，默认 `--min-wrap 0`；运动代理是全局 MAD，仅适用于短循环）。程序只保证速度均匀，画面语义（脸/手/表情/背景）由用户审核。

判断顿感时不要先怪播放器。先看末段相邻帧变化：

- 末段连续接近静止、接回首帧后又跳回平均运动，是片子停死，不是播放器。
- 片头前几步和片尾后几步的运动量级应接近。
- 本机 H.264 往往只有开头一个 I 帧，Windows 自带播放器循环时可能再顿一下；用 mpv 或 VLC 对照，但不能用播放器差异否定片子里的刹停。

首尾静态帧相似只能证明位置接近，不能证明运动连续。边界观看不通过时，返回提示词或 seed 阶段重做，不能靠后期复制帧隐藏。

## 用户授权的尾段裁帧（人选帧定剪，2026-09-04 起执行）

默认仍应回到提示词或 seed 阶段解决末段停死。只有用户明确要求保留现有生成结果并删除静止尾帧时，才允许做一次可追溯的尾段裁帧。留删决定流程：

- Agent 先导出全帧数图片列（`outputs/images/keep_001.png` 起，见 `06-visual-review.md` 人选帧门）；
- 用户看图列给出保留范围/帧号（做什么版本、删哪些帧），Agent 照做，不自行增删；
- 速度测量数据（逐帧 MAD、uniformity flags/CSV）只做参考，不替代用户决定；

执行裁剪时遵守以下技术规则：

- 先逐帧测量相邻帧 MAD。末段连续低于片内均值约 40% 的步骤视为冻结区；
- 未插帧的 H3 源片：整段删除冻结区，只保留最后一帧 LoopLock 锚定帧。不要在冻结区里稀疏留中间帧——`draw02` v3 留了 63 和 68，末步 MAD 仍只有均值的 16%，循环仍像刹停；
- 已经 RIFE 插帧的片子：冻结/回位区不要整段挖掉。插帧已经把两帧之间的动作补连续了，应隔帧删除（留 1,3,5,7，删 2,4,6），让回位沿原轨迹加快，而不是从中段跳到末帧。用 `--drop-stride 2 --drop-range <start>-<end>`，末帧始终保留（脚本默认拦截删末帧，需 `--allow-drop-last` 才放行）；
- 选择删除范围时，让「保留的最后运动帧 → 锚定末帧」的 MAD 接近片头第一步或片内均值，而不是接近 0；
- 不能复制帧、倒放、交叉融合或用插帧掩盖停死；
- 用 `scripts/retime_video_no_interpolation.py --drop-frames <索引或范围>` 生成唯一命名的新文件和 JSON 报告，不覆盖源片；越界索引会被过滤并记入 `ignored_out_of_range`，真实变速比看 `effective_speed_ratio`（`speed_ratio` 只计 fps 比）；
- 若整体仍采用 0.8 倍速，24fps 源片输出为 `19.2fps`。未删掉的冻结帧在 19.2fps 下会显得更长，所以 0.8 倍速不能代替删冻结区；
- 裁帧前后都记录帧数、时长、末步 MAD、末 5 步平均 MAD、末帧接首帧 MAD，并重新做正常速度边界观看和技术验证；
- 若人物或道具出现位置跳跃，或剩余尾段仍明显停死，裁帧候选按 `REJECT` 处理并回到生成阶段。

示例（按实测冻结区整段删除，而不是稀疏留帧）：

```powershell
$comfyPython = 'D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe'
& $comfyPython .\scripts\retime_video_no_interpolation.py '<24fps-source.mp4>' '<19.2fps-tailtrim.mp4>' --fps 19.2 --drop-frames '63-71' --report '<tailtrim-run.json>'
```

## 技术验证

技术 validator 只确认文件能稳定解码、静音、无黑帧、循环校验和一致。它不判断动作是否顺，也不能替代正常速度边界观看。长时间反复解码同一段短片几乎不会多发现画面问题，因此只跑 1 分钟等效循环：

```powershell
$comfyPython = 'D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\.venv\Scripts\python.exe'
& $comfyPython .\scripts\validate_wallpaper_loop.py '<looplock-output.mp4>' --minutes 1
```

要求：

- H.264、`yuv420p`；
- 只有一个 `video` 流，确认静音；
- 预期尺寸、fps、帧数和时长；
- `pts_errors=0`；
- `black_frames=0`；
- `checksum_mismatch_cycles=0`；
- `faststart=true`；
- `passed=true`。

`loop_boundary_mad` 只用于记录首尾画面差异，不衡量速度连续性，不能取代正常速度边界观看。

## 本次任务约束

如果用户明确说“先不用跑验证”，只完成流程或文档修改，不执行上述 validator，不把验证状态写成通过。

## 产物

- LoopLock 原始输出或其不改帧内容的项目归档副本；
- 通过后复制到 `outputs/masters/` 和 `outputs/wallpapers/`，不要重新编码；
- profile、seed、prompt、LoRA、静音和运行报告；
- 正常速度边界观看结论；
- 用户授权后才产生的 validator 结果和 SHA-256。

## 晋级条件

正常速度边界观看通过；若当前任务包含技术验证，还必须同时满足 validator 门槛。
