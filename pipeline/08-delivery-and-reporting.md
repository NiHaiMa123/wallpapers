# 08 交付与报告

## 推荐目录

```text
inputs/imported/       项目内输入副本；不改原文件
prompts/generated/     版本化执行提示词
outputs/candidates/    seed、draft 和 long draft
outputs/masters/       通过验收的 LoopLock 母版
outputs/wallpapers/    同一份循环壁纸副本，不重新编码
outputs/review/        抽帧和拼图证据
outputs/images/        全帧数图片列（keep_001 起；人选帧门证据）
artifacts/             诊断中间产物（RIFE 对诊断 PNG/报告）
reports/               runner 结构化报告
```

不要覆盖同名文件。运行日期、主体、seed、profile、版本或 loop 模式至少有一项进入文件名。

## 最终报告内容

按“结果先行”报告：

1. 最终成片绝对路径和可点击链接；
2. 尺寸、fps、时长、帧数、codec、pixel format、流类型和文件大小；
3. 输入图、prompt、seed、LoRA、profile、静音和 loop 模式；
4. draft/long/final 的实际晋级情况；
5. 峰值 VRAM、RAM、耗时和熔断余量；
6. 视觉上通过的项目和仍存在的缺陷；
7. validator 结果和 SHA-256；
8. 未执行的可选升级，例如 4K。

## 必须区分

- “计划命令”与“实际运行命令”；
- “runner 成功”与“视觉通过”；
- “母版”与“循环成片”（LoopLock 交付时二者是同一份文件的两个副本）；
- “静音参数”与“媒体文件实际没有音轨”；
- “低分辨率阶段通过”与“final 已重新验收”。

## 交付前检查

- 任何为绕过环境问题而临时挪动的项目目录都已恢复；
- ComfyUI 队列没有遗留任务；
- 用户原始输入未被修改；
- 原始 ComfyUI 输出和运行报告仍保留；
- 最终文件可以打开；
- 文件哈希已记录。

## 完成标准

用户可以直接找到和播放最终文件，并能从报告复现核心参数、理解已知缺陷和选择是否继续 1080p/4K 升级。
