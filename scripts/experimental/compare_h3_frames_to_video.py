#!/usr/bin/env python3
"""Prove that changing only the output stage did not change the rendered frames.

The frame-sequence route and the old CreateVideo route share the same model,
sampler, prompt, seed, LoRA and internal resolution, so a run at the same frame
count must produce the same pixels. This compares a PNG sequence against a
reference MP4 frame by frame and reports PSNR/MAD, streaming both sides so the
comparison itself never buffers a whole video.

A high PSNR here means the two routes agree on content and only differ in how
the result was written to disk. It is a content-identity check, not a quality
metric: the reference MP4 already carries its own encoder loss.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("frame_dir", type=Path)
    parser.add_argument("reference_video", type=Path)
    parser.add_argument("--pattern", default=r"^frame_(\d{5})_\.png$")
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    matcher = re.compile(args.pattern)
    frames = {}
    for entry in sorted(args.frame_dir.iterdir()):
        found = matcher.match(entry.name) if entry.is_file() else None
        if found:
            frames[int(found.group(1))] = entry
    ordered = [frames[index] for index in sorted(frames)]
    if not ordered:
        raise RuntimeError(f"No frames matched {args.pattern} in {args.frame_dir}")

    psnrs: list[float] = []
    luma_psnrs: list[float] = []
    mads: list[float] = []
    decoded = 0
    luma_weights = np.array([0.299, 0.587, 0.114], dtype=np.float64)
    with av.open(str(args.reference_video)) as container:
        for index, frame in enumerate(container.decode(video=0)):
            decoded += 1
            if index >= len(ordered):
                continue
            candidate = frame.to_ndarray(format="rgb24").astype(np.float64)
            with Image.open(ordered[index]) as handle:
                reference = np.asarray(handle.convert("RGB")).astype(np.float64)
            if candidate.shape != reference.shape:
                raise RuntimeError(f"Shape mismatch at index {index}: video {candidate.shape} vs png {reference.shape}")
            difference = candidate - reference
            mse = float((difference ** 2).mean())
            luma_mse = float((((candidate @ luma_weights) - (reference @ luma_weights)) ** 2).mean())
            mads.append(float(np.abs(difference).mean()))
            psnrs.append(float("inf") if mse == 0.0 else 10.0 * float(np.log10(255.0 * 255.0 / mse)))
            luma_psnrs.append(float("inf") if luma_mse == 0.0 else 10.0 * float(np.log10(255.0 * 255.0 / luma_mse)))

    finite = [value for value in psnrs if value != float("inf")]
    finite_luma = [value for value in luma_psnrs if value != float("inf")]
    result = {
        "schema_version": 1,
        "kind": "h3_frames_vs_reference_video",
        "frame_dir": str(args.frame_dir.resolve()),
        "reference_video": str(args.reference_video.resolve()),
        "png_frames": len(ordered),
        "video_frames": decoded,
        "compared_frames": len(psnrs),
        "frame_counts_match": len(ordered) == decoded,
        "psnr_mean_db": float(np.mean(finite)) if finite else None,
        "psnr_min_db": float(np.min(finite)) if finite else None,
        "luma_psnr_mean_db": float(np.mean(finite_luma)) if finite_luma else None,
        "luma_psnr_min_db": float(np.min(finite_luma)) if finite_luma else None,
        "mad_mean": float(np.mean(mads)) if mads else None,
        "mad_max": float(np.max(mads)) if mads else None,
    }
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
