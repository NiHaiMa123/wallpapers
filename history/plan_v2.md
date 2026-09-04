# MiniMax H3 Live2D 正向闭环 + VFI 实验计划（v2）

## 0. 结论

本计划吸收 Codex 可行性分析后的修正版。

总体评定：**PARTIAL，但 576p 实验可执行。**

当前目标只验证三件事：

1. `Main -> Bridge -> 正向闭环` 能否解决刀身电弧在循环边界处的时间连续性；
2. `RIFE 2×` 是否适合作为闭环视频的时间展开/慢放；
3. 576p 通过后，1080p 双 guide 是否能在 RTX 5080 16GB + 32GB RAM 下安全运行。

在 576p Gate 通过前：
- 不替换现有稳定默认路线；
- 不要求 1080p；
- 不要求单个巨型 ComfyUI prompt；
- 不声称 VFI 已能替代长原生 H3。

---

# 1. 最终目标

输入：单张角色静态图。

输出：ComfyUI 体系内完成的 Live2D 风格循环视频，包含：

- 轻微呼吸；
- 头部/肩部小幅运动；
- 双马尾、衣摆轻摆；
- 自然眨眼；
- 刀身附着式紫色电弧；
- 静态镜头；
- 无花瓣。

原图花瓣先删除，不再纳入循环。

刀身电弧具有：

`出现 -> 增强 -> 分叉 -> 衰减 -> 消失`

的非对称时间过程，所以 **mirror / 倒放不作为主闭环机制**。

---

# 2. 已知基线

设备：
- RTX 5080 16GB VRAM
- 32GB RAM（约 31.11GiB 可见）

已验证：
- H3 FL2VA 可运行；
- RIFE 4.26 可运行；
- 逐帧落盘 + 流式编码可运行；
- 1080p 正确链路：`1920×1088 -> VAE decode -> 1920×1080`；
- 1080p：
  - 39F PASS
  - 56F PASS
  - 73F PASS（边界）
  - 90F FAIL
- 56F 为日常推荐档；
- 73F 为边界档；
- 不继续优先攻击 90F+ 1080p。

`MiniMaxH3AddGuide` 已确认：
- 支持 IMAGE batch；
- 支持任意 `frame_idx`；
- 支持多节点串联；
- guide 会裁为 H3 合法帧长度。

实例识别：
- 以实际启动实例、版本、repo path、`/object_info` 为准；
- 不按 8188/8189 端口硬编码。

---

# 3. Bridge 帧数规则

H3 合法帧长度：

`5, 22, 39, 56, 73, 90, 107, 124, ...`

若两侧 context 均为 `C`，Bridge 为 `B`：

`自由生成区 = B - 2*C`

当前组合：

| 单侧 context | Bridge | 自由生成区 |
|---:|---:|---:|
| 5F | 22F | 12F |
| 22F | 56F | 12F |
| 22F | 73F | 29F |
| 39F | 90F | 12F |

因此：

- **禁止 `22F context + 39F Bridge`**；
- 22+22 会在 39F Bridge 内重叠 5 帧；
- 接线 smoke：`22F + 56F Bridge`；
- 质量验证：`22F + 73F Bridge`；
- 39F context 只在后续 576p A/B 中使用，对应至少 90F Bridge。

---

# 4. 最终闭环帧数

Main=`M`，Bridge=`B`，单侧 context=`C`。

拼接定义：

`FinalNative = Main全部帧 + Bridge[C : B-C]`

所以：

`FinalNativeFrames = M + B - 2*C`

主测试：

### 56F Main + 56F Bridge + 双22F context
`56 + 56 - 44 = 68F`

### 56F Main + 73F Bridge + 双22F context
`56 + 73 - 44 = 85F`

---

# 5. RIFE 必须处理闭环边界

普通 FrameInterpolate 不会处理：

`最后一帧 -> 第一帧`

正确流程：

1. 原始 N 帧：
   `[0..N-1]`
2. 追加首帧：
   `[0..N-1, 0]`
3. RIFE 2×
4. 删除最后重复帧

即：

`[0..N-1,0] -> RIFE 2× -> trim duplicated final frame`

最终约为：

`2N`

所以：

- 68F -> 136F -> 24fps ≈ 5.67s
- 85F -> 170F -> 24fps ≈ 7.08s

禁止只插内部帧再直接 loop。

---

# 6. H2 必须拆成两个问题

## H2-A：RIFE 慢放是否可用

可以直接验证：

