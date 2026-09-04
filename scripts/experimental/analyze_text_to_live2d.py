#!/usr/bin/env python3
"""Validate an H3 pseudo-T2I still passed directly into an H3 Live2D video."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-frame", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--sheet-output", type=Path, required=True)
    return parser.parse_args()


def mad(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.abs(first.astype(np.int16) - second.astype(np.int16)).mean())


def edge_energy(image: np.ndarray) -> float:
    gray = image.astype(np.float32).mean(axis=2)
    return float(np.abs(gray[:, 1:] - gray[:, :-1]).mean() + np.abs(gray[1:, :] - gray[:-1, :]).mean())


def main() -> int:
    args = parse_args()
    still_image = Image.open(args.first_frame).convert("RGB")
    source_size = still_image.size
    with av.open(str(args.video)) as container:
        stream = container.streams.video[0]
        streams = [item.type for item in container.streams]
        frames = [frame.to_ndarray(format="rgb24") for frame in container.decode(video=0)]
        info = {
            "codec": stream.codec_context.name,
            "width": stream.codec_context.width,
            "height": stream.codec_context.height,
            "fps": float(stream.average_rate),
            "declared_frames": stream.frames,
            "streams": streams,
        }
    target_size = (info["width"], info["height"])
    if still_image.size != target_size:
        still_image = still_image.resize(target_size, Image.Resampling.LANCZOS)
    still = np.asarray(still_image)
    height, width = still.shape[:2]
    subject = (slice(int(height * 0.02), int(height * 0.99)), slice(int(width * 0.25), int(width * 0.75)))
    bg_mask = np.ones((height, width), dtype=bool)
    bg_mask[subject] = False
    steps = np.array([mad(frames[i], frames[i + 1]) for i in range(len(frames) - 1)])
    metrics = {
        "first_frame": str(args.first_frame.resolve()),
        "video": str(args.video.resolve()),
        **info,
        "decoded_frames": len(frames),
        "file_bytes": args.video.stat().st_size,
        "source_image_size": list(source_size),
        "analysis_image_size": list(target_size),
        "input_to_video_frame0_mad": mad(still, frames[0]),
        "motion_step_mean_mad": float(steps.mean()),
        "motion_step_p95_mad": float(np.percentile(steps, 95)),
        "motion_step_max_mad": float(steps.max()),
        "endpoint_full_mad": mad(frames[0], frames[-1]),
        "endpoint_subject_mad": mad(frames[0][subject], frames[-1][subject]),
        "endpoint_background_mad": mad(frames[0][bg_mask], frames[-1][bg_mask]),
        "edge_energy_mean": float(np.mean([edge_energy(frame) for frame in frames])),
        "black_frames": int(sum(float(frame.mean()) < 5.0 for frame in frames)),
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    indexes = [round((len(frames) - 1) * fraction / 4) for fraction in range(5)]
    thumb_width, thumb_height, label_height = 512, 288, 28
    sheet = Image.new("RGB", (thumb_width * len(indexes), thumb_height + label_height), "#171717")
    draw = ImageDraw.Draw(sheet)
    for column, index in enumerate(indexes):
        image = Image.fromarray(frames[index]).resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        x = column * thumb_width
        sheet.paste(image, (x, label_height))
        draw.text((x + 8, 7), f"frame {index}", fill="white")
    sheet.save(args.sheet_output, quality=95)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"contact_sheet={args.sheet_output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
