# MiniMax H3 Live2D 循环视频：运动连续性 + 2×时间压缩/VFI 验证计划

## 0. 任务定位

本计划只解决一个目标：

> 在 **ComfyUI 内完成从单张静态图到可长期循环的 Live2D 风格视频**，不依赖 mirror/倒放作为主方案；重点解决人物微动画与刀身闪电/电弧特效在循环边界处的**时间连续性**，并验证“减少 H3 原生帧数，相当于压缩时间，再用 VFI 插帧恢复到正常时长/观感速度”的可行性。

当前参考图是一张二游/MMD 风格角色静帧，画面包含：
- 角色主体；
- 轻微可动的头发、衣摆、身体；
- 刀身附着式紫色闪电/电弧特效。

原图中的花瓣不再作为动画元素。由于“花瓣从出现到落出画面”的完整生命周期会显著拉长循环周期，本计划改为**在进入 H3 前删除花瓣**，避免让花瓣成为循环连续性的约束。

刀身电弧不是严格时间对称运动，因此 **mirror/ping-pong 不是主路线**。

执行者：Codex  
执行环境：现有 MiniMax H3 / ComfyUI 项目  
首要原则：**优先复用已验证工作流、节点、模型、脚本和 preset，不重造轮子，不先装新插件。**

---

# 1. 已知基线（不得重复探索）

以下事实已经实测，应作为本计划的硬约束：

1. 目标设备：
   - RTX 5080 16GB VRAM
   - 32GB 系统内存（约 31.11 GiB 可见）

2. H3 FL2VA 在该机器可用。

3. 原生 1080p 正确路线：
   - 内部 1920×1088
   - VAE decode
   - 再缩放为 1920×1080

4. 1080p 原生帧数实测：
   - 39F：通过
   - 56F：通过
   - 73F：通过但接近 RAM 边界
   - 90F：失败
   - 90F 的根因不是 CreateVideo 单独造成，而是 `VAEDecode + ImageScale` 阶段双批次同时驻留导致 RAM 爆满。

5. 日常档：
   - 56F = 推荐安全档
   - 73F = 边界档
   - 不应为了本任务继续优先攻击 90F+ 原生 1080p。

6. RIFE 4.26 已经技术跑通。
   - 之前失败的是“人工关键帧本身错误，像图层平移”。
   - 这不能推出 RIFE 对 H3 原生连续视频无效。
   - RIFE 只负责补时间采样，不负责修正错误动作逻辑。

7. H3 原生首尾锚定已技术通过：
   - 同一静帧首尾约束可维持角色和整体运动连续；
   - 但此前出现“闭眼阶段过长”；
   - 说明 H3 可以处理回环约束，但单帧首尾相同不等于运动/特效生命周期一定连续。

8. 当前项目已存在：
   - ComfyUI 0.34 独立测试实例；
   - `MiniMaxH3AddGuide`；
   - 节点可在任意 `frame_idx` 添加图像/短视频等 guide；
   - 现有 streaming 输出链；
   - 现有 RIFE；
   - 现有 4K 路线。

执行前先阅读：
- `README.md`
- `VALIDATION_HISTORY.md`
- `plans/`
- `presets/`
- `workflows/`
- `scripts/`

不要根据旧聊天记忆改写当前基线；以 repo 当前文件为准。

---

# 2. 本轮核心问题

本轮不是继续追求“更多 H3 原生帧”。

要验证两个核心假设：

## H1：非对称闭环可由 H3 正向生成解决

目标不是：

`A -> B -> reverse(B -> A)`

而是：

`A -> ... -> B -> ... -> A`

且所有时间始终向前。

循环中允许：
- 刀身电弧生成、增强、分叉、衰减、消失，再产生新电弧；
- 人物完成一个轻微 idle cycle。

关键验收不是“首尾像素完全相同”，而是：

