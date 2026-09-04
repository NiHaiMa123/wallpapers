# workflows/experimental — NON-PRODUCTION

> [!WARNING]
> 本目录中的 ComfyUI workflow JSON **不是当前生产路线**。它们是历史实验时代的 API 工作流，保留作为可考证据与重建素材。

当前生产 workflow 在 `../`（workflows 根目录），其语义由 `contracts/` 约束。

## 文件清单

| Workflow | 历史用途 |
|---|---|
| `minimax_h3_i2v_baseline_api.json` | 最早的无 LoRA I2V 基线 |
| `minimax_h3_i2v_hmnsfw_v25_api.json` | HMNSFW V2.5 图像/运动双分支时代的 I2V |
| `minimax_h3_i2v_native_looplock_api.json` | LoopLock 首尾锚定的早期独立工作流（后被 profile runner 内联） |
| `keqing_keyframe_rife_1080p_api.json` | keqing 关键帧 + RIFE 镜像路线（已废弃） |
| `keqing_krea2_motion_keyframe_a_api.json` | keqing Krea2 身份编辑关键帧路线（已废弃：重画人物） |

## 与 history/ 的对应

- 镜像路线证据：`history/H3_1080_LOOP_STRATEGY_NOTES.md`、`history/图生视频_Gemini执行手册.md`
- Krea2 失败结论：`history/VALIDATION_HISTORY.md` 第 10.2 节
