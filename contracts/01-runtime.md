# 01 Runtime / ComfyUI Execution Contract

## Purpose

定义任何实际生成或高占用后处理在提交前必须满足的运行条件。端口、安装路径和当前实现细节不是永久规范。

## Inputs

```text
stage
api_endpoint
required_capabilities
input_artifacts
target_output
resource_policy
```

## Required invariants

- 实际服务必须可达，并读取 **实际 ComfyUI 版本**；不得只根据端口推断实例身份。
- 提交前确认队列状态，不在已有生产任务上叠加第二个高占用任务。
- 必须确认当前阶段需要的 node/model/capability 存在。
- 输入文件必须存在，并记录路径、尺寸/媒体信息和 SHA-256（适用时）。
- ComfyUI / H3 / RIFE / AI upscale 等高占用任务严格串行。
- H3 生产任务运行时不同时驻留不必要的 Qwen、本地 LLM、第二个 H3 或其他重负载。
- 默认 RAM abort policy 为 `31.0 GiB`；这是当前生产保护线，不等于硬件物理上限。
- 输出、帧目录和报告必须使用唯一名称；不得覆盖已有证据。
- 运行结束后应释放不再需要的模型/缓存，尤其在下一阶段仍需要大量 RAM 时。

## Allowed implementation freedom

实现可以：

- 使用不同端口；
- 使用不同安装路径；
- 通过 PowerShell、Python 或其他可审计方式调用 ComfyUI API；
- 对不同 ComfyUI 版本采用不同已验证 workflow 表达。

前提是能力和输出契约不变，并在 run report 中记录真实环境。

## Forbidden behavior

- 把 `8188` 永久等同某个版本；
- 把 `8189` 永久等同某个版本；
- 因某次边界实验成功就自动提高 RAM abort；
- 在未知队列状态下重复提交；
- 缺节点时自动安装；
- 使用未验证 workflow 代替生产 workflow 而不进入 Contract Review / 用户授权流程。

## Outputs / Evidence

每次实际运行至少记录：

```yaml
api_endpoint:
comfyui_version:
queue_state_before_submit:
required_capabilities_checked:
input_sha256:
prompt_sha256:
run_id:
prompt_id:
started_at:
completed_at:
peak_ram_gib:
peak_vram_gib:
ram_abort_gib:
status:
output:
```

## Failure states

- `BLOCKED_RUNTIME_UNREACHABLE`
- `BLOCKED_QUEUE_BUSY`
- `BLOCKED_CAPABILITY_MISSING`
- `BLOCKED_RESOURCE_HEADROOM`
- `INTERRUPTED_RAM_THRESHOLD`
- `EXECUTION_FAILED`

如果失败揭示“现有 Contract 要求实际上无法在目标环境实现”，subagent 应改为 `CONTRACT_REVIEW_REQUIRED` 上报，而不是自行修改生产目标。