`native loop -> closed-ring RIFE 2× -> 24fps`

判断：
- 是否更顺；
- 人物是否有 ghosting；
- 刀身电弧是否有双影、溶解、mushy fade。

## H2-B：RIFE 是否可替代长原生 H3

不能只对比：

`56F` vs `56F -> RIFE`

若要声称“替代更多原生时间信息”，必须增加 576p 长原生参考：

- 107F
或
- 124F

第一轮只选一个。

比较：
- 短原生 + RIFE；
- 长原生 H3。

没有长原生参考时，最终结论只能写：

`RIFE 慢放可用/不可用`

不能写：

`RIFE 已替代长原生 H3`

---

# 7. 阶段 A：环境与 repo 审计

先读取：

- `README.md`
- `VALIDATION_HISTORY.md`
- `plans/`
- `presets/`
- `workflows/`
- `scripts/`

确认实际运行实例：
- port；
- ComfyUI version / commit；
- repo path；
- Python / PyTorch；
- `MiniMaxH3AddGuide` node source；
- `/object_info`。

确认已有：
- ImageFromBatch；
- batch concatenate；
- RIFE；
- SaveImage；
- ImageScale；
- mask / composite。

检查 repo 是否已有：
- Bridge runner；
- Bridge preset；
- Head/Tail extraction；
- overlap trim；
- closed-ring RIFE；
- `boundary_motion_spike_ratio`；
- blade arc ROI metrics；
- multi-job orchestrator。

缺什么就记录什么，不先假定已有。

输出：

- `artifacts/loop_vfi_probe/A1_runtime_audit.md`
- `artifacts/loop_vfi_probe/A2_repo_gap.md`

---

# 8. 阶段 B0：花瓣 clean plate

花瓣不参与动画。

默认方案：

`局部 mask 编辑 -> 与原图按 mask 合成`

要求：
- 不用全图 Krea2 edit 作为默认；
- mask 外尽量保持原图像素不变；
- 不重画人物、脸、武器、服装、背景主体；
- 刀身原始电弧区域不能被误删。

输出：
- `input_clean_no_petals.png`
- `B0_mask.png`
- `B0_cleanplate_metrics.json`
- `B0_cleanplate_review.md`

若人物/武器/背景发生明显重绘：FAIL。

---

# 9. 阶段 B1：576p Main

规格：
- 1024×576
- 56F
- 24fps metadata
- 20 steps
- 当前标准 H3 Live2D baseline
- 静态镜头
- 3 个 seed 起步，最多 5 个

提示词方向：

### 人物
- subtle idle body motion
- gentle breathing
- slight head and shoulder movement
- natural twin-tail sway
- subtle cloth movement
- one natural blink
- no large pose change
- static camera

### 刀身电弧
- restrained purple electrical arcs attached to the blade
- arcs emerge, intensify, branch slightly, fade and disappear naturally
- new arcs may appear later
- continuous temporal evolution
- no instantaneous one-frame topology jump
- no explosive lightning strike
- no full-screen flash
- no detached lightning across the frame

### 花瓣
- no petals
- no falling petals
- no drifting petal particles
- no petal-like debris

保存：
- MP4
- frames
- prompt
- seed
- RAM / VRAM
- elapsed
- SHA-256

选最佳 Main。

---

# 10. 阶段 B2：提取 Head / Tail

从最佳 Main：

- Head = first 22F
- Tail = last 22F

保存：
- `head_22`
- `tail_22`
- contact sheet
- preview MP4

---

# 11. 阶段 B3：Bridge 接线 smoke

配置：
- 22F context / side
- 56F Bridge
- 自由区 12F
- 576p
- 20 steps

目标只验证：
- Tail -> Bridge -> Head guide 接线成立；
- 无 guide overlap；
- trim 逻辑正确；
- 人物没有严重重绘。

拼接：

`Main + Bridge[22 : 34]`

最终 native：
`68F`

若失败：停止，不进质量组。

---

# 12. 阶段 B4：Bridge 质量验证

配置：
- 22F context / side
- 73F Bridge
- 自由区 29F
- 576p
- 20 steps

拼接：

`Main + Bridge[22 : 51]`

最终 native：
`85F`

重点：
- Main -> Bridge 是否顺；
- Bridge 自由生成区是否自然；
- Bridge -> Main 开头是否顺；
- 人物运动相位是否连续；
- 刀身电弧生命周期是否连续。

---

# 13. 阶段 C：循环指标

