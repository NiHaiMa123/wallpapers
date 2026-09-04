from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
COMFY = Path(r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI")
NODE_FILE = PROJECT / "comfyui_custom_nodes" / "ComfyUI-Qwen-H3-Bilingual" / "nodes.py"
sys.path.insert(0, str(COMFY))

spec = importlib.util.spec_from_file_location("qwen_h3_bilingual_nodes", NODE_FILE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

director = module.QwenH3BilingualDirector()
zh, en, status, raw = director.direct(
    creative_brief="精致树脂手办风，明确30岁以上成年女性，银蓝色长发，月夜庭院，16:9壁纸；补全姿态、镜头、材质和光影。",
    task_mode="文生图 / T2I",
    expansion_level="平衡发散 / Balanced",
    extra_requirements="单人、成熟面部、画面无文字；中文和英文必须描述同一画面。",
    reference_instruction_1="提取当前图片风格",
    reference_instruction_2="提取当前图片风格",
    reference_instruction_3="提取当前图片风格",
    reference_instruction_4="提取当前图片风格",
    reference_max_side=1024,
    context_length=32768,
    gpu_offload=0.20,
    vision_gpu_offload_cap=0.20,
    max_output_tokens=1800,
    reasoning="off",
    temperature=0.65,
    top_p=0.90,
    top_k=30,
    min_p=0.05,
    unload_other_lmstudio_models=True,
    stop_server_after=False,
    timeout_seconds=600,
    model_key=module.DEFAULT_MODEL_KEY,
    lms_exe=str(Path.home() / ".lmstudio" / "bin" / "lms.exe"),
)

assert len(zh) > 100, len(zh)
assert len(en) > 100, len(en)
assert "Qwen已卸载" in status
print(json.dumps({"zh_chars": len(zh), "en_chars": len(en), "status": status}, ensure_ascii=False))
print("ZH_PREVIEW=" + zh[:300].replace("\n", " "))
print("EN_PREVIEW=" + en[:300].replace("\n", " "))