> 视频从末尾跳回开头时，人物运动相位、刀身电弧生命周期没有明显的 motion cut / temporal discontinuity。

---

## H2：H3 时间压缩 + VFI 时间展开可替代更多原生帧

用户所说的“2×”不是后期删帧，而是：

1. 用较少 H3 原生帧完成一个本来应更慢的完整动作过程；
2. 例如用 56F 表达约 4.5 秒左右的最终运动逻辑；
3. 再用 RIFE 2× 在相邻原生帧之间补帧；
4. 最终仍按 24fps 编码；
5. 从而把 56F 的 H3 运动信息展开成约 111F/112F 的最终视频。

概念：

`H3 sparse temporal sampling -> VFI -> 24fps playback`

而不是：

`H3 full video -> delete frames -> VFI`

要判断：
- 人物微动作是否自然；
- 电弧从无到有/从有到无时，RIFE 是否产生鬼影、双电弧、溶解、闪烁；
- 2× 是否可接受；
- 4× 暂不作为本轮主目标。

---

# 3. 约束

## 3.1 必须满足

- 全流程最终可在 ComfyUI 体系内完成。
- 原图花瓣在 H3 前处理阶段删除，后续不作为动态元素。
- 不把 mirror 作为主循环方案。
- 不把花瓣或电弧拆到 AE / Blender / Unity / Wallpaper Engine 单独制作。
- 不要求 90F+ 原生 1080p 才算成功。
- 不修改已验证模型权重和主实例。
- 优先在现有 0.34 测试实例运行。
- 所有测试都记录：
  - workflow / preset；
  - seed；
  - prompt；
  - frame count；
  - 分辨率；
  - steps；
  - LoRA；
  - VRAM peak；
  - RAM peak；
  - elapsed time；
  - 输出文件；
  - SHA-256；
  - 人工验收结论。

## 3.2 禁止

- 不允许为了“看起来能跑”关闭内存熔断。
- 不允许通过提高 swap/pagefile 把明显 OOM 伪装成通过。
- 不允许一开始就安装大量未知 custom node。
- 不允许把单帧首尾 MAD 小直接当成“循环成功”。
- 不允许只看静态抽帧判断特效连续性。
- 不允许使用 mirror 结果来替代本轮正向闭环验证。
- 不允许把 RIFE 的插值结果当成新的生成语义；RIFE 不负责“理解闪电应该如何生灭”。

---

# 4. 阶段 A：仓库与节点能力审计

## A1. 读取现状

Codex 先检查当前 repo：

1. 当前 active plan/task；
2. 现有 H3 1080p workflow；
3. 现有首尾 guide workflow；
4. 现有 RIFE workflow；
5. 现有 streaming 输出；
6. 是否已有任何：
   - motion context；
   - video guide；
   - head/tail extraction；
   - concatenate；
   - trim overlapping context；
   - multi-guide；
   - loop bridge；
   相关节点或脚本。

输出：
`artifacts/loop_vfi_probe/A1_repo_audit.md`

---

## A2. 验证 `MiniMaxH3AddGuide`

必须从当前 ComfyUI `/object_info` 或当前节点定义中确认实际接口，不凭记忆。

记录：
- 输入类型；
- `frame_idx`；
- 是否可接受 VIDEO / IMAGE batch；
- 多 guide 是否可串联；
- guide 帧数合法要求；
- 是否支持把短视频放在任意时间位置；
- 是否存在特殊 padding / overlap 行为。

输出：
`artifacts/loop_vfi_probe/A2_addguide_capability.json`

---

## A3. 审计本机是否已有 H3 motion-context 类节点

先查本机安装和 repo。

只有在现有节点无法完成“尾部多帧上下文 -> 正向 bridge -> 头部多帧目标”时，才允许进入外部方案调研。

若需要外部节点：
1. 先审计源码；
2. 检查依赖；
3. 检查网络行为；
4. 检查是否复制/下载大模型；
5. 检查是否改写主 ComfyUI；
6. 只装进 0.34 测试实例；
7. 记录 commit。

