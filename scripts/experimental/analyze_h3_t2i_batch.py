#!/usr/bin/env python3
"""Measure consistency of a five-frame MiniMax H3 pseudo-T2I packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def mad(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


def edge_energy(image: np.ndarray) -> float:
    gray = image.astype(np.float32).mean(axis=2)
    return float(np.abs(gray[:, 1:] - gray[:, :-1]).mean() + np.abs(gray[1:, :] - gray[:-1, :]).mean())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("images", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frames = [np.asarray(Image.open(path).convert("RGB")) for path in args.images]
    steps = [mad(frames[index], frames[index + 1]) for index in range(len(frames) - 1)]
    result = {
        "images": [str(path.resolve()) for path in args.images],
        "frame_count": len(frames),
        "width": frames[0].shape[1],
        "height": frames[0].shape[0],
        "consecutive_mad": steps,
        "consecutive_mad_mean": float(np.mean(steps)),
        "first_to_last_mad": mad(frames[0], frames[-1]),
        "edge_energy": [edge_energy(frame) for frame in frames],
        "black_frames": int(sum(float(frame.mean()) < 5.0 for frame in frames)),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
