> [!WARNING]
> **NON-NORMATIVE HISTORICAL EVIDENCE.** 本文件记录 2026-08-29~30 的环境、实验、当时默认、失败路线与验证结果。当前生产规范只以 `AGENTS.md`、`pipeline/`、`contracts/` 为准。本文中的 30.5GiB/31.0GiB、56f/73f、HMNSFW 0.5、crossfade、镜像回放、61f/119-loop validator、8188/8189 等结论都只能作为历史证据；如需提升为当前规范，必须走 `CONTRACT_REVIEW_REQUIRED` 并由主 Agent 作为 Spec Owner 审核。

# MiniMax H3 本地工作流验证历史

**验证日期：** 2026-08-29 至 2026-08-30  
**目标设备：** GeForce RTX 5080 16GB VRAM + 32GB 系统内存  
**用途：** 本地、封闭环境中的短视频、动态壁纸和技术验证  
**当前规范入口：** [AGENTS.md](AGENTS.md)｜[pipeline/README.md](pipeline/README.md)｜[contracts/README.md](contracts/README.md)

本文合并原可行性调研、实施计划和步骤 7–21 的阶段报告。它保留可追溯的环境、模型、配置、实测、失败路线和当时待办。本文中的运行命令、默认值、档位与“定案”只代表对应历史阶段；当前生产行为不得从本文直接推导，必须回到 normative MD。

## 1. 总结

MiniMax H3 FL2VA 在 RTX 5080 16GB + 32GB RAM 上可用，最适合的路线是高质量静帧定稿后做短 I2V，而不是把最终角色一致性押在纯 T2V 上。H3 可以生成“看起来像 Live2D”的随机微动画，但不是骨骼绑定系统，不能保证参数化动作、精确口型或永久无漂移。

经过 22 个步骤，以下能力已经实际跑通：

- 官方 H3 I2V、HMNSFW V2.5 可开关运动分支；
- 手办/实时二游 CG 微动画三档预设和外部输入图接口；
- H3 伪 T2I，以及文本 → 首图 → 73 帧视频的一体化链路；
- 三段式 ComfyUI UI 工作流；
- Qwen3.6 双语提示词导演和四参考图定向视觉融合；
- 静音循环、5 分钟重复解码与 4K 两路线；
- ComfyUI 0.34 独立测试实例、原生任意帧引导、原生首尾闭环；
- 内部 1920×1088 → 标准 1920×1080 的短片原生 1080p；
- 1080p 逐帧落盘 + 外部流式编码，输出阶段内存与帧数解耦。

资源结论：32GB RAM 只是可运行下限。多数 H3 任务峰值约 29–30.5GiB；生成时必须串行、及时卸载 Qwen/扩散模型、关闭其他重任务并使用 30.5GiB 熔断。若长期批量生产，64GB 内存比继续堆叠激进量化或更多 LoRA 更有价值。

## 2. 阶段状态

| 步骤 | 结果 | 核心结论 |
|---:|---|---|
| 1 | 通过 | 主实例 ComfyUI 0.33.1、RTX 5080、共享模型路径和 API 已确认。 |
| 2 | 通过 | ModelScope → HF-Mirror → Hugging Face 的可续传下载链建立。 |
| 3 | 通过 | H3 原生节点与官方模板齐全，第一版无需第三方 H3 节点。 |
| 4 | 通过 | FL2VA 四个必需权重下载、大小与 SHA-256 校验完成。 |
| 5 | 通过 | 无 LoRA 官方 I2V 两个 seed 均生成 73 帧并通过解码/目视检查。 |
| 6 | 通过 | HMNSFW V2.5 原生 LoRA 加载、0 强度绕过和 0.5 A/B 通过。 |
| 7 | 通过 | 微动画工作流、三档预设、提示模板和运行器固化。 |
| 8 | 通过 | 12 帧交叉融合静音循环通过 119 轮、5 分钟验证。 |
| 9 | 通过 | Turbo 4/8 步只用于预览；最终母版保持标准 20 步。 |
| 10 | 机器侧通过 | 4K 两路线均通过；默认 temporal_safe，仍待人工动态观看。 |
| 11 | 接口通过 | 换图无需编辑 JSON；每张新图仍需完整筛 seed。 |
| 12 | 通过 | H3 伪 T2I 和文本到 Live2D 一体化链路实跑成功。 |
| 13 | 链路通过 | 明确成年内容可本地生成；测试视频锁姿不足，不能作最终母版。 |
| 14 | 通过 | 三套 UI 工作流安装并逐阶段实跑。 |
| 15 | 通过 | Qwen 双语提示词导演 T2I/I2V 两模式通过并能自动卸载。 |
| 16 | 通过 | 四参考图过滤边界和真实双图融合通过。 |
| 17 | 技术通过、视觉方向迭代 | 2K 链路可用；从树脂手办调整为实时二游 CG + MMD 风。 |
| 18 | 技术通过、视觉失败 | RIFE 插帧稳定，但手工关键帧像身体图层平移，路线弃用。 |
| 19 | 通过 | 0.34 独立实例和 `MiniMaxH3AddGuide` 接口可用，主实例未覆盖。 |
| 20 | 通过 | H3 原生首尾锚定 73 帧闭环稳定，闭眼阶段偏长。 |
| 21 | 上限已定位 | 39/56/73 帧通过；90 帧在 CreateVideo 达到 31.11GiB 后中断。日常推荐 56 帧，73 帧为边界档。 |
| 22 | 部分通过 | 逐帧落盘 + 外部流式编码跑通到 73 帧且峰值更低；90 帧仍中断，瓶颈从 CreateVideo 移到 VAEDecode+ImageScale。 |