不要因为节点名字带 `loop` 就假定它是“视频无缝循环”。

---

# 5. 阶段 B：建立“无 mirror 的正向循环”基线

本阶段先**不加 RIFE**。

目的是先证明循环运动逻辑本身成立。

## B0. 先删除输入图中的花瓣

在生成主视频前，先得到一个**无花瓣版本的输入图**。

要求：
- 全流程仍在 ComfyUI 内完成；
- 优先复用现有 inpaint / image-edit 节点；
- 只删除花瓣，不重绘人物、武器、背景主体结构；
- 尽量保持原图构图、角色身份、刀身、电弧区域和光照不变；
- 若现有节点无法稳定删除花瓣，允许先生成一张静态 clean plate，再把它作为后续 H3 的唯一输入；
- 删除后必须人工比对，若人物、刀、脸、服装或背景被明显改写，则该 clean plate FAIL。

输出：
- `input_clean_no_petals.png`
- `B0_cleanplate_review.md`

后续所有 Main / Bridge / RIFE / 1080p 测试都只使用该无花瓣输入，不再测试花瓣运动。

---

## B1. 生成主视频 Main

第一轮使用低成本验证：

- 分辨率：1024×576
- 原生帧数：56F
- FPS metadata：24
- steps：20
- 模型/采样器/LoRA：沿用当前标准 Live2D baseline
- camera：静止
- seed：先筛 3 个，不超过 5 个

提示词目标：

### 人物
- subtle idle body motion
- gentle breathing
- slight head / shoulder movement
- natural twin-tail sway
- subtle cloth movement
- no large pose change
- no camera movement

### 花瓣
- no petals
- no falling petals
- no drifting petals
- do not generate new petal particles

### 刀身电弧
不是“一次爆炸雷击”，而是：
- restrained purple electrical arcs attached to the blade
- arcs emerge, intensify, branch slightly, decay and disappear naturally
- new arcs may appear later
- no explosive lightning strike
- no full-screen flash
- no detached lightning crossing the frame

### 循环方向
不要求 mirror。
允许最终状态与第一帧图像接近，但必须保持正向时间逻辑。

保存每个 seed。

人工快速筛选只选：
- 角色稳定；
- 不重新生成花瓣或类似花瓣粒子；
- 刀身电弧不是全屏随机跳变；
- 无镜头推拉；
- 无明显身份漂移。

选最好的 1 个进入 B2。

---

## B2. 提取 Head / Tail motion context

从最佳 Main 提取：

第一轮：
- `Head = first 22 frames`
- `Tail = last 22 frames`

保存：
- `head_22`
- `tail_22`

并生成 contact sheet / MP4 方便观看。

不要只存第一/最后单帧。

---

## B3. 生成 Bridge

目标：

> 使用 Tail 的运动趋势作为 bridge 起点，并让 bridge 最终进入 Head 的运动趋势。

优先级：

### 路线 1：现有 H3 原生 guide / multi-guide 能做到
优先用现有节点实现。

### 路线 2：现有已安装 motion-context 节点
如果已有可靠实现，则使用。

### 路线 3：需要最小新增节点
只有 A3 证明现有能力不足时才做。

Bridge 第一轮目标长度：
- 39F 或 56F，优先 39F；
- 576p；
- 20 steps；
- 独立 seed。

不要要求 bridge 的每一帧复制 Head/Tail。
目标是：
- Tail 后继续正向发展；
- 不出现花瓣或类似新增粒子；
- 电弧自然结束/重新生成；
- 人物自然回到 Main 开头的运动状态；
- 最终能进入 Head 的“运动相位”。

---

## B4. Trim overlap + concatenate

拼接逻辑必须避免重复 context。

概念：

`Main core + Bridge core`

