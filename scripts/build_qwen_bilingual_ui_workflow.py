from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "workflows" / "ui" / "00_Qwen3.6_双语H3提示词导演.json"
PLACEHOLDER_NAME = "QwenReferencePlaceholder.png"


def node(
    node_id,
    node_type,
    pos,
    size,
    order,
    inputs,
    outputs,
    widgets,
    title=None,
    color=None,
    bgcolor=None,
    widgets_named=None,
):
    result = {
        "id": node_id,
        "type": node_type,
        "pos": list(pos),
        "size": list(size),
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": inputs,
        "outputs": outputs,
        "properties": {"Node name for S&R": node_type},
        "widgets_values": widgets,
    }
    if widgets_named is not None:
        result["widgets_values_named"] = widgets_named
    if title:
        result["title"] = title
    if color:
        result["color"] = color
    if bgcolor:
        result["bgcolor"] = bgcolor
    return result


notes = """# 00｜Qwen3.6 双语 H3 提示词导演｜最多四张参考图

它不是逐句翻译：先理解中文构思，再按需分析参考图，发散补齐制作细节，最后同时输出内容一致的 **中文完善版** 和 **English H3 Prompt**。

- **🟢 建议调：** 中文构思、任务模式、发散等级、额外要求、参考图及其说明。
- **🔵 可调：** 参考图最长边、上下文、GPU 卸载、最大输出、推理、Temperature。
- **🔴 不建议调：** Top-P / Top-K / Min-P、自动卸载、超时、模型键、lms.exe。

参考图规则：每个上传槽下面都有独立说明，默认“提取当前图片风格”。只有 **真实图片 + 非空说明** 同时存在才会发送给千问；只传图但把说明清空，则该图跳过。默认 1×1 占位图代表“未选择”，不会送入模型。可分别写“只参考背景与光影”“只参考服装材质”“只参考构图，不参考人物”等。

默认组合按 RTX 5080 16GB + 32GB RAM 的稳定性设置：32K 上下文、20% GPU卸载、视觉模式20%上限、单并发。更高卸载虽然更快，但当前桌面占用下可能无法分配计算缓冲；节点会在任何模式下自动回退到30%/20%，避免OOM。执行前释放 ComfyUI 模型缓存，生成后无论成功失败都卸载 Qwen。复用 LM Studio 自带运行时，不需要另装 llama.cpp。"""

nodes = [
    {
        "id": 1,
        "type": "MarkdownNote",
        "pos": [20, 20],
        "size": [1500, 390],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [],
        "outputs": [],
        "properties": {},
        "widgets_values": [notes],
        "title": "使用说明｜原始构思 + 可选参考图 → 双语 H3 提示词",
        "color": "#315c45",
        "bgcolor": "#111111",
    },
    node(
        2,
        "PrimitiveStringMultiline",
        (20, 470),
        (980, 330),
        1,
        [{"name": "value", "type": "STRING", "widget": {"name": "value"}, "link": None}],
        [{"name": "STRING", "type": "STRING", "links": [1]}],
        ["精致高端树脂手办风，一名明确30岁以上的成年女性，月夜庭院陈列场景，16:9桌面壁纸。请发散补全主体细节、成熟年龄特征、姿态、构图、镜头、树脂与PVC材质、光影、背景和负面约束。"],
        "🟢 建议调 ①｜中文核心构思",
        "#1f5d3a",
        "#163a29",
        {"value": "精致高端树脂手办风，一名明确30岁以上的成年女性，月夜庭院陈列场景，16:9桌面壁纸。请发散补全主体细节、成熟年龄特征、姿态、构图、镜头、树脂与PVC材质、光影、背景和负面约束。"},
    ),
    node(
        3,
        "PrimitiveStringMultiline",
        (1040, 470),
        (480, 330),
        2,
        [{"name": "value", "type": "STRING", "widget": {"name": "value"}, "link": None}],
        [{"name": "STRING", "type": "STRING", "links": [2]}],
        ["保持单人、固定镜头、明确成年人；中文与英文内容必须一一对应。不要改变用户指定的主体、风格和场景。"],
        "🟢 建议调 ②｜额外硬性要求",
        "#1f5d3a",
        "#163a29",
        {"value": "保持单人、固定镜头、明确成年人；中文与英文内容必须一一对应。不要改变用户指定的主体、风格和场景。"},
    ),
]

