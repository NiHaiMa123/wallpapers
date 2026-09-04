# 07 最终 QC 与交付

本阶段只验收已经完成“人工留帧 -> 插帧 -> 超分”的最终候选。

## 正常速度观看

至少连续观看多个循环，重点检查：

- 身份、脸、眼睛、手、肢体；
- 武器、饰品、水晶、建筑等硬质结构；
- 镜头是否漂移；
- 尾段是否仍有明显刹停；
- 接缝是否有抽动、速度突变或假溶解；
- RIFE 是否产生鬼影；
- 超分是否产生纹理爬行、halo、轮廓呼吸、边缘闪烁；
- 色彩和亮度是否在边界跳变。

## 技术 QC

根据当前输出规格运行对应 validator / ffprobe 检查：

- 文件可稳定解码；
- 预期尺寸、fps、帧数和时长；
- H.264 / 目标 codec 与 pixel format；
- 静音任务只有 video stream；
- 无黑帧；
- 无明显 PTS 错误；
- faststart / checksum 等仓库 validator 要求通过。

技术 validator 不能替代正常速度观看。

## 判定

- `PASS`：可直接交付。
- `PASS_WITH_WARNINGS`：用户目标已满足，但存在已知小缺陷，必须在报告中写明。
- `REJECT`：存在明显生成/插帧/超分/循环问题，回到最近能改变问题的阶段。
- `BLOCKED`：无法解码、缺工具、资源或环境阻碍判断。

## 交付记录

最终报告至少包含：

```text
final_output:
resolution:
fps:
frame_count:
duration:
codec:
pixel_format:
source_image:
selected_seed:
selected_1080p_take:
keep_frames:
interpolation_method:
upscale_profile:
visual_qc:
technical_qc:
known_defects:
sha256:
```

必须区分：

- Agent 推荐与用户实际选择；
- 原始 1080p take 与最终后处理成片；
- 技术通过与视觉通过；
- 自动分析建议的删帧区间与用户最终 keep list。

## 完成标准

用户可以直接找到最终文件，并能从记录追溯：导演方案 -> 静态图 -> seed -> 1080p take -> keep list -> 插帧 -> 超分 -> 最终 QC。