## 3. 环境快照

### 3.1 主实例

- 服务：`http://127.0.0.1:8188`，只监听回环地址。
- 部署：Comfy Desktop `local-desktop2-standalone`。
- 根目录：`D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI`。
- 共享模型：`D:\Comfy-Desktop\ComfyUI-Shared\models`。
- ComfyUI：0.33.1，commit `72865f4f27eaf5396f8f36370e0a2be3a9a090ee`。
- Python 3.13.12；PyTorch 2.10.0+cu130；`cudaMallocAsync`。
- GPU：RTX 5080 16GB，驱动 591.86，compute capability 12.0。
- 系统内存：31.11GiB。

原有自定义节点包括 `ComfyUI_essentials`、`ComfyUI-Easy-Use`、`ComfyUI-KJNodes`、`comfyui-krea2edit` 和 `rgthree-comfy`，实施过程没有覆盖这些目录。

### 3.2 0.34 测试实例

- 名称：`ComfyUI H3 0.34 Test`。
- API：`http://127.0.0.1:8189`。
- Desktop 卡片：`v0.34.2+16`；仓库 commit `8a33128f2f8c5585c57486c07de481241e70a39c`；运行核心报告 0.34.0。
- 独立 Python 3.13.12 / PyTorch 2.12.1+cu130。
- 共享现有约 53GB 模型，没有复制权重。
- `/object_info/MiniMaxH3AddGuide` 返回成功；节点支持把单图、短视频、音频或带音轨片段锚定到任意 `frame_idx`，也允许串联多个引导节点。
- 没有整批迁移旧实例的第三方插件，避免兼容性污染。

## 4. 模型与来源核验

### 4.1 FL2VA 最小模型集

| 文件 | 字节数 | SHA-256 |
|---|---:|---|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 20,970,379,616 | `e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a` |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 15,687,142,551 | `35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6` |
| `minimax_h3_video_vae_fp16.safetensors` | 5,207,808,496 | `7c1f131492e7eddacaac9069a61b81bdd39de5cc96561e677c5eab1cdce5e522` |
| `minimax_h3_audio_vae_fp32.safetensors` | 605,254,808 | `8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48` |

四个文件从 ModelScope 下载，先写 `.part`，完成大小与 SHA-256 校验后原子改名。ModelScope、HF-Mirror 和经 `127.0.0.1:9567` 代理的官方 Hugging Face 均验证支持 Range；镜像与官方源的字节数及 ETag 一致。

### 4.2 LoRA 与多模态投影

| 文件 | 字节数 | SHA-256 | 用途 |
|---|---:|---|---|
| `HMNSFW-AIO-V2.5.safetensors` | 86,040,232 | `a07732a84fd733085eb5d910f602f918fa7a3658117116927e4329f5951a9d2d` | H3 运动/可选图像适配器 |
| `minimax_h3_turbo_v4_step600_ema.safetensors` | 779,849,816 | `5f3a626cd72c93a8b9318d6760c510bc5092d2ab13aaba1f932c5bab07a416d3` | 4/8 步预览 |
| `Qwen3.6-35B-A3B-mmproj-BF16.gguf` | 902,822,240 | `1c625f05cd52e90abc76a5f756226c3a5fe279593379c22f6c6846c970a0cd18` | Qwen3.6 视觉投影 |

HMNSFW V2.5 来自 `Hearmeman/minimax-h3-loras`，模型头包含 200 个 `diffusion_model.blocks.*.lora_A/B` 张量，元数据为 `ss_base_model_version=minimax_h3`。它用原生 `LoraLoaderModelOnly` 加载，不需要专用节点。作者建议 0.5–0.9，但在量化模型上应从低端开始逐 seed A/B，不能把作者模型卡中的训练数据与效果声明当作独立基准。

