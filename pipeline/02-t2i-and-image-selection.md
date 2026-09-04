# 02 文生图与人工选图

本阶段把 Director Brief 转成可执行 T2I prompt，生成静态候选，并在用户选定后锁定后续 I2V 输入图。

## 目标

不是单纯生成一张漂亮图，而是生成 **漂亮且适合作为 H3 I2V 首帧** 的静态图。

## Agent 动作

1. 根据 `01` 的 Director Brief 写 T2I prompt。
2. prompt 必须明确：主体、姿势、构图、镜头、光线、场景、材质和禁止变化。
3. 优先保证：
   - 脸、手、肢体和道具结构清晰；
   - 16:9 构图稳定；
   - 软质可动区域轮廓清楚；
   - 硬质区域不易被后续视频重构；
   - 后续动作有足够空间。
4. 执行 T2I 抽卡并保存候选。
5. Agent 可以先淘汰明显结构错误候选，但不能替用户完成最终审美选择。

## Gate A：人工选图

状态必须进入：

```text
WAITING_FOR_USER_SELECTION
```

向用户展示/提供候选后，由用户明确指定进入 I2V 的静态图。

用户选定后记录：

```text
selected_image:
selected_image_sha256:
selection_notes:
status: SELECTED
```

## 不自动晋级的原因

静态图是后续全部 video seed 的共同起点。Agent 可以判断技术问题，但角色审美、姿势和画面偏好属于用户最终决定。

## 晋级

用户完成 Gate A 后进入 `03-motion-and-seed-screen.md`。