# 05 全帧导出与人工留帧

本阶段解决 MiniMax H3 首尾循环常见的末尾降速/冻结问题。原则是：**完整导出证据，自动分析辅助，用户决定最终保留帧。**

## 输入

- Gate C 选定的 `1920×1080 / 73f` take。

## 全帧导出

1. 将视频完整导出为连续编号图片。
2. 不跳帧、不重排、不覆盖旧目录。
3. 建议统一目录：

```text
outputs/images/<take-id>/keep_001.png
...
outputs/images/<take-id>/keep_073.png
```

4. 保留原始视频和完整 73 帧目录作为证据。

## 自动分析仅作辅助

Agent 可以运行 MAD、光流、motion uniformity 等工具，标出：

- 尾部连续低运动区；
- 明显速度尖峰；
- 末帧到首帧变化；
- 可能值得加速/删除的区间。

但分析结果只用于说明，不直接产生最终 keep list。

## Gate D：人工决定保留帧

向用户提供完整帧列，并在有帮助时同时提供速度分析结果。

状态进入：

```text
WAITING_FOR_USER_SELECTION
```

用户可以用以下任一方式指定：

```text
保留 1-63,73
删除 64-72
保留 1,3,5,...
按明确帧号列表保留
```

Agent 必须逐字落实用户的留删决定，不因为自动指标“看起来更合理”而自行增加或删除帧。

记录：

```text
source_take:
all_frames_dir:
keep_frames:
drop_frames:
analysis_reference:
user_selection_notes:
status: SELECTED
```

## 重建前检查

- keep list 不得越界；
- 不改变保留帧原始顺序；
- 默认保留 LoopLock 锚定末帧，除非用户明确要求其他方案；
- 发现保留结果会造成明显人物/道具位置跳跃时要警告用户，但不要擅自改变选择。

## 晋级

Gate D 完成后，将 keep list 交给 `06-interpolation-and-upscale.md`。