# Four reference cards. A bundled 1x1 placeholder means "unused".
for slot, x, instruction_node_id, image_node_id, text_link, image_link in [
    (1, 20, 11, 15, 3, 7),
    (2, 520, 12, 16, 4, 8),
    (3, 1020, 13, 17, 5, 9),
    (4, 1520, 14, 18, 6, 10),
]:
    image_node = node(
            image_node_id,
            "LoadImage",
            (x, 930),
            (460, 480),
            image_node_id,
            [
                {"name": "image", "type": "COMBO", "widget": {"name": "image"}, "link": None},
                {"name": "upload", "type": "IMAGEUPLOAD", "widget": {"name": "upload"}, "link": None},
            ],
            [
                {"name": "IMAGE", "type": "IMAGE", "links": [image_link]},
                {"name": "MASK", "type": "MASK", "links": None},
            ],
            [PLACEHOLDER_NAME, "image"],
            f"🟢 参考图 {slot}｜上传图片（占位图=未选择）",
            "#6b4d1f",
            "#3f2f18",
            {"image": PLACEHOLDER_NAME, "upload": "image"},
        )
    image_node["properties"].update({"cnr_id": "comfy-core", "ver": "0.33.1"})
    nodes.append(image_node)
    nodes.append(
        node(
            instruction_node_id,
            "PrimitiveStringMultiline",
            (x, 1450),
            (460, 210),
            instruction_node_id,
            [{"name": "value", "type": "STRING", "widget": {"name": "value"}, "link": None}],
            [{"name": "STRING", "type": "STRING", "links": [text_link]}],
            ["提取当前图片风格"],
            f"🟢 参考图 {slot} 说明｜清空则不送入 LLM",
            "#6b4d1f",
            "#3f2f18",
            {"value": "提取当前图片风格"},
        )
    )

director_inputs = [
    {"name": "creative_brief", "type": "STRING", "link": 1},
    {"name": "task_mode", "type": "COMBO", "link": None},
    {"name": "expansion_level", "type": "COMBO", "link": None},
    {"name": "extra_requirements", "type": "STRING", "link": 2},
    {"name": "reference_instruction_1", "type": "STRING", "link": 3},
    {"name": "reference_instruction_2", "type": "STRING", "link": 4},
    {"name": "reference_instruction_3", "type": "STRING", "link": 5},
    {"name": "reference_instruction_4", "type": "STRING", "link": 6},
    {"name": "reference_max_side", "type": "INT", "link": None},
    {"name": "context_length", "type": "INT", "link": None},
    {"name": "gpu_offload", "type": "FLOAT", "link": None},
    {"name": "vision_gpu_offload_cap", "type": "FLOAT", "link": None},
    {"name": "max_output_tokens", "type": "INT", "link": None},
    {"name": "reasoning", "type": "COMBO", "link": None},
    {"name": "temperature", "type": "FLOAT", "link": None},
    {"name": "top_p", "type": "FLOAT", "link": None},
    {"name": "top_k", "type": "INT", "link": None},
    {"name": "min_p", "type": "FLOAT", "link": None},
    {"name": "unload_other_lmstudio_models", "type": "BOOLEAN", "link": None},
    {"name": "stop_server_after", "type": "BOOLEAN", "link": None},
    {"name": "timeout_seconds", "type": "INT", "link": None},
    {"name": "model_key", "type": "STRING", "link": None},
    {"name": "lms_exe", "type": "STRING", "link": None},
    {"name": "reference_image_1", "type": "IMAGE", "link": 7},
    {"name": "reference_image_2", "type": "IMAGE", "link": 8},
    {"name": "reference_image_3", "type": "IMAGE", "link": 9},
    {"name": "reference_image_4", "type": "IMAGE", "link": 10},
]
director_widgets = [
    "精致高端树脂手办风，一名明确30岁以上的成年女性，月夜庭院陈列场景，16:9桌面壁纸。请发散补全构图、材质、光影、背景与负面约束。",
    "文生图 / T2I",
    "平衡发散 / Balanced",
    "保持单人、固定镜头、明确成年人；中文与英文内容必须一一对应。",
    "提取当前图片风格",
    "提取当前图片风格",
    "提取当前图片风格",
    "提取当前图片风格",
    1024,
    32768,
    0.20,
    0.20,
    1800,
    "off",
    0.65,
    0.90,
    30,
    0.05,
    True,
    False,
    600,
    "qwen3.6-35b-a3b-uncensored-heretic-nvfp4-experts-only",
    r"C:\Users\Administrator\.lmstudio\bin\lms.exe",
]
for director_input in director_inputs[: len(director_widgets)]:
    director_input["widget"] = {"name": director_input["name"]}
