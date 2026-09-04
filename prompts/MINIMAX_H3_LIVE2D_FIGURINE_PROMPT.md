# MiniMax H3 精致手办 / Live2D 微动画提示模板

## 推荐主提示（英文）

```text
hmmotion. A premium collectible resin figurine depicting a clearly adult woman is displayed fully clothed in a warmly lit night garden. This is one continuous locked-off shot. The camera, framing, focal length, background, lantern and plants remain perfectly static. The figurine keeps exactly the same pose and silhouette as the first frame: the head, torso, shoulders, hips, hands, arms, legs and feet stay anchored with no repositioning. Only three barely perceptible motions occur: she slowly closes and opens her eyelids once, her upper torso shows extremely subtle natural breathing without changing posture, and only the very tips of a few loose hair strands and the red tassel make a tiny soft secondary movement. Preserve the exact adult face, eye shape, hairstyle, costume coverage, body proportions, painted details, glossy resin/PVC material, warm rim light, shadows, depth of field, composition and every accessory from the first frame. Motion must be smooth, restrained and suitable for a seamless desktop Live2D-style wallpaper. No nudity, no exposure, no explicit sexual action, no lip movement, no speaking, no hand movement, no limb movement, no pose change, no body turn, no walking, no camera motion, no zoom, no pan, no tilt, no shake, no cut, no scene change, no morphing, no extra fingers, no extra limbs, no text and no subtitles. Audio: quiet night-garden ambience with very soft leaves and distant wind, no speech and no music.
```

## 可替换字段

- 场景：`warmly lit night garden`
- 主体材质：`glossy resin/PVC material`
- 微动作一：一次完整眨眼
- 微动作二：几乎不可见的上身呼吸
- 微动作三：发梢与挂饰轻微二级运动
- 音频：保留安静环境声作为 H3 联合生成检查；动态壁纸成片在步骤 8 去除音轨

## 动作控制规则

1. 每次最多指定 2–3 个微动作，不同时要求转头、抬手、走动或镜头运动。
2. 使用 `anchored`、`same pose`、`same silhouette`、`locked-off` 和 `perfectly static background` 多重约束。
3. 不写泛化的 `dynamic motion`、`cinematic camera`、`dramatic movement`。
4. HMNSFW V2.5 仅作为动作先验，默认 `0.5`；强度 `0` 即关闭。
5. 若姿态仍漂移，优先启用“首帧=尾帧”约束，而不是立刻提高 LoRA 强度。

## 质量筛选标准

- 脸、瞳孔、发型、服装边界和挂饰不闪烁；
- 手脚与身体轮廓不重构；
- 背景和镜头保持静止；
- 至少出现一次自然眨眼或可辨认的呼吸；
- 末帧相对首帧漂移较小，适合后续制作循环；
- 不出现意外裸露或与提示不一致的内容。

