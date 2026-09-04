# Contradiction Audit / 规范矛盾审计

本文件记录仓库中已经识别出的 **相互矛盾或容易被误读为冲突的结论**，以及当前主 Agent 的规范决议。

它是审计索引，不取代各 Contract；每项最终 normative source 仍是所列文件。

## A-001 循环方式：镜像回放 vs 首尾同图锚定

**旧结论**

`plans/H3_1080_LOOP_STRATEGY_NOTES.md` 写“镜像回放已定案/锁定”。

**当前决议**

正式生产采用：

```text
same_image_first_last_anchor
-> 用户选正式 take
-> Gate D 人工选择帧解决尾部降速
```

镜像回放保留为历史/实验能力，不是当前默认生产路线。

**Normative source**

- `04-native-1080p-73f.md`
- `05-frame-sequence-selection.md`

**状态**：RESOLVED

---

## A-002 主状态机：draft -> long_draft -> final vs 四个人工 Gate

**旧结论**

旧 pipeline、README、history 曾使用：

```text
Turbo -> draft -> long_draft -> final -> loop -> 4K
```

**当前决议**

```text
Director -> T2I -> Gate A
-> lowres seed -> Gate B
-> formal 1080p/73f -> Gate C
-> canonical frames -> Gate D
-> interpolation -> upscale -> validation
```

旧 `draft/long_draft/final` 只可作为 legacy/experimental implementation profiles。

**Normative source**

- `../pipeline/README.md`

**状态**：RESOLVED; implementation cleanup pending C-008

---

## A-003 “final” 分辨率：1344×768×124 vs 1920×1080×73

**旧结论**

历史 `final` profile 是 1344×768、124f。

**当前决议**

正式 take 目标是：

```yaml
visible_resolution: 1920x1080
frames: 73
fps: 24
```

1344×768×124 不再拥有“final/master”规范语义。

**Normative source**

- `04-native-1080p-73f.md`

**状态**：RESOLVED; implementation naming pending C-008

---

## A-004 正式 1080p：1920×1080 vs H3 内部 1920×1088

**表面冲突**

文档有时说“原生 1080p”，实现却生成/解码 1920×1088 再变成 1920×1080。

**当前决议**

这是内部空间和可见交付空间的区别：

```text
internal: 1920x1088
visible:  1920x1080
```

不得把内部 1088 报成最终分辨率，也不得把 1080 visible 误解为 H3 必须直接以 1080 内部采样。

**Normative source**

- `04-native-1080p-73f.md`
- `10-capability-baseline.md`

**状态**：RESOLVED

---

## A-005 Frame numbering：0-based vs 1-based

**旧/实现事实**

- Python retime 工具把 frame index 当 0-based；
- 早期 streaming plan 预期 `frame_00000`；
- ComfyUI Native SaveImage 实际历史输出从 1 开始；
- 用户自然使用“第 1~73 帧”。

**当前决议**

所有 human-facing / manifest frame number 统一：

```text
1-based
```

内部 0-based 仅允许存在于明确的转换边界。

**Normative source**

- `05-frame-sequence-selection.md`

**状态**：RESOLVED; implementation gap C-002

---

## A-006 Gate D：自动 equalize/remap vs 用户最终 keep list

**旧结论**

`plan2.md` 和多个工具探索自动 speed equalization、tail compression、RIFE remap。

**当前决议**

用户 Gate D 是时间轴主要编辑权：

```text
approved keep list
-> rebuild
-> interpolation only
```

自动 equalize/tail compression/remap 默认不进入生产主线。需要使用时必须显式批准为独立策略。

**Normative source**

- `05-frame-sequence-selection.md`
- `06-interpolation.md`

**状态**：RESOLVED; implementation isolation pending C-003

---

## A-007 可选 HMNSFW LoRA：默认 0.5 vs 默认关闭

**旧结论/实现**

历史 A/B 后多个 runner/preset 将 0.5 当默认。

**当前决议**

生产默认：

```yaml
lora_enabled: false
lora_strength: 0
```

只有当前任务明确启用才加载并记录。

**Normative source**

- `03-lowres-i2v-seed.md`
- `10-capability-baseline.md`

**状态**：RESOLVED; implementation gap C-006

---

## A-008 RAM abort：30.5 GiB vs 31.0 GiB

**旧结论**

历史阶段曾使用 30.5GiB；后续受控测试改为 31.0GiB。

**当前决议**

当前生产默认：

```text
31.0 GiB
```

它是生产保护线，不是硬件绝对上限。改变需要用户/主 Agent受控决策。

**Normative source**

- `01-runtime.md`

**状态**：RESOLVED

---

## A-009 ComfyUI 端口：8188 vs 8189

**旧结论**

