#!/usr/bin/env python3
"""Compare fixed-condition H3 renders and build a compact contact sheet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--turbo8", type=Path, required=True)
    parser.add_argument("--turbo4", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--sheet-output", type=Path, required=True)
    parser.add_argument("--face-sheet-output", type=Path, required=True)
    return parser.parse_args()


def decode(path: Path) -> tuple[list[np.ndarray], dict[str, object]]:
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        info: dict[str, object] = {
            "path": str(path.resolve()),
            "codec": stream.codec_context.name,
            "width": stream.codec_context.width,
            "height": stream.codec_context.height,
            "fps": float(stream.average_rate),
            "declared_frames": stream.frames,
            "file_bytes": path.stat().st_size,
        }
        frames = [frame.to_ndarray(format="rgb24") for frame in container.decode(video=0)]
    info["decoded_frames"] = len(frames)
    return frames, info


def mad(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.abs(first.astype(np.int16) - second.astype(np.int16)).mean())


def edge_energy(image: np.ndarray) -> float:
    gray = image.astype(np.float32).mean(axis=2)
    return float(
        np.abs(gray[:, 1:] - gray[:, :-1]).mean()
        + np.abs(gray[1:, :] - gray[:-1, :]).mean()
    )


def metrics(frames: list[np.ndarray], info: dict[str, object]) -> dict[str, object]:
    height, width = frames[0].shape[:2]
    # Stable center ROI covers the figurine; four outer strips approximate the static background.
    subject = (slice(int(height * 0.04), int(height * 0.98)), slice(int(width * 0.24), int(width * 0.76)))
    bg_mask = np.ones((height, width), dtype=bool)
    bg_mask[subject] = False
    steps = np.array([mad(frames[i], frames[i + 1]) for i in range(len(frames) - 1)])
    sharpness = np.array([edge_energy(frame) for frame in frames])
    black_frames = sum(float(frame.mean()) < 5.0 for frame in frames)
    result = dict(info)
    result.update(
        {
            "motion_step_mean_mad": float(steps.mean()),
            "motion_step_p95_mad": float(np.percentile(steps, 95)),
            "motion_step_max_mad": float(steps.max()),
            "motion_step_std_mad": float(steps.std()),
            "endpoint_full_mad": mad(frames[0], frames[-1]),
            "endpoint_subject_mad": mad(frames[0][subject], frames[-1][subject]),
            "endpoint_background_mad": mad(frames[0][bg_mask], frames[-1][bg_mask]),
            "edge_energy_mean": float(sharpness.mean()),
            "edge_energy_min": float(sharpness.min()),
            "black_frames": int(black_frames),
        }
    )
    return result


def build_sheet(groups: list[tuple[str, list[np.ndarray]]], path: Path) -> None:
    indexes = [0, 18, 36, 54, 72]
    thumb_width = 384
    thumb_height = 216
    label_height = 28
    sheet = Image.new("RGB", (thumb_width * len(indexes), (thumb_height + label_height) * len(groups)), "#171717")
    draw = ImageDraw.Draw(sheet)
    for row, (label, frames) in enumerate(groups):
        for column, index in enumerate(indexes):
            actual = min(index, len(frames) - 1)
            image = Image.fromarray(frames[actual]).resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
            x = column * thumb_width
            y = row * (thumb_height + label_height) + label_height
            sheet.paste(image, (x, y))
            draw.text((x + 8, y - label_height + 7), f"{label}  frame {actual}", fill="white")
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=94)


def build_face_sheet(groups: list[tuple[str, list[np.ndarray]]], path: Path) -> None:
    indexes = [0, 18, 36, 54, 72]
    tile = 256
    label_height = 28
    sheet = Image.new("RGB", (tile * len(indexes), (tile + label_height) * len(groups)), "#171717")
    draw = ImageDraw.Draw(sheet)
    for row, (label, frames) in enumerate(groups):
        for column, index in enumerate(indexes):
            actual = min(index, len(frames) - 1)
            # The fixed 16:9 test composition places the face in this square.
            crop = Image.fromarray(frames[actual]).crop((180, 25, 500, 345))
            image = crop.resize((tile, tile), Image.Resampling.LANCZOS)
            x = column * tile
            y = row * (tile + label_height) + label_height
            sheet.paste(image, (x, y))
            draw.text((x + 8, y - label_height + 7), f"{label}  frame {actual}", fill="white")
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=95)


def main() -> int:
    args = parse_args()
    paths = [("20-step reference", args.reference), ("Turbo 8-step", args.turbo8), ("Turbo 4-step", args.turbo4)]
    decoded: list[tuple[str, list[np.ndarray], dict[str, object]]] = []
    for label, path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        frames, info = decode(path)
        if len(frames) != 73:
            raise RuntimeError(f"Expected 73 decoded frames for {label}; got {len(frames)}")
        decoded.append((label, frames, info))

    reference = decoded[0][1]
    results: dict[str, object] = {}
    for label, frames, info in decoded:
        item = metrics(frames, info)
        item["mean_frame_mad_vs_reference"] = float(np.mean([mad(a, b) for a, b in zip(reference, frames)]))
        item["last_frame_mad_vs_reference"] = mad(reference[-1], frames[-1])
        item["edge_energy_ratio_vs_reference"] = item["edge_energy_mean"] / metrics(reference, decoded[0][2])["edge_energy_mean"]
        results[label] = item

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    build_sheet([(label, frames) for label, frames, _ in decoded], args.sheet_output)
    build_face_sheet([(label, frames) for label, frames, _ in decoded], args.face_sheet_output)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"contact_sheet={args.sheet_output.resolve()}")
    print(f"face_contact_sheet={args.face_sheet_output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
