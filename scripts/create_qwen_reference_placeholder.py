from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "QwenReferencePlaceholder.png"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
Image.new("RGB", (1, 1), (0, 0, 0)).save(OUTPUT, format="PNG")
print(OUTPUT)
