# 02 环境预检

任何实际生成前都执行本阶段。规划和提示词请求不调用 ComfyUI。

## API 与队列

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8188/system_stats'
Invoke-RestMethod -Uri 'http://127.0.0.1:8188/queue'
```

记录：ComfyUI 版本、RAM 总量与空闲量、GPU/VRAM、`queue_running` 和 `queue_pending`。

通过条件：API 可达，队列为空，且没有 Qwen、第二个 H3 或本地大模型占用冲突资源。

队列已空但空闲 RAM 仍接近 `31.0GiB` 熔断时，视为上次任务没有卸载模型。先释放再提交：

```powershell
$body = '{"unload_models":true,"free_memory":true}'
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8188/free' -ContentType 'application/json' -Body $body
```

`/free` 只是排队标志，要等到 `system_stats` 的 RAM/VRAM 降下来并稳定后再继续。这次实跑释放前约 28.6GiB，释放后约 10.5GiB。

## 输入检查

1. 使用绝对路径确认文件存在。
2. 读取尺寸、格式、大小和 SHA-256。
3. 实际查看图片，记录主体、脸、手、道具、易误识别结构、背景动态元素和构图比例。
4. 竖图或非 16:9 图要先说明裁切风险；不要默默改变构图。

外部图片由运行脚本安全发布到 ComfyUI input：同名同哈希复用，同名不同哈希拒绝覆盖。staging 目标必须是当前 serving 实例的输入目录（当前 `D:\Comfy-Desktop\ComfyUI-Shared\input`）；提交若报 400/`Invalid video file`，先读该实例 `logs/comfyui.log` 的服务端确切原因，不要反复重送。

## 版本与节点检查

- 常规 I2V 以 runner 实际工作流所需节点为准。
- 原生 1080p runner 会检查 ComfyUI `0.34`，不要只凭端口推断版本。
- 提交前可从工作流 JSON 收集 `class_type`，与 `/object_info` 比对。
- Turbo 需要 `MiniMaxH3TurboLoRA`。如果缺失，不安装节点；转入标准 `draft` 小规模 seed 筛选。
- 标准 `run_h3_live2d_profile.ps1` 的核心依赖必须全部存在，否则状态为 `BLOCKED`。

## 安全检查

- 保留 `AbortRamGiB=31.0`，除非特定已验证 runner/preset 明确采用更低边界。
- 静音任务必须传 `-Silent`。
- 检查输出和报告目标不存在，拒绝覆盖。
- 确认只会提交一个任务。
- 最终 1344×768×124 帧在 32GB 机器上接近物理极限；运行前关闭其他重负载程序。

## 产物

```text
api_reachable:
comfyui_version:
queue_running:
queue_pending:
input_exists:
input_sha256:
required_nodes_missing:
ram_headroom:
safe_to_submit:
fallback_if_needed:
```

## 晋级条件

`safe_to_submit=true`。任何未知缺节点、忙队列、输入缺失或内存余量不足都不得进入生成。