Turbo 节点发布版 v1.2.3、commit `4274783a23afcfdbea3b4876cb79effd6c510785` 已审计；没有额外依赖、网络下载、子进程或动态执行行为。审计副本保留在 `vendor_audit/ComfyUI-MiniMax-H3-Turbo`。

## 5. 基线、LoRA 与微动画固化（步骤 5–7）

### 5.1 官方 I2V 基线

固定条件：1024×576、73 帧、24fps、20 步、`res_multistep/simple`、无 LoRA。

| seed | 总耗时 | VRAM 峰值 | RAM 峰值 | 输出 |
|---:|---:|---:|---:|---:|
| 2026082901 | 125.77 秒 | 15.47GiB | 29.58GiB | 362,692 B |
| 2026082902 | 115.33 秒 | 15.71GiB | 29.63GiB | 356,600 B |

两次均完整解码 73 帧，无 OOM、黑帧、噪声、音画错误或持续内存增长。身份、服装、配件和手办材质基本稳定，但动作幅度比目标微动画偏大。

### 5.2 HMNSFW 0/0.5 A/B

同一输入、提示、seed 2026082901：

| 组别 | 耗时 | VRAM | RAM | 结果 |
|---|---:|---:|---:|---|
| 强度 0 | 114.92 秒 | 15.29GiB | 29.37GiB | 日志显示 0 patches |
| 强度 0.5 | 109.70 秒 | 15.35GiB | 29.48GiB | 日志显示 100 patches |

两组同帧平均绝对差 6.57/255，证明 LoRA 确实改变结果。0.5 组保留眨眼且整体姿态漂移更小，未产生不可接受的脸、服装、配件或材质退化，因此 0.5 成为后续默认运动强度。

### 5.3 三档微动画

| 档位 | 规格 | 用途 |
|---|---|---|
| `draft` | 1024×576×73，20 步 | 标准质量复核 |
| `long_draft` | 864×480×124，20 步 | 先检查 5.17 秒眨眼与末帧状态 |
| `final` | 1344×768×124，20 步 | 串行生成最终母版 |

4 个 seed 均成功；2026082901 和 2026082904 达到可用线，后者末帧整体漂移为 7.00，约为其余组的一半。普通 I2V 保留完整眨眼，成为主路线。旧实例的同图首尾约束能把末帧漂移降到 1.87，但运动量也下降约三分之二，因此只作极静备选。

1344×768×124 成片实测 620.2 秒，峰值 VRAM 14.67GiB、RAM 30.40GiB。该样片后半段闭眼后未在末帧前睁开，说明成片前必须先过 `long_draft`，不能仅凭 73 帧草稿判断长时行为。

## 6. 循环、性能和 4K（步骤 8–10）

### 6.1 静音循环

对 seed 2026082904 比较 6、9、12 帧线性光交叉融合；12 帧的编码后边界 MAD 最低：1.965，而原始首尾直接相接为 7.000。

最终样片：H.264 High、yuv420p、1024×576、24fps、61 帧、2.542 秒、fast-start、无音轨、CRF 18 / slow / animation。文件 SHA-256 为 `4a379dea793dbe9959ce2b26c6d68d5efe310ae2f6141e802d9952a8e1d78de6`。

5 分钟验证实际重复解码 119 轮、7259 帧、302.458 秒；PTS 错误、黑帧和解码不一致均为 0。

### 6.2 Turbo

固定 1024×576×73、seed 2026082904、HMNSFW 0.5：

| 档位 | 耗时 | 相对 20 步 | VRAM | RAM | 决策 |
|---|---:|---:|---:|---:|---|
| Turbo 8 步 | 72.8 秒 | 快 38.7% | 14.99GiB | 29.41GiB | 可选细节预览 |
| Turbo 4 步 | 36.3 秒 | 快 69.4% | 14.19GiB | 29.60GiB | 默认 seed 预筛 |
| 标准 20 步 | 约 119 秒 | 基线 | 接近 15GiB | 接近 29.5GiB | 最终质量 |

两档 Turbo 都完整解码 73 帧并保留身份与眨眼，但循环边界漂移高于标准 20 步，且没有显著降低系统 RAM。因此 Turbo 只负责排序 seed，不替代最终母版。

### 6.3 4K 两路线

Run ID：`20260829T021812Z-38ce`。两条路线均输出 3840×2160、24fps、61 帧、静音 H.264，并完成 119 轮重复解码。隔离目录重跑与冻结基线逐字节一致。

