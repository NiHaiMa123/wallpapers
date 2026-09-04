# 09 Artifacts & Reports Contract

## Purpose

保证所有人工选择、生成阶段和后处理都可追溯、不可被静默覆盖，并让主 Agent 能仅根据 manifests/reports 判断一个产物来自哪条生产链。

## Immutability

以下产物默认不可覆盖：

- 用户输入及仓库复制的输入；
- Director Brief；
- prompt 文件；
- T2I 候选；
- low-res seed candidates；
- 1080p takes；
- 1080p canonical PNG frame sequence；
- human keep-list manifest；
- rebuilt sequence；
- RIFE output；
- upscale output；
- run reports / validation reports；
- 失败样片和失败报告。

同路径已存在时，生产实现应拒绝覆盖或自动生成新的唯一 RunId/文件名。

## Run identity

每次实际执行必须有唯一 `run_id`。一个 run report 只能描述一次具体执行，不允许后续把不同参数的重跑追加成同一个“成功记录”。

## Required hashes

适用时至少记录：

- input SHA-256；
- prompt SHA-256；
- selected image SHA-256；
- selected 1080p take SHA-256；
- frame manifest hash；
- human selection manifest hash；
- intermediate/final output SHA-256。

## Human decisions are first-class artifacts

人工 Gate 不能只存在聊天记忆里。Gate A/B/C/D 的最终选择必须写入可持久化 manifest/report，且区分：

```text
agent_recommendation
user_selection
```

Agent 不得把推荐值复制到 `user_selection` 字段冒充用户已批准。

## Minimum final trace

最终交付必须可以追溯：

```text
Director Brief
-> T2I prompt
-> selected image
-> motion brief/prompt
-> selected video seed
-> selected 1080p take
-> canonical frame sequence
-> user keep list
-> rebuilt sequence
-> interpolation run
-> upscale run
-> final validation
-> final output
```

## Report truthfulness

- 计划中的命令不得写成已运行；
- runner exit 0 只代表执行成功，不代表视觉 PASS；
- `screening_only` 产物不得标为 master；
- 自动分析建议不得标为人工决定；
- 如果存在 known defect，必须保留在最终报告，不因后续技术 PASS 自动删除。

## Recommended logical artifact classes

具体目录可以由实现调整，但语义至少区分：

```text
inputs
briefs/prompts
candidates
takes
frames
human_manifests
masters
postprocess
review_evidence
run_reports
validation_reports
finals
```

如果实现使用不同目录名，只要 manifest 能明确标识 artifact class 即符合 Contract。