director_widgets_named = {
    director_inputs[index]["name"]: value for index, value in enumerate(director_widgets)
}
nodes.append(
    node(
        4,
        "QwenH3BilingualDirector",
        (2150, 260),
        (820, 1450),
        3,
        director_inputs,
        [
            {"name": "中文完善版", "type": "STRING", "links": [11, 15]},
            {"name": "English H3 Prompt", "type": "STRING", "links": [12, 16]},
            {"name": "运行状态", "type": "STRING", "links": [13]},
            {"name": "原始响应", "type": "STRING", "links": [14]},
        ],
        director_widgets,
        "Qwen3.6 视觉双语导演｜参数前缀标明优先级",
        "#244a66",
        "#183347",
        director_widgets_named,
    )
)

for node_id, y, title, link_id in [
    (5, 260, "中文完善版｜检查与复制", 11),
    (6, 650, "English H3 Prompt｜粘贴到 01 / 02", 12),
    (7, 1040, "运行状态｜参考图计数 + Qwen 已卸载", 13),
    (8, 1270, "原始响应｜解析失败时排查", 14),
]:
    nodes.append(
        node(
            node_id,
            "PreviewAny",
            (3120, y),
            (900, 300 if node_id in (5, 6) else 170),
            node_id - 1,
            [{"name": "source", "type": "*", "link": link_id}],
            [{"name": "STRING", "type": "STRING", "links": None}],
            [],
            title,
            "#1f5d3a" if node_id in (5, 6) else "#3d3d3d",
            "#163a29" if node_id in (5, 6) else "#262626",
        )
    )

nodes.extend(
    [
        node(
            9,
            "SaveText",
            (4160, 360),
            (430, 160),
            8,
            [
                {"name": "text", "type": "STRING", "link": 15},
                {"name": "filename_prefix", "type": "STRING", "link": None},
                {"name": "format", "type": "COMBO", "link": None},
            ],
            [],
            ["minimax_h3/prompts/zh_prompt", "txt"],
            "保存中文完善版 TXT",
        ),
        node(
            10,
            "SaveText",
            (4160, 750),
            (430, 160),
            9,
            [
                {"name": "text", "type": "STRING", "link": 16},
                {"name": "filename_prefix", "type": "STRING", "link": None},
                {"name": "format", "type": "COMBO", "link": None},
            ],
            [],
            ["minimax_h3/prompts/en_h3_prompt", "txt"],
            "保存 English H3 Prompt TXT",
        ),
    ]
)

workflow = {
    "last_node_id": 18,
    "last_link_id": 16,
    "nodes": nodes,
    "links": [
        [1, 2, 0, 4, 0, "STRING"],
        [2, 3, 0, 4, 3, "STRING"],
        [3, 11, 0, 4, 4, "STRING"],
        [4, 12, 0, 4, 5, "STRING"],
        [5, 13, 0, 4, 6, "STRING"],
        [6, 14, 0, 4, 7, "STRING"],
        [7, 15, 0, 4, 23, "IMAGE"],
        [8, 16, 0, 4, 24, "IMAGE"],
        [9, 17, 0, 4, 25, "IMAGE"],
        [10, 18, 0, 4, 26, "IMAGE"],
        [11, 4, 0, 5, 0, "*"],
        [12, 4, 1, 6, 0, "*"],
        [13, 4, 2, 7, 0, "*"],
        [14, 4, 3, 8, 0, "*"],
        [15, 4, 0, 9, 0, "STRING"],
        [16, 4, 1, 10, 0, "STRING"],
    ],
    "groups": [
        {"id": 1, "title": "使用说明", "bounding": [0, 0, 1550, 430], "color": "#315c45", "font_size": 24, "flags": {}},
        {"id": 2, "title": "🟢 建议调｜中文构思与硬性要求", "bounding": [0, 440, 1550, 400], "color": "#2f8f5b", "font_size": 24, "flags": {}},
        {"id": 3, "title": "🟢 可选参考图｜图片 + 非空说明才生效", "bounding": [0, 880, 2020, 820], "color": "#8b662b", "font_size": 24, "flags": {}},
        {"id": 4, "title": "🔵 可调 + 🔴 不建议调｜默认值已实机验证", "bounding": [2110, 200, 900, 1540], "color": "#3f6f9f", "font_size": 24, "flags": {}},
        {"id": 5, "title": "输出｜先看中文，再复制英文到 H3", "bounding": [3080, 200, 1550, 1430], "color": "#2f8f5b", "font_size": 24, "flags": {}},
    ],
    "config": {},
    "extra": {"ds": {"scale": 0.57, "offset": [45, 45]}, "frontendVersion": "1.48.7"},
    "version": 0.4,
}

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
print(OUTPUT)