| 指标 | Lanczos `temporal_safe` | RealESRGAN `ai_detail_default` |
|---|---:|---:|
| 生成时间 | 5.57 秒 | 62.27 秒 |
| 峰值 RAM | 11.19GiB | 12.48GiB |
| GPU | 不使用 | 分配峰值 1.16GiB，整卡约 3.04GiB |
| 循环边界 MAD | 2.0748 | 2.1512 |
| 结构锐度 | 2.8347 | 3.0695 |
| 静态区域纹理爬行 | 0.1216 | 0.1638 |
| 时序残差 mean / p95 | 0.3161 / 0.4552 | 0.4769 / 0.7130 |
| 运动放大 | 1.0001 | 1.1457 |

RealESRGAN 以约 1.35 倍纹理爬行和 1.51 倍时序残差换取 8.3% 结构锐度，交换比不成立。默认保持 `temporal_safe`；AI 档保留给静态细节收益明显且人工动态观看确认无闪烁的场景。唯一未完成项是用户在正常速度连续循环下进行人工动态复核。

## 7. 输入图接口与标准作业（步骤 11）

`scripts/h3_input_common.ps1` 为标准和 Turbo 运行器提供统一输入解析：

- input 内相对文件名或任意绝对路径均可；
- 外部文件安全发布到 ComfyUI input，同名同 SHA-256 复用，同名不同内容拒绝；
- 支持 PNG/JPEG/WebP/BMP；
- 提交前通过 `/object_info/LoadImage` 确认 ComfyUI 可见；
- 使用 UTF-8 payload，中文文件名实跑通过；
- 输出名包含输入图片标识，避免不同输入互相覆盖。

接口验证使用 1024×1536 中文文件名图片、Turbo 4 步、seed 2026082910：42.3 秒，峰值 VRAM 15.52GiB、RAM 29.52GiB，73 帧完整输出。文件缺失、扩展名不支持和同名不同哈希均在提交前正确拒绝。

换图后的顺序固定为：Turbo 预筛 5–8 个 seed → draft 复核前两名 → long_draft 检查完整时间行为 → final 母版 → 12 帧交叉融合 → 5 分钟验证 → 可选 4K。每张新图都必须重新筛 seed。

## 8. 伪 T2I、成人链路与三段 UI（步骤 12–14）

### 8.1 H3 伪 T2I 与端到端链路

H3 没有原生单图 latent。本项目使用 5 帧最短时序包，经 Video VAE 解码后由 `ImageFromBatch` 抽取 frame 0；不安装第三方 Image Studio 节点。

独立首图：1024×576、5 帧、20 步、seed 2026083003，暖缓存 18.3 秒，峰值 VRAM 15.68GiB、RAM 29.41GiB。5 帧均有效，frame 0 边缘能量最高 7.663。

文本到 Live2D：image/video seed 2026083003/2026082904，HMNSFW motion 0.5，总耗时 108.7 秒，峰值 VRAM 15.28GiB、RAM 29.48GiB；73/73 帧，黑帧 0，末帧整体/主体/背景漂移 2.654/4.677/0.747。归档视频 SHA-256：`932afb31f6abac3e5557d0a4f2e35fa04e8b09ba9d89224d0502b9fbe611b04c`。

### 8.2 明确成年内容的技术验证

验证范围限定为明确 30+ 的虚构成年人、无性行为的裸体手办展示；默认安全工作流没有改成成人提示，必须显式提供成年描述。

固定 1024×576、5 帧、20 步、seed 2026083013：

| 指标 | 基础 H3 | 图像 HMNSFW 0.3 |
|---|---:|---:|
| 耗时 | 24.2 秒 | 20.2 秒 |
| VRAM / RAM | 15.72 / 29.10GiB | 15.49 / 29.09GiB |
| frame 0 边缘能量 | 5.0185 | 5.5237 |
| frame 0→4 MAD | 9.0849 | 9.6590 |

两组均成功，没有内容替换、自动遮挡、黑帧或 OOM。基础 H3 已能响应明确成年提示，HMNSFW 不是静态图的必要条件；0.3 会改变构图和细节，但不能凭一个 seed 断言质量普遍更高。

端到端 image LoRA 0.3 + motion LoRA 0.5、video seed 2026083014 成功输出 73 帧，耗时 125.2 秒，峰值 VRAM 15.66GiB、RAM 29.42GiB。背景首尾 MAD 0.833，但主体 MAD 21.487，人物明显前移/放大；链路可行性通过，微动画锁姿失败，样片不可直接作为循环母版。

早期让强度 0 的数据仍经过 LoRA loader 时出现 `hostbuf_file_reader_read failed`。这不是内容审核；将 0 强度改为真正绕过 loader 并释放缓存后恢复，修复已固化到两个运行器。

