# config

本目录存放 **机器相关部署声明**，不定义任何生产规范。

## 文件约定

```text
*.example.yaml   Git 跟踪的模板，含 <PLACEHOLDER>，不含任何真实机器路径
*.local.yaml     本机真实配置，被 .gitignore 排除，永不入库
```

首次使用：复制 `comfyui_shared_models.example.yaml` 为 `comfyui_shared_models.local.yaml`，把 `base_path` 改成当前机器的 ComfyUI 共享目录。

## Agent 规则

- 运行时必须实际探测 ComfyUI 实例的版本、能力与队列（见 `contracts/01-runtime.md`）；
- 本目录任何路径都只是本机部署状态，不是永久规范；
- 换机器时改 `*.local.yaml`，不改 Contract、不改脚本默认值；
- 端口、安装路径、某台机器的峰值内存属于环境事实，不得升级为全局门槛。