必须增加 ROI，不能只看全图 MAD。

至少：
1. `character_roi`
2. `blade_arc_roi`
3. `background_roi`

指标：
- whole-frame boundary MAD
- character ROI boundary MAD
- blade arc ROI boundary MAD
- background ROI boundary MAD
- internal adjacent MAD median / p95
- boundary adjacent MAD
- `boundary_motion_spike_ratio`

定义：

`boundary_motion_spike_ratio = boundary_delta / internal_delta_p95`

另外至少增加：

### 一阶时间差分
观察速度/变化量是否在 boundary 突变。

### 二阶时间差分
观察加速度/方向变化是否在 boundary 出现尖峰。

若现有 optical flow 代码可复用，可补：
- flow magnitude；
- flow direction consistency。

不是硬依赖。

---

# 14. 阶段 C 人工验收

正常速度连续播放：
- 至少 2 分钟；
- 至少 20 loops；
- 隐藏进度条。

优先观察：

1. 刀身电弧：
   - 是否突然断；
   - 是否从无直接跳到强电弧；
   - 是否亮度硬切；
   - 是否结构瞬间换一套。
2. 头发 / 衣摆：
   - 是否边界突然换方向。
3. 眨眼：
   - 是否边界突开/突闭。
4. 全局亮度：
   - 是否闪一下。

PASS：
- 人物无明显 motion cut；
- 电弧无明显 lifecycle hard cut；
- 无花瓣重新生成；
- 20+ loops 不容易定位边界；
- boundary 指标不形成明显异常峰值。

PARTIAL：
- 人物基本通过，但电弧仍可定位。

FAIL：
- Bridge 重绘人物；
- 电弧明显硬切；
- guide 冲突；
- motion cut 明显。

FAIL 时：
- 不进 1080p；
- 不用 RIFE 掩盖闭环问题。

---

# 15. 阶段 D：closed-ring RIFE 2×

仅当 C >= PARTIAL。

对完整 native loop：

`[0..N-1,0] -> RIFE 2× -> trim final duplicate`

测试：

### 68F native
-> 136F
-> 24fps
-> 5.67s

### 85F native
-> 170F
-> 24fps
-> 7.08s

重点验收：

### 人物
- 双轮廓
- face morph
- hair ghosting
- cloth ghosting
- blink

### 电弧
- 无->有 是否出现幽灵电弧；
- 分叉是否糊成光带；
- 有->无 是否残留；
- 两套拓扑是否叠加；
- loop boundary 插值是否自然。

结论：

- `VFI_PASS`
- `VFI_PARTIAL`
- `VFI_FAIL`

若 VFI_FAIL：
- 不上 4×；
- 保留 native loop；
- 优先增加 H3 正向原生时间。

---

# 16. 阶段 E：长原生 H3 参考

仅用于回答：

> VFI 能否替代更多原生 H3 时间信息？

在 576p 选一组：
- 107F native
或
- 124F native

优先只跑一个。

对比：

### Candidate
短原生闭环 + RIFE 2×

### Reference
长原生 H3

比较：
- 动作丰富度
- 自然度
- 电弧生命周期
- 角色稳定性
- temporal artifacts
- time
- RAM / VRAM

最终结论只能是：

1. `VFI_CAN_REPLACE_LONG_NATIVE`
2. `VFI_ONLY_GOOD_FOR_SLOWDOWN`
3. `VFI_NOT_RECOMMENDED`

---

# 17. 阶段 F：context A/B

若 22F+73F 仍不能解决电弧：

先重筛 Bridge seed。

仍不足，再在 576p 测：

`39F context + 90F Bridge`

注意：
- 只有 12F 自由区；
- 不代表一定比 22F+73F 好；
- 这是强约束连接实验。

记录：

| context | bridge | free core | 人物连续 | 电弧连续 | RAM | time |
|---:|---:|---:|---|---|---:|---:|

---

# 18. 阶段 G：1080p memory smoke

576p PASS 后才执行。

关键风险：

`guide batch + guide VAE encoding + 1088/1080 image batches`

逐帧输出不能解决 guide encoding peak。

## 1080p guide 格式

必须使用：

`1920×1088` 内部帧

作为 AddGuide 输入。

禁止默认使用已经缩到 1920×1080 的帧回喂，因为 AddGuide 的 resize / center 可能改变几何。

## smoke 顺序

1. 5F single guide
2. 5F + 5F dual guide
3. 22F single guide
4. 22F + 22F dual guide

