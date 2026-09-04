#!/usr/bin/env python3
"""Minimal closed-loop RIFE pair diagnostic.

originalA.png / originalB.png  (av decode, lossless PNG)
       |
same loader (PIL -> float32 BHWC, ComfyUI LoadImage convention)
       |
A_tensor / B_tensor  --IFNet(rife, t=0.5)-->  M_tensor   (in memory, pre-encode)

Measures (MAD, RGB 0-255 scale, same unit as analyze_motion_uniformity):
  d(A,B)  d(A,M)  d(M,B)
Saves A_loaded.png / M.png / B_loaded.png, then measures
  originalA <-> A_loaded   and   originalB <-> B_loaded   (loader roundtrip)

Verdict logic (triangle inequality: d(A,M)+d(M,B) >= d(A,B) always):
  - d(A,M) ~= d(M,B) ~= d(A,B)/2  -> valid intermediate: model is fine,
    blame the encode/service pipeline.
  - M clings to one endpoint / lopsided split -> hallucinated transition:
    the pair is beyond what this interpolator can put into correspondence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import av
import numpy as np
import torch
import torch.nn as nn
from PIL import Image


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mad(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


def load_ifnet(ifnet_path: Path):
    """Load IFNet without importing the ComfyUI tree (stub comfy.ops)."""
    ops_stub = types.SimpleNamespace(Conv2d=nn.Conv2d, ConvTranspose2d=nn.ConvTranspose2d)
    ops_stub.disable_weight_init = ops_stub
    comfy_pkg = types.ModuleType("comfy")
    comfy_pkg.ops = ops_stub
    sys.modules.setdefault("comfy", comfy_pkg)
    sys.modules.setdefault("comfy.ops", ops_stub)
    spec = importlib.util.spec_from_file_location("diag_ifnet", ifnet_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pad64(t: torch.Tensor) -> tuple[torch.Tensor, int, int]:
    _, _, h, w = t.shape
    ph = (64 - h % 64) % 64
    pw = (64 - w % 64) % 64
    if ph or pw:
        t = torch.nn.functional.pad(t, (0, pw, 0, ph), mode="reflect")
    return t, h, w


def pil_to_tensor(path: Path) -> torch.Tensor:
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(rgb).unsqueeze(0)  # BHWC, ComfyUI convention


def tensor_to_rgb(t: torch.Tensor) -> np.ndarray:
    return (t.detach().float().clamp(0, 1).squeeze(0).cpu().numpy() * 255.0 + 0.5).astype(np.uint8)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path, help="Source video")
    parser.add_argument("--a-index", required=True, type=int, help="0-based frame index for A")
    parser.add_argument("--b-index", required=True, type=int, help="0-based frame index for B")
    parser.add_argument("--weights", required=True, type=Path, help="rife .safetensors")
    parser.add_argument("--ifnet", required=True, type=Path, help="ifnet.py path")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--timesteps",
        default="0.5",
        help="Comma-separated timesteps, e.g. 0.125,0.25,0.375,0.5,0.625,0.75,0.875",
    )
    args = parser.parse_args()

    out_dir = args.out_dir.resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"Refusing to reuse non-empty dir: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    source = args.source.resolve()
    with av.open(str(source)) as container:
        frames = [frame.to_ndarray(format="rgb24") for frame in container.decode(video=0)]
    original_a = out_dir / "originalA.png"
    original_b = out_dir / "originalB.png"
    Image.fromarray(frames[args.a_index]).save(original_a)
    Image.fromarray(frames[args.b_index]).save(original_b)

    # Same loader for both: PIL -> float32 BHWC.
    a = pil_to_tensor(original_a)
    b = pil_to_tensor(original_b)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ifnet = load_ifnet(args.ifnet.resolve())
    # Build config first, then the model (two-pass to keep it readable).
    from safetensors.torch import load_file

    sd = load_file(str(args.weights.resolve()))
    sd = {(k[len("module."):] if k.startswith("module.") else k): v for k, v in sd.items()}
    sd = {k[len("flownet."):] if k.startswith("flownet.") else k: v for k, v in sd.items()}
    key_map = {}
    for k in sd:
        for i in range(5):
            if k.startswith(f"block{i}."):
                key_map[k] = f"blocks.{i}.{k[len(f'block{i}.'):]}"
    if key_map:
        sd = {key_map.get(k, k): v for k, v in sd.items()}
    sd = {k: v for k, v in sd.items() if not k.startswith(("teacher.", "caltime."))}
    head_ch, channels = ifnet.detect_rife_config(sd)
    model = ifnet.IFNet(head_ch=head_ch, channels=channels)
    model.load_state_dict(sd)
    model.eval().to(device, torch.float32)

    a_bchw, ha, wa = pad64(a.movedim(-1, 1).to(device, torch.float32))
    b_bchw, _, _ = pad64(b.movedim(-1, 1).to(device, torch.float32))
    timesteps = [float(t) for t in args.timesteps.split(",")]
    mids: dict[float, np.ndarray] = {}
    with torch.no_grad():
        for t in timesteps:
            mid = model(a_bchw, b_bchw, timestep=t)
            mid = mid[:, :, :ha, :wa].movedim(1, -1)  # BHWC
            mids[t] = tensor_to_rgb(mid)

    a_rgb = tensor_to_rgb(a)
    b_rgb = tensor_to_rgb(b)

    a_loaded = out_dir / "A_loaded.png"
    b_loaded = out_dir / "B_loaded.png"
    Image.fromarray(a_rgb).save(a_loaded)
    Image.fromarray(b_rgb).save(b_loaded)
    mid_files = []
    mid_distances = []
    prev = a_rgb
    for t in timesteps:
        path = out_dir / f"M_t{t:g}.png"
        Image.fromarray(mids[t]).save(path)
        mid_files.append(str(path))
        step = round(mad(prev, mids[t]), 4)
        mid_distances.append({"t": t, "file": str(path), "step_from_prev": step})
        prev = mids[t]
    tail = round(mad(prev, b_rgb), 4)

    orig_a = np.asarray(Image.open(original_a).convert("RGB"))
    orig_b = np.asarray(Image.open(original_b).convert("RGB"))
    dab = round(mad(a_rgb, b_rgb), 4)
    result = {
        "schema_version": 1,
        "source": str(source),
        "source_sha256": sha256(source),
        "a_index": args.a_index,
        "b_index": args.b_index,
        "timesteps": timesteps,
        "device": str(device),
        "dtype": "float32",
        "d_A_B": dab,
        "ladder": mid_distances,
        "ladder_tail_to_B": tail,
        "ladder_total": round(sum(d["step_from_prev"] for d in mid_distances) + tail, 4),
        "loader_A": round(mad(orig_a, a_rgb), 4),
        "loader_B": round(mad(orig_b, b_rgb), 4),
        "files": {
            "originalA": str(original_a),
            "originalB": str(original_b),
            "A_loaded": str(a_loaded),
            "B_loaded": str(b_loaded),
            "mids": mid_files,
        },
    }
    if len(timesteps) == 1:
        t = timesteps[0]
        dam = round(mad(a_rgb, mids[t]), 4)
        dmb = round(mad(mids[t], b_rgb), 4)
        result["d_A_M"] = dam
        result["d_M_B"] = dmb
        if dab > 1e-8 and abs(dam - dmb) < 0.3 * dab and dam + dmb < 1.3 * dab:
            result["verdict"] = "valid_intermediate_model_ok_blame_pipeline"
        else:
            result["verdict"] = "hallucinated_or_lopsided_model_cannot_correspond_pair"
    report_path = out_dir / "diag_report.json"
    report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
