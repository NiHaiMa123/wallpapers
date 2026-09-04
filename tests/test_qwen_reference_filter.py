from __future__ import annotations

import importlib.util
from pathlib import Path

import torch


PROJECT = Path(__file__).resolve().parents[1]
NODE_FILE = PROJECT / "comfyui_custom_nodes" / "ComfyUI-Qwen-H3-Bilingual" / "nodes.py"
spec = importlib.util.spec_from_file_location("qwen_h3_bilingual_nodes", NODE_FILE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

placeholder = torch.zeros((1, 1, 1, 3), dtype=torch.float32)
real_image = torch.ones((1, 48, 64, 3), dtype=torch.float32)

active, skipped = module._collect_reference_images(
    [
        (placeholder, "提取当前图片风格"),
        (real_image, ""),
        (None, "只参考背景"),
        (real_image, "只参考材质"),
    ]
)

assert [item[0] for item in active] == [4], active
assert skipped == 1, skipped
data_url = module._image_to_data_url(real_image, 1024)
assert data_url.startswith("data:image/jpeg;base64,")
print("PASS: placeholder / blank instruction / missing image filtering and JPEG encoding")