### 8.3 ComfyUI 三阶段 UI

三套 UI 工作流均从侧栏加载成功，无 missing node：

| 阶段 | 耗时 | VRAM | RAM | 输出 |
|---|---:|---:|---:|---|
| 01 文生图 | 10.1 秒（暖缓存） | 15.45GiB | 29.08GiB | 5 帧预览 + 1 PNG |
| 02 图生视频 | 103.1 秒 | 14.15GiB | 29.41GiB | 1024×576、73 帧、静音 |
| 03 AI 4K | 60.5 秒 | 2.92GiB | 25.61GiB | 3840×2160、73 帧、静音 |

曾测试 ComfyUI 整批 Lanczos 放大 73 帧，虽然成功但 RAM 达 31.11GiB，因此从最终 UI 删除。时序安全 Lanczos 保留为外部逐帧流式路线；UI 只保留 RealESRGAN `per_batch=1`。

## 9. Qwen3.6 双语导演与参考图（步骤 15–16）

节点复用 LM Studio 的 `lms.exe` 和已有 Qwen3.6 35B A3B NVFP4 GGUF，不安装 `llama-cpp-python`，不复制 21.5GiB 主权重。输出不是逐句翻译，而是结构化补全后分别给出中文检查版和英文 H3 执行版；I2V 英文强制以 `hmmotion. ` 开头。

初版默认 50% GPU 卸载；60% 在桌面显存占用波动时出现 `failed to allocate compute pp buffers`。加入视觉投影后，完整双图在 30% 也曾启动失败，无图 50% 也曾失败，因此当前统一稳定默认降为 20%，并保留原值 → 30% → 20% 自动回退。

T2I UI 实测：模型加载 14.2 秒，总耗时 35.6 秒，402 token、21.60 tok/s；I2V API 实测加载 11.1 秒，总耗时 25.7 秒。两次结束后 `lms ps --json=[]`。

四参考图规则：只有真实图片且对应说明非空时才进入 LLM；1×1 占位图、空说明、只有说明但没图均跳过。参考图先转质量 90 JPEG，最长边默认 1024。双图融合测试耗时 81.1 秒、223 token、14.83 tok/s，正确提取指定的背景光影、黑金配色和表面雕刻，没有复制被明确排除的主体。

新版前端曾因手写 UI JSON 缺少 widget 名称映射而误报未选图、越界和类型错误。生成器补齐 `image/upload` 和 `widgets_values_named` 后，无图 UI 正式提交通过。

## 10. 风格、关键帧与原生引导（步骤 17–20）

### 10.1 实时二游 CG + MMD 风格与 2K

默认文生图方向从实体树脂/PVC手办调整为当前世代实时二游 PBR + 高质量 MMD 干净角色照明：自然哑光皮肤、轻微 SSS 与粗糙度变化，并区分丝袜、皮肤、头发、漆面鞋和金属饰件的材质语言。第一次斜构图 A/B 被 H3 放大成近 90° 倾斜，已删除；`softbox/light panel` 会被画成发光板，最终改用环境光、天空补光、湿地反弹和冷暖轮廓光。

后处理链为 RealESRGAN x4plus 修复局部 → Lanczos 无裁剪缩放 2560×1440，同时保留原图。固定 1024×576、5 帧、20 步、seed 2026083013、HMNSFW 0.30 的完整 T2I + 2K 链耗时 24.3 秒，峰值 VRAM 14.79GiB、RAM 29.45GiB，无 OOM。技术链通过，但风格结论是一次视觉方向迭代，不应当作通用质量基准。

### 10.2 RIFE 技术通过但视觉失败

使用可信参考图构造 7 张 1920×1080 闭环关键帧，以官方 RIFE v4.26 做 4× 插帧，删除重复终点后得到 24 帧、1 秒 H.264 视频。节点执行约 1.85 秒；连续解码 6 轮、144 帧，PTS 错误、黑帧和校验差异均为 0；首尾边界 MAD 1.0909。

用户视觉复核确认结果像“头部和背景固定，身体作为独立图层晃动”，因此视觉失败。Krea2 Identity Edit 的脸部 `ref_boost=1.35` 明显重画人物，全图 `ref_boost=4.0` 仍改变双马尾、裙摆、腿和剑，不能作为相邻关键帧。RIFE 只会插值，不会修复错误关键帧，该路线停止。

### 10.3 原生首尾锚定

0.34 实例用同一张 `keqing_gpt_reference_16x9.png` 锚定首尾，固定 1024×576、73 帧、24fps、20 步、seed 2026083019、HMNSFW 0.5、静音：