每步记录：
- baseline RAM
- guide encode peak
- sampling peak
- VAEDecode peak
- resize peak
- total peak
- VRAM
- elapsed

保持 31GiB 熔断。

任一步接近熔断：停止。

只有双22F PASS 后才测：
- 22F + 56F Bridge
- 再考虑 22F + 73F Bridge

若 56F 已危险，不继续 73F。

---

# 19. 最终架构：一个入口，多串行 Job

不要构建一个巨型 ComfyUI prompt 同时持有：

`Main + Bridge + RIFE + Scale + Encode`

最终交付改为：

> 一个入口 + orchestrator + 多个串行 ComfyUI jobs

推荐：

### Job 0
Clean plate
-> save
-> free

### Job 1
H3 Main
-> save
-> free

### Job 2
Extract Head/Tail
-> H3 Bridge
-> save
-> free

### Job 3
Trim overlap
-> concatenate native loop
-> save
-> free

### Job 4
Optional closed-ring RIFE 2×
-> save
-> free

### Job 5
1080p / encode
-> save
-> free

### Job 6
Optional 4K
-> save

用户仍然可以“一次提交”。

底层必须串行。

优先实现：
- PowerShell runner
或
- Python runner

通过 ComfyUI API 编排。

---

# 20. 当前待实现

Codex 需要明确补齐：

- Bridge runner
- Bridge preset
- Head/Tail extraction
- overlap trim
- native loop concatenate
- closed-ring RIFE
- `boundary_motion_spike_ratio`
- blade arc ROI metrics
- multi-job orchestrator

除非 repo 实际存在，否则不得写成“已有”。

---

# 21. Gate 顺序

严格执行：

1. A：runtime / repo audit
2. B0：clean plate
3. B1：576p Main 56F
4. B3：22F + 56F Bridge smoke
5. B4：22F + 73F Bridge quality
6. C：loop continuity
7. C >= PARTIAL -> D：closed-ring RIFE 2×
8. 若要证明替代长原生 -> E：107F/124F reference
9. 电弧仍差 -> F：context A/B
10. 576p PASS -> G：1080p memory smoke
11. 1080p PASS -> orchestrator 固化
12. 最后才考虑 4K

---

# 22. 成功定义

## H1 PASS

`Main + Bridge` 能形成**正向时间闭环**，且刀身电弧在 loop boundary 没有明显 lifecycle hard cut。

## H2-A PASS

closed-ring RIFE 2× 能让 native loop 更慢/更顺，且不引入不可接受的电弧伪影。

## H2-B PASS

只有存在 107F/124F native reference 且对比成立时，才允许证明：

> 少量原生帧 + VFI 可替代更长原生 H3。

## 1080p PASS

必须：
- 双 guide 实测通过；
- 31GiB 熔断下仍有余量；
- 使用 1920×1088 guide；
- 人工动态复核通过。

## 最终产品 PASS

- 单图入口；
- 无花瓣；
- 人物自然微动画；
- 刀身电弧循环连续；
- 静态镜头；
- 不依赖 mirror；
- RIFE 可选；
- 串行多 job；
- 32GB RAM 可重复稳定运行；
- 有 workflow + preset + runner + report。

---

# 23. 停止条件

以下任一成立则停止扩大实验：

- 22F + 73F Bridge 多 seed 仍无法建立电弧连续闭环；
- 39F + 90F 也无改善；
- RIFE 2× 明显破坏电弧；
- 1080p 双22F guide 接近/超过熔断；
- 必须依赖 90F+ 1080p 才能成立；
- 必须侵入主实例或引入高风险 custom node 才能继续。

所有报告必须区分：

- 已实测；
- 推断；
- 未验证。

禁止把“理论上可以”写成 PASS。

---

# 24. Codex 最终汇报格式

## Result
PASS / PARTIAL / FAIL

## H1
Bridge 正向闭环是否成立。

## H2-A
RIFE 2× 慢放是否成立。

## H2-B
是否有足够证据证明替代长原生 H3。

## Best Configuration
- Main frames
- Context
- Bridge frames
- Native loop frames
- RIFE frames
- Final duration
- Seed
- RAM / VRAM

## Blade Arc Boundary
专门描述刀身电弧的边界连续性。

## 1080p
- 是否已测
- guide 格式
- RAM peak
- 熔断余量

## Remaining Blocker
只写当前最高优先级阻塞。

## Files
列出 runner / workflow / preset / report / MP4。