其中：
- Tail 已作为 Bridge 的前置 context，则对应重复区需要裁掉；
- Head 已作为 Bridge 的目标/末端 context，则根据节点实际输出决定是否裁掉重复段；
- 禁止简单 `Main + Bridge` 无脑拼接。

最终输出：
`loop_no_vfi_576p.mp4`

---

# 6. 阶段 C：循环连续性验收

这一阶段比 MAD 更重要。

## C1. 人工动态观看

至少：
- 正常速度连续播放 2 分钟；
- 不显示进度条；
- 连续循环至少 20 次。

分别观察：

### 人物
- 身体是否边界处突然换方向；
- 头发是否边界处跳一下；
- 裙摆是否相位断裂；
- 眼睛是否突然开/闭。

### 刀身闪电
这是本轮最高权重：
- 电弧是否在边界突然断掉；
- 是否从完全消失直接跳成强电弧；
- 是否出现亮度突变；
- 是否有“上一帧一条电弧，下一帧完全不同结构”的硬切；
- 生命周期是否表现为自然的生成/增强/分叉/衰减/消失。

---

## C2. 自动指标

自动指标只能辅助，不作为最终 PASS 唯一依据。

至少计算：
- 首尾全图 MAD；
- 首尾主体区域 MAD；
- 首尾背景 MAD；
- 首尾若干帧 temporal residual；
- boundary 前后 5~10 帧的相邻帧差分曲线；
- boundary 是否成为全片 temporal residual 的异常峰值。

新增一个高价值指标：

`boundary_motion_spike_ratio`

概念：
- 计算正常内部相邻帧差的 median / p95；
- 计算 loop boundary 最后一帧 -> 第一帧的差；
- 输出 boundary / internal_p95 比值。

不要硬编码 PASS 阈值，先收集基线，再结合人工观看决定。

---

## C3. B 阶段 Gate

### PASS
同时满足：
1. 人物循环无明显 motion cut；
2. 不重新生成花瓣或类似花瓣粒子；
3. 刀身电弧边界没有明显硬切；
4. 连续观看 20+ loop 不容易定位边界；
5. 无新身份/材质退化。

### PARTIAL
人物可接受，但刀身电弧仍能明显识别边界。

### FAIL
人物或特效存在明显硬切，或 bridge 自身发生严重重绘。

如果 B FAIL：
- 不进入 1080p；
- 不进入 4K；
- 不通过 RIFE 掩盖问题。

---

# 7. 阶段 D：2×时间压缩 + RIFE 恢复验证

只有 C 阶段至少 PARTIAL 才进行。

本阶段回答：

> 能不能用较少 H3 原生帧，表达完整循环动作，然后 RIFE 2× 使最终视频恢复到更慢、更顺的 24fps 成片？

---

## D1. 术语固定

本项目中的“2×时间压缩”定义：

假设最终需要约 4.5 秒动作。

不直接 H3 生成约 108F。

而是：
- H3 只生成约 56F 的动作采样；
- 在这 56F 中要求动作完整走完；
- RIFE 2×；
- 输出约 111/112F；
- 仍然以 24fps 编码；
- 成片时长约 4.6 秒。

它不是：
- 先生成 112F；
- 再删一半；
- 再补回来。

---

## D2. 测试矩阵

第一轮只测 2×，不测 4×。

至少比较：

### Baseline
`56F H3 -> no VFI -> 24fps`

### Candidate
`56F H3 -> RIFE 2× -> 24fps`

若 B 阶段 loop 由 Main + Bridge 组成，则两段都统一进入同一 RIFE 流程，避免只对某段补帧。

---

## D3. VFI 重点观察

### 人物
- 是否更顺；
- 是否出现双轮廓；
- 手、脸、头发是否有 morph。

### 刀身电弧
这是最高风险：
- 无 -> 有 的相邻帧之间是否出现“幽灵电弧”；
- 电弧分叉变化是否被糊成大片光带；
- 电弧消失时是否残留透明鬼影；
- 是否出现两套电弧拓扑叠在一起；
- brightness flicker 是否变成 mushy fade。

