# 08 故障、回退与 Contract Review

本文件定义当前生产主流程的故障回退。治理规则见 `../contracts/00-governance.md`，runtime 故障见 `../contracts/01-runtime.md`。

## 先分类：内容失败、实现失败、还是规范冲突

### 1. CONTENT_FAILURE

生成/后处理按 Contract 正常执行，但结果质量不合格。

处理：回到最近能改变缺陷的生产阶段。

### 2. IMPLEMENTATION_FAILURE

当前 script/workflow/preset/validator 没有正确实现 Contract。

处理：修实现，不降低 Contract。

### 3. CONTRACT_REVIEW_REQUIRED

实现证据显示 Contract 缺关键事实、内部矛盾，或当前目标本身需要重新设计。

处理：subagent 停止自行修改 normative MD，按 `contracts/00-governance.md` 上报；主 Agent决定：

```text
IMPLEMENTATION_BUG
CONTRACT_GAP
CONTRACT_CHANGE
```

## 通用原则

- 一次只改变一个主要变量；
- 保留失败视频、canonical frames、reports、manifest 和参数；
- 人工 Gate 未完成不是故障；
- 不把历史 plan/validator 的旧默认当作解决当前冲突的依据；
- 不通过降低目标、删 Gate 或放宽 validator 来“消除失败”。

## 生产故障表

| 现象 | 回退/处理 |
|---|---|
| T2I 脸/手/姿势严重错误 | 回 02；必要时回 01 调 Director Brief |
| 静态图漂亮但不适合动画 | 回 01 调遮挡、轮廓和动态预留 |
| 低清 seed 镜头漂移/动作错误 | 换 seed；必要时单轴改 motion prompt |
| 低清执行器缺能力 | runtime block；如 Contract 本身无法表达则 Contract Review |
| 1080p 行为与低清 seed 不同 | 正常重新人审；重抽 take 或回 Gate B |
| 1080p 身份/解剖/武器错误 | 淘汰 take |
| 1080p 尾部降速但主体质量可接受 | 进入 Gate D，不自动 equalize |
| 自动指标与用户观感冲突 | 用户 Gate D 决定为准，指标留作证据 |
| keep list 造成明显位置跳跃 | 警告；用户要改则回 Gate D |
| RIFE 鬼影/假溶解 | 回到人工定稿的未插帧序列 |
| RIFE 实现默认自动改节奏 | IMPLEMENTATION_FAILURE / Contract Review，不接受隐藏默认 |
| 超分新增纹理爬行/halo | 回 temporal-safe 或未超分版本 |
| upscale preset 因 fps 写死拒绝已批准输入 | 实现不合规；修实现或 Contract Review，不自动改 fps |
| validator 写死历史样片规格 | 实现不合规；改为参数化 validator |
| API/队列/资源问题 | 按 Runtime Contract BLOCKED/中断 |
| 实现需要新增关键事实才能重建 | `CONTRACT_REVIEW_REQUIRED` |

## 需要额外授权的操作

以下不能因为“继续方便”自动执行：

- 安装新节点/模型；
- 修改 ComfyUI 安装目录/实例；
- 提高生产 RAM abort；
- 删除/覆盖历史文件；
- 切换未验证生产 workflow；
- 运行负对照/边界实验；
- subagent 自行修改 normative MD 的目标语义。

## Contract Review 上报

至少：

```yaml
status: CONTRACT_REVIEW_REQUIRED
contract_file:
contract_clause:
expected:
observed:
evidence:
impact:
proposal:
alternatives:
implementation_changed: false
```

主 Agent修改 Contract 后，要检查所有受影响 pipeline/contracts/实现/tests；不能只改一处文档留下新矛盾。

## 回退层级

```text
T2I 不合格 -> 01/02
seed 不合格 -> 03
1080p take 不合格 -> 04；必要时 03
尾部时序 -> 05 Gate D
插帧问题 -> 06 interpolation
超分问题 -> 06 upscale
最终 QC -> 最近能改变缺陷的阶段
实现不符合 Contract -> IMPLEMENT / REVIEW
规范本身有问题 -> SPEC_REVIEW
```