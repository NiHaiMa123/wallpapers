# 06 重建、插帧与超分

本阶段只处理 Gate D 已确认的最终帧序列。顺序固定为：

```text
人工 keep list
  -> 重建选定帧序列
  -> 插帧
  -> 超分
  -> 编码候选
```

## 1. 重建选定序列

- 只使用用户确认保留的帧；
- 保持原始时间顺序；
- 不覆盖原片、全帧目录或旧候选；
- 输出唯一命名文件和结构化报告；
- 记录有效帧数、目标 fps、时长和等效变速比。

如果用户通过删帧主动加快尾段，必须如实记录，不把它描述为“原始 H3 运动已均匀”。

## 2. 插帧

优先使用仓库当前已验证的 RIFE / FrameInterpolate 路线。

循环视频插帧必须考虑末帧到首帧的边界，不只处理片内相邻帧。

插帧候选必须检查：

- 脸、眼睛、手、发丝是否鬼影；
- 武器、电弧、细线结构是否分叉；
- 接缝是否变成溶解而非真实运动；
- 是否重新放大尾部降速或边界脉冲。

RIFE 失败时回退到未插帧版本，不因为 FPS 更高强行晋级。

## 3. 超分

只对已经通过插帧观看的候选做超分。

默认优先时序安全路线；AI detail 路线只有在动态观看确认没有以下问题时才保留：

- 纹理爬行；
- halo；
- 轮廓呼吸；
- 边缘闪烁；
- 色偏或亮度跳变。

如果 AI 超分新增时序问题，回退到 `temporal_safe`。

## 4. 产物记录

至少记录：

```text
source_take:
keep_frames:
rebuilt_sequence:
rebuilt_frame_count:
interpolation_method:
interpolated_fps:
interpolated_output:
upscale_profile:
upscaled_resolution:
final_candidate:
known_artifacts:
```

## 不允许的修复

- 不用插帧修复脸崩、肢体错误、武器弯曲或背景重构；
- 不用超分掩盖错误生成；
- 不把未经用户确认的自动删帧重新偷偷加入主流程。

## 晋级

完成候选后进入 `07-final-qc-and-delivery.md`。