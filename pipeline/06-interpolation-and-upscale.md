# 06 重建、插帧与超分

本阶段只处理 Gate D 已批准的最终帧序列。

执行契约：

- `../contracts/05-frame-sequence-selection.md`
- `../contracts/06-interpolation.md`
- `../contracts/07-upscale.md`
- `../contracts/09-artifacts-and-reports.md`

## 固定阶段顺序

```text
user-approved keep list
  -> rebuild selected sequence
  -> interpolation
  -> upscale
  -> final candidate
```

## 1. 重建

- canonical source 是 Gate C take 的原始帧序列；
- 只使用用户批准的 keep list；
- 保持原始帧顺序；
- 不自动恢复已删除帧；
- 不在重建阶段自动 equalize/remap；
- 生成 rebuilt-sequence manifest 和 hash。

## 2. 插帧

按 `contracts/06-interpolation.md`：

- target fps 必须显式记录；
- 循环任务必须处理 wrap interval；
- 默认只增加中间帧，不偷偷重新分配用户已批准的时间轴；
- 自动 tail compression / arc-length remap / global speed factor 不是默认生产行为；
- 正常速度观看检查鬼影、双影、假溶解和 micro-freeze。

如果需要额外自动变速，必须由主 Agent/用户明确批准为单独策略，不能因为现有脚本有默认参数就自动执行。

## 3. 超分

按 `contracts/07-upscale.md`：

- 保持插帧后已经批准的 fps；
- 不在超分阶段再次插帧/删帧/重定时；
- 默认 temporal-safe；
- AI detail 只有在动态观看无新增时序伪影时才可晋级。

## 产物

至少形成：

```yaml
human_selection_manifest:
rebuilt_sequence:
interpolation_report:
interpolated_output:
upscale_report:
final_candidate:
known_artifacts:
```

## 实现冲突

如果当前 RIFE runner 会默认自动改尾段节奏，或当前 upscale preset 因固定 fps 拒绝已批准输入，不允许反过来修改 pipeline；应进入 `CONTRACT_REVIEW_REQUIRED`，由主 Agent判断修实现还是修改 Contract。

## 晋级

完成候选 -> `07-final-qc-and-delivery.md`。