---

## D4. 结论分类

### VFI_PASS
2× 后：
- 观感更顺；
- 无明显新伪影；
- 电弧生命周期仍可信；
- 不重新生成花瓣。

=> 2× VFI 纳入最终流程。

### VFI_PARTIAL
人物明显受益，但电弧偶尔有轻微鬼影。

=> 保留为可选后处理；
=> 后续可以通过提示词让电弧生命周期稍微延长、降低单帧拓扑跳变，再复测。

### VFI_FAIL
电弧或粒子出现明显双影/溶解。

=> 不用 RIFE 扩时；
=> 保留原生帧；
=> 优先依靠 Main+Bridge 多段 H3 正向生成增加总时长，而不是继续把 2× 变 4×。

---

# 8. 阶段 E：上下文长度 A/B

若 22F bridge 不能稳定解决电弧连续性，再做：

- 5F
- 22F
- 39F

优先比较 22F vs 39F。

目的：
- 判断更长 motion context 是否改善电弧生命周期；
- 判断更长 context 是否导致 bridge 自由度过低；
- 判断 RAM / latency 增幅。

不要一开始就用 56F context。

输出表：

| context | 人物连续 | 电弧连续 | bridge自由度 | RAM | time |
|---|---|---|---|---|---|

选择“最短且足够”的 context。

---

# 9. 阶段 F：1080p 复现

只有 576p Gate PASS 后才上 1080p。

原则：
- 仍然使用 56F 为主档；
- 不优先 73F；
- 不尝试 90F；
- 保持已有 1920×1088 -> 1920×1080 规范；
- 保持 streaming 输出；
- 保持熔断。

必须用通过的同一：
- prompt；
- 逻辑；
- context 长度；
- workflow；
- seed 策略。

注意：
同 seed 跨会话/不同内存状态不保证拿到 bit-identical 母版，因此 1080p 必须重新人工观看，不能只凭 seed 名称认为与 576p 同轨迹。

---

# 10. 阶段 G：最终 ComfyUI 工作流

最终目标是形成一个用户可直接使用的工作流，而不是只留实验脚本。

目标 UI：

## 输入
- 单张图片
- H3 prompt
- seed
- loop preset
- VFI on/off
- output fps
- optional upscale

## 自动步骤
1. Load image
2. H3 Main
3. Extract Head/Tail context
4. H3 Bridge
5. Trim overlap
6. Concatenate
7. Optional RIFE 2×
8. 1080p encode
9. Optional 4K
10. Save final loop

理想情况下：
- 不需要用户手工导出中间帧；
- 不需要用户手动输入 Head/Tail；
- 不需要外部 AE/Blender；
- 不需要 mirror。

---

# 11. 提示词策略

不要直接在 prompt 写：
- `2x speed`
- `fast motion`

因为模型可能理解成“动作急促”，而不是“在较少帧内完整覆盖正常动作周期”。

要写成：
- complete one subtle idle motion cycle within the clip
- the motion evolves continuously from beginning to end
- no abrupt pose change
- no camera movement
- no petals, no falling petals, no drifting petal particles
- blade electricity evolves continuously: emerging, intensifying, branching slightly, fading and disappearing naturally
- avoid instantaneous one-frame lightning changes
- avoid explosive lightning strikes

如果目标是让 VFI 更容易：
- 电弧不要只活 1 个原生帧；
- 尽量让一次电弧事件覆盖至少多个 H3 原生帧；
- 不要让强电弧结构在相邻帧完全重构。

---

# 12. 失败分支

## F1. 人物顺，电弧不顺
最有价值的失败。

处理：
1. 保持 bridge；
2. 增加 context 22F -> 39F；
3. 让电弧更“附着式、连续式”，减少瞬间重拓扑；
4. 重筛 seed；
5. 再测；
6. 不回退到 mirror。