- 132.8 秒成功；峰值 VRAM 13.47GiB、RAM 29.80GiB；
- 73/73 帧、黑帧 0；
- 相邻帧 MAD 均值 0.4601、P95 1.2456；
- 首尾全图/主体/背景 MAD 3.1725/4.1233/2.2762；
- 身份、脸型和紫红瞳色稳定，头、肩、双马尾、裙摆和雷光呈连续整体运动，没有复现图层平移。

不足是闭眼覆盖约中间一半视频。后续应写 `one quick blink lasting only a few frames` 并继续筛 seed，而不是加入未经验证的重绘关键帧。

## 11. 原生 1080p（步骤 21）

把 H3 节点直接设为 1920×1080 会因空间 patch 对齐在采样前产生形状错误，并非 OOM。正确链路是内部 1920×1088 → VAE 解码 → Lanczos 无裁剪缩放 1920×1080，竖向仅压缩 8 像素（约 0.74%）。

固定 20 步、HMNSFW 0.5、24fps、单首帧、无末帧锚定、无音频。2026-08-30 使用同一输入、seed `2026083022` 和统一监控继续按 H3 合法帧长上探：

| 测试 | 耗时 | VRAM | RAM | 结果 |
|---|---:|---:|---:|---|
| 5 帧烟测 | 60.8 秒 | 15.25GiB | 29.38GiB | 成功 |
| 22 帧短片 | 173.2 秒 | 14.68GiB | 29.69GiB | 成功 |
| 39 帧 | 357.5 秒 | 13.04GiB | 30.08GiB | 成功；39/39、黑帧 0 |
| 56 帧 | 590.4 秒 | 12.98GiB | 30.43GiB | 成功；56/56、黑帧 0 |
| 73 帧 | 874.3 秒 | 12.73GiB | 30.58GiB | 成功；73/73、黑帧 0 |
| 90 帧 | 1190.5 秒后中断 | 12.96GiB | 31.11GiB | `CreateVideo` 触发 31.0GiB 熔断，无输出 |

22 帧文件为 H.264、1920×1080、24fps、无音频、黑帧 0；相邻 MAD 均值 0.882，背景首尾 MAD 1.062。39/56/73 帧也均为 H.264、1920×1080、24fps、仅视频流并逐帧解码通过；相邻 MAD 均值分别为 0.702、0.379、0.812，黑帧均为 0。

完成样片 SHA-256：39 帧 `6306C3A50C60CCBD7597D615B4691C0B03236364D4E2748D7BCCD469B4A05BC2`；56 帧 `B1B02A7573A9A7B15F7A94AABFD0D65EC9D100AF61FD4685D1B90BED42CE5F80`；73 帧 `AEEB2FA910F0C6CDB0344C1B5C20FFB504573BEEA69C509DFC8430212B1A3D64`。

首次 39 帧测试在 RAM 30.59GiB 时被原 30.5GiB 熔断中止，ComfyUI 历史显示已执行采样、VAE 解码和缩放，正在 `CreateVideo`。释放缓存并把受控阈值改为 31.0GiB 后，同一配置以 30.08GiB 完成，说明后台基线和短暂采样误差会影响约 0.5GiB，单次旧峰值不能直接外推帧数上限。

90 帧同样完成了扩散、VAE 解码和 1920×1080 缩放，只在 `CreateVideo` 整批编码时达到 31.11GiB 并被中断。因此：

- **保守档：39 帧**，适合无法完全清理后台时使用；
- **日常推荐上限：56 帧 / 2.33 秒**，本次峰值 30.43GiB；
- **可完成边界：73 帧 / 3.04 秒**，峰值 30.58GiB，只剩约 0.53GiB，不适合无人值守；
- **现有整批输出管线的首次失败：90 帧 / 3.75 秒**；107/124 帧因此未继续执行。

超过 73 帧应把 `CreateVideo` 改为逐帧落盘后外部流式编码，或使用低分辨率母版再超分；不应取消熔断依赖页面文件硬撑。该改造已在步骤 22 实施，结论见下一节；具体交付物、阶段门槛和回滚规则见 [H3 1080p 逐帧输出与流式编码实施计划](plans/H3_1080_STREAMING_OUTPUT_PLAN.md)。

## 12. 逐帧输出与外部流式编码（步骤 22）

改造把末端从「整批帧交给 `CreateVideo`」换成「节点 20 `SaveImage` 按运行 ID 逐帧写 PNG → 释放模型 → 外部 PyAV/libx264 顺序读图编码 → 验收后原子发布」。模型、采样器、提示词、输入图、seed、LoRA 和内部尺寸全部不变，因此数值与步骤 21 直接可比。