不同历史阶段分别把 8188/8189 绑定到 0.33/0.34 实例；Comfy Desktop 后来出现端口变化。

**当前决议**

端口不是实例身份。运行时读取实际 ComfyUI version/capabilities。

**Normative source**

- `01-runtime.md`

**状态**：RESOLVED

---

## A-010 Low-res seed：Turbo first-frame I2V vs formal LoopLock semantic

**当前实现差异**

Turbo preview 只有 first-frame I2V；正式 take 要求 same-image first/last anchor。

**当前决议**

Turbo 只能标记：

```yaml
screening_only: true
loop_semantic_match: false
```

可以粗筛 seed，但不能声称正式 loop 行为已验证。是否增加标准低分辨率 loop-confirmation 由主 Agent根据成本/漂移证据决定。

**Normative source**

- `03-lowres-i2v-seed.md`
- `04-native-1080p-73f.md`

**状态**：RESOLVED at spec level; implementation gap C-009

---

## A-011 1080p streaming：canonical PNG 优势 vs 缺 last-frame anchor

**当前实现差异**

stream runner 已有 PNG、RunId、watchdog、外部编码，但历史 workflow 只有 first anchor；普通 live2d runner 能 LoopLock，却不是 canonical streaming production entry。

**当前决议**

正式生产入口必须同时具备：

```text
same-image first/last anchor
+ 1920x1080 / 73f
+ canonical PNG sequence
+ preview video/report
```

不能二选一。

**Normative source**

- `04-native-1080p-73f.md`
- `11-rebuild-manifest.md`

**状态**：spec RESOLVED; implementation gap C-001

---

## A-012 4K：24fps profile vs 插帧后的高 fps

**旧/实现事实**

历史 4K profile 固定 24fps，而后处理路线可能先插到 60fps。

**当前决议**

Upscale 是空间处理，必须保持 **当前已经批准的输入 fps**。如果实现 profile 不支持该 fps，应修实现/参数化 profile，不能自动降回 24fps。

**Normative source**

- `07-upscale.md`

**状态**：RESOLVED at spec level; implementation gap C-004

---

## A-013 Final validator：固定 61f/24fps/119 loops vs 动态 keep-list/fps

**旧结论**

历史 4K validator 针对一个 61f@24fps 样片建立固定门槛。

**当前决议**

Final validator 必须从 current expected spec 获取：

```text
resolution
fps
frame_count
codec/pixel format
silent
```

历史 61f/119-loop 指标只可作为 regression evidence。

**Normative source**

- `08-final-validation.md`

**状态**：RESOLVED at spec level; implementation gap C-005

---

## A-014 73f：历史“边界/不适合无人值守” vs 当前正式目标

**表面冲突**

历史资源测试说 73f 接近 32GB 边界；当前正式生产 Contract 又指定 73f。

**当前决议**

这两个结论处于不同层：

- Product Contract：正式目标仍是 73f；
- Runtime Contract：任何一次运行必须先过资源检查和 31.0GiB 熔断。

如果环境当前无法安全跑 73f，状态是 `BLOCKED_RESOURCE_HEADROOM`，不是自动把产品规范降成 56f。

如果长期证据显示 73f 在目标硬件不可持续，则提交 Contract Review，由主 Agent决定是否改变正式产品目标。

**Normative source**

- `04-native-1080p-73f.md`
- `01-runtime.md`

**状态**：RESOLVED

---

## A-015 Audio VAE：旧 workflow 存在音频链 vs 动态壁纸默认静音

**旧实现**

早期 H3 workflow 包含 audio VAE / audio decode。

**当前决议**

当前生产主线默认 silent，因此 audio VAE 不属于生产最低必需依赖。需要音频是新的需求/Contract 变化。

**Normative source**

- `10-capability-baseline.md`
- `01-runtime.md`

**状态**：RESOLVED

---

## A-016 历史指标：MAD/PSNR/特定 seed 是否是全局门槛

**旧文档**

history/plans 保存大量单样片 MAD、PSNR、tail ratio、seed、固定 ROI。

**当前决议**

这些是 evidence/regression data，不自动升级为全局质量规范。全局门槛只有在主 Agent明确提升到 Contract 后才 normative。

**Normative source**

- `08-final-validation.md`
- `00-governance.md`

**状态**：RESOLVED

---

## 审计规则

以后发现新矛盾时：

1. 不直接删历史事实；
2. 找出它属于 governance / pipeline / execution contract / implementation / history 哪一层；
3. 指定唯一 normative source；
4. 若规范本身需要改变，走 `CONTRACT_REVIEW_REQUIRED`；
5. 若只是代码偏离，登记到 `CONFORMANCE_STATUS.md`；
6. 本表增加一项，避免以后重复争论同一冲突。