---

## F2. H3 又重新生成花瓣/类似粒子
处理：
- 强化负面约束：`no petals / no drifting particles / no falling debris`；
- 检查 clean plate 是否残留明显花瓣形状；
- 必要时重新做 B0 clean plate；
- 不把花瓣重新纳入循环逻辑。

---

## F3. Bridge 重绘人物
处理：
- 检查 guide / context 是否正确；
- 增加 identity 约束；
- 缩短 bridge；
- 调 context 长度；
- 调 seed；
- 不用外部单帧 edit 伪造关键帧。

---

## F4. RIFE 破坏电弧
处理：
- RIFE 标记为 optional；
- 最终使用原生 H3 loop；
- 或使用更多 H3 正向段增加时长；
- 不上 4× VFI。

---

# 13. 产物

所有本轮产物放入：

`artifacts/loop_vfi_probe/`

至少包括：

- `A1_repo_audit.md`
- `A2_addguide_capability.json`
- `B_main_runs.csv`
- `B_head_tail_manifest.json`
- `B_bridge_runs.csv`
- `C_loop_metrics.json`
- `C_manual_review.md`
- `D_vfi_ab.csv`
- `D_vfi_manual_review.md`
- `E_context_ab.csv`（如执行）
- `F_1080_report.md`（如进入）
- 最终 workflow JSON
- 最终 preset
- 代表性 MP4
- SHA-256 manifest

---

# 14. 执行策略

严格使用 gate，不要一次性跑完整矩阵。

顺序：

1. A：能力审计
2. B：576p Main + 22F context + Bridge
3. C：循环动态验收
4. 若 C 至少 PARTIAL -> D：RIFE 2×
5. 若电弧仍差 -> E：22F vs 39F context
6. 576p PASS 后 -> F：1080p
7. 1080p PASS 后 -> G：固化 UI workflow
8. 最后才考虑 4K

---

# 15. 本轮成功定义

本任务最终 PASS 不是“成功输出视频”。

必须同时满足：

1. 单张图片可进入完整 ComfyUI 流程；
2. 人物有自然 Live2D 风格微运动；
3. 输入图花瓣已删除，生成过程中不重新产生花瓣/类似粒子；
4. 刀身电弧在 loop 边界没有明显生成/消失硬切；
5. 不使用 mirror 作为主闭环机制；
6. 连续观看 20+ loop 难以准确定位边界；
7. 若启用 RIFE 2×，不会给人物/电弧引入明显鬼影或双结构；
8. 1080p 在 RTX 5080 16GB + 32GB RAM 上稳定运行；
9. 保留熔断和可回滚；
10. 形成可重复执行的 workflow + preset + 报告。

---

# 16. 终止条件

以下任一成立则停止继续堆复杂度，先报告：

- 现有 H3 / AddGuide 无法提供足够 motion-context 语义；
- bridge 连续筛多个 seed 仍无法改善电弧边界；
- 新增 motion-context 节点需要侵入主实例或高风险依赖；
- RIFE 2× 对刀身电弧产生不可接受伪影；
- 1080p RAM 再次接近/超过熔断；
- 必须依赖 90F+ 原生帧才能工作。

报告应明确：
- 已证实什么；
- 未证实什么；
- 当前最高价值下一步；
- 不允许用“可能”“应该”替代实测。

---

# 17. Codex 最终汇报格式

最终给用户的摘要保持简洁：

## Result
PASS / PARTIAL / FAIL

## Best Route
当前最优工作流一句话描述。

## Key Evidence
- 最佳分辨率/帧数
- context 长度
- seed
- RAM/VRAM
- loop 边界表现
- RIFE 2× 表现

## Remaining Blocker
只写真正的最高优先级阻塞。

## Files
列出最终 workflow / preset / report / MP4 路径。

不要擅自进入与本任务无关的新路线。