| 档位 | 帧 | 生成耗时 | 生成峰值 RAM | 步骤 21 同帧数 | 编码峰值 | 最差阶段余量 | 结果 |
|---|---:|---:|---:|---:|---:|---:|---|
| 5 帧 | 5/5 | 62.9 秒 | 29.06GiB | 29.38GiB | 9.26GiB | 2.05GiB | 通过 |
| 22 帧 | 22/22 | 166.1 秒 | 29.11GiB | 29.69GiB | 9.72GiB | 2.00GiB | 通过 |
| 73 帧 | 73/73 | 837.1 秒 | 30.18GiB | 30.58GiB | 6.94GiB | 0.93GiB | 通过 |
| 90 帧 | 0/90 | 1152.6 秒后中断 | 31.02GiB | 31.11GiB（中断） | — | 0.09GiB | 中断 |

三档成片均为 H.264 High、1920×1080、24fps、`yuv420p`、CRF 18、`slow`/`animation`、fast-start、仅视频流，黑帧 0，PNG 编号 1..N 连续。与源 PNG 的保真度基线：5/22/73 帧 luma PSNR 分别 40.69/40.93/41.48dB，RGB PSNR 37.59/38.15/38.37dB，MAD 2.3416/2.2316/2.1308。73 帧成片 SHA-256 `e5115e76f80b2ef0708b2c48e978bcc4098193602c529609ee92079e98853967`。

三个内存阶段现在分开读数（73 帧）：采样+解码+缩放 827.0 秒、峰值 30.18GiB；逐帧落盘 10.1 秒、峰值 27.89GiB（**低于**上一阶段，说明 `SaveImage` 不产生批量副本）；外部编码 3.6 秒、峰值 6.94GiB、进程 RSS 仅 0.48GiB、全程增长 0.231GiB。编码峰值在 5/22/73 帧随机器基线波动而非随帧数上升，这是整批 `CreateVideo` 不具备的性质。

90 帧的失败位置由 576 个采样点定死：1111 秒 VRAM 从 3.74 跳到 11.30GiB（`VAEDecode` 开始），1123→1141 秒 RAM 从 29.73 升到 30.14GiB（1920×1088 批次入内存），1143→1149 秒 30.47→30.91→31.02GiB 触发熔断，落盘帧为 0。因此瓶颈是节点 12 的 1920×1088 批次与节点 19 的 1920×1080 批次同时驻留（90 帧两批约 4.18GiB），缺口约 1.5–2GiB。去掉 `CreateVideo` 是必要的但不充分。

三条执行期结论值得单独记住：

- **同 seed 不保证跨会话拿到同一条母版。** 同会话同参数重跑 bit 级相同（5 帧连跑两次成片 SHA-256 一致，PNG 像素 MAD 0.0000），但与步骤 21 归档样片逐帧对比显示轨迹分叉：首帧 33.15dB，第 8 帧 26.53dB，第 32 帧后稳定在约 22.6dB / MAD 7.6。编码损耗不会随帧号递增。最可能原因是内存压力驱动的权重卸载与后端选择在不同空闲内存下作出不同决策。已归档样片无法从新会话按字节复现，换机器或重启实例后母版需重新人工复核。
- **峰值 RAM 与后台基线基本无关。** 四次运行空闲基线在 5.88–11.00GiB 之间，采样平台始终停在 28.3–29.5GiB。ComfyUI 0.34 的 `RAM_PRESSURE` 缓存按物理内存自适应，腾出的后台内存被它拿去多缓存，不会变成末端余量。「关掉后台程序」不是让 90 帧通过的手段。
- **节点 17 的 `crop` 是决定性参数。** 基础工作流默认 `center`，而 1080p 档位的运行器会强制 `disabled`；复制工作流时漏掉这一步会改变首帧，同一个 seed 走出不同轨迹。定位方式是从旧成片取出 ComfyUI 嵌入的 workflow 元数据逐节点 diff。现已在两处统一为 `disabled`，并把该字段写入运行报告。

熔断保护也在本步骤补强。原先熔断只存在于监控进程里，运行器被杀后 ComfyUI 会继续执行且无任何看守（执行期间实际发生过一次，RAM 停在 29.21GiB）。现在运行器的监控循环包在 `try/finally` 内覆盖正常退出、异常与 Ctrl+C，硬杀场景由 `scripts/h3_stream_watchdog.ps1` 兜住，并已用 `Stop-Process -Force` 实测验证中断生效。

## 13. 关键产物索引

