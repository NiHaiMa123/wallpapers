from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image


PROJECT = Path(__file__).resolve().parents[1]
COMFY = Path(r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI")
NODE_FILE = PROJECT / "comfyui_custom_nodes" / "ComfyUI-Qwen-H3-Bilingual" / "nodes.py"
sys.path.insert(0, str(COMFY))

spec = importlib.util.spec_from_file_location("qwen_h3_bilingual_nodes", NODE_FILE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def load_tensor(path: Path) -> torch.Tensor:
    image = Image.open(path).convert("RGB")
    array = np.asarray(image).astype(np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


input_dir = Path(r"D:\Comfy-Desktop\ComfyUI-Shared\input")
image_1 = load_tensor(input_dir / "暖灯庭院中的银发幻灵.png")
image_2 = load_tensor(input_dir / "PV_M4A1_S_BornBeast_Raw.png")

director = module.QwenH3BilingualDirector()
zh, en, status, raw = director.direct(
    creative_brief="设计一张16:9桌面壁纸：明确30岁以上的成年女性树脂手办，室内收藏柜陈列场景。保持我的主体设定为最高优先级，并融合参考图中被指定的视觉元素。",
    task_mode="文生图 / T2I",
    expansion_level="平衡发散 / Balanced",
    extra_requirements="单人、成熟面部、画面无文字；不要照搬参考图人物身份或武器主体。",
    reference_instruction_1="只参考背景氛围、暖色光源与景深，不参考人物身份或服装。",
    reference_instruction_2="只参考精密表面雕刻、金属镶嵌质感和黑金配色，不参考文字、武器形状或主体。",
    reference_instruction_3="",
    reference_instruction_4="",
    reference_max_side=768,
    context_length=32768,
    gpu_offload=0.50,
    vision_gpu_offload_cap=0.20,
    max_output_tokens=1500,
    reasoning="off",
    temperature=0.55,
    top_p=0.90,
    top_k=30,
    min_p=0.05,
    unload_other_lmstudio_models=True,
    stop_server_after=False,
    timeout_seconds=600,
    model_key=module.DEFAULT_MODEL_KEY,
    lms_exe=str(Path.home() / ".lmstudio" / "bin" / "lms.exe"),
    reference_image_1=image_1,
    reference_image_2=image_2,
)

assert len(zh) > 100, len(zh)
assert len(en) > 100, len(en)
assert "参考图=2" in status, status
assert "Qwen已卸载" in status, status
print(json.dumps({"zh_chars": len(zh), "en_chars": len(en), "status": status}, ensure_ascii=False))
print("ZH_PREVIEW=" + zh[:500].replace("\n", " "))
print("EN_PREVIEW=" + en[:500].replace("\n", " "))