| 类型 | 项目内文件 |
|---|---|
| API 工作流 | `workflows/*.json` |
| UI 工作流 | `workflows/ui/*.json` |
| Live2D 档位 | `presets/minimax_h3_live2d_profiles.json` |
| Turbo 档位 | `presets/minimax_h3_performance_profiles.json` |
| T2I 档位 | `presets/minimax_h3_t2i_profiles.json` |
| 4K 档位与门槛 | `presets/wallpaper_4k_profiles.json` |
| 循环成品 | `outputs/wallpaper/` |
| 4K 成品与 Run 报告 | `outputs/wallpaper4k/`、`outputs/performance/step10/` |
| T2I 与文本到视频 | `outputs/t2i/`、`outputs/text_to_live2d/` |
| 成人链路 A/B | `outputs/nsfw_t2i_ab/` |
| RIFE 反例 | `outputs/keqing_keyframe_vfi_test/` |
| 原生闭环证据 | `outputs/keqing_reference_test/` |
| 1080p 指标、运行报告与抽帧 | `artifacts/h3_1080_short_*`、`artifacts/h3_1080_probe_*` |
| 1080p 逐帧流式证据 | `artifacts/h3_1080_stream_*`、`outputs/h3_1080_stream/` |

## 14. 合规与安全边界

本地权重不经过云端逐请求审核，不等于许可证或法律允许。H3 Community License、Acceptable Use Policy、内容标识要求、著作权、肖像、隐私和当地内容法律仍然适用。

项目验证成人题材时限定为明确成年、虚构、自愿的角色设定；排除未成年人或年龄含混外观、真实人物换脸、未经同意的肖像/声音、胁迫和伤害。不要把 ComfyUI API 或无鉴权分享链接暴露到公网。公开传播或商业化前必须重新核对当时有效的许可证、平台规则与当地法律；本文件不是法律意见。

## 15. 尚待人工或后续验证

- 正常播放速度下复看 4K 连续循环，重点观察躯干、服装和底座的纹理爬行、轮廓呼吸和边界脉冲。
- 对每张新输入图按完整标准作业筛 seed；历史最佳 seed 不应跨角色复用。
- 成人链路固定首图后重新筛 video seed，降低主体首尾漂移。
- 原生首尾闭环重新筛短眨眼 seed，或增加经验证的中间锚点。
- 逐帧流式的 5/22/73 帧成片仍需一次人工动态观看确认。
- 1080p 循环方式已锁定为镜像回放（73 帧 → 144 帧 / 6 秒）。提示词改为单向走到极值，编码与筛选已支持 `--loop-mode mirror`。下一步是用新提示词做 576p 73 帧 seed 筛选，前两名再上 1080p。旧 `1080_stream_73` 样片不可作母版。外部 VFI 调研结论：不引入 FILM/GIMM-VFI，RIFE 4.26 仅作为人工通过后的可选后处理。详见 [H3 1080p 循环方案](plans/H3_1080_LOOP_STRATEGY_NOTES.md)。
- 要突破 90 帧原生 1080p，必须处理解码+缩放阶段的双批次驻留：时间维分块解码（根治）、把 1088→1080 缩放移出 ComfyUI（省约 2.08GiB，但缩放实现变更）、或降低内部生成分辨率（等于放大，与 4K 路线重叠）。仅去掉 `CreateVideo` 已证明不够。

## 16. 历史调研来源

以下链接是 2026-08-29 调研时使用的依据；后续版本、许可证和法规可能变化，实际部署前应重新核对：

- [MiniMax H3 官方模型卡](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/README.md)
- [MiniMax H3 Community License](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE)
- [Comfy-Org H3 权重与官方工作流](https://huggingface.co/Comfy-Org/MiniMax-H3/blob/main/README.md)
- [Hugging Face Diffusers：H3 推理说明](https://huggingface.co/docs/diffusers/main/en/api/pipelines/minimax_h3)
- [Hearmeman MiniMax-H3 LoRA 模型卡](https://huggingface.co/Hearmeman/minimax-h3-loras?not-for-all-audiences=true)
- [NVIDIA RTX 5080 官方规格](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5080/)
- [RTX 5080 + 32GB 社区 H3 实测](https://note.com/tnsor_works/n/n5405bf0154d9)
- [ComfyUI H3 SageAttention 纯噪声 issue](https://github.com/Comfy-Org/ComfyUI/issues/15263)
- [中国《生成式人工智能服务管理暂行办法》](https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm)
- [AI 生成合成内容标识办法与国家标准](https://www.miit.gov.cn/xwfb/mtbd/wzbd/art/2025/art_5e46c60f9a714fdb584eb139f476ce9.html)
- [互联网淫秽电子信息案件司法解释（二）](https://www.court.gov.cn/zixun/xiangqing/302.html)
