#!/usr/bin/env python3
"""Measure fidelity, sharpness, temporal residuals, and loop boundaries of 4K candidates."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--lanczos", type=Path, required=True)
    parser.add_argument("--ai", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--sheet-output", type=Path, required=True)
    return parser.parse_args()


def decode(path: Path) -> tuple[list[np.ndarray], dict[str, object]]:
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        info: dict[str, object] = {
            "path": str(path.resolve()),
            "codec": stream.codec_context.name,
            "profile": stream.codec_context.profile,
            "pixel_format": stream.codec_context.pix_fmt,
            "width": stream.codec_context.width,
            "height": stream.codec_context.height,
            "fps": float(stream.average_rate),
            "declared_frames": stream.frames,
            "file_bytes": path.stat().st_size,
            "silent": [item.type for item in container.streams] == ["video"],
        }
        frames = [frame.to_ndarray(format="rgb24") for frame in container.decode(video=0)]
    info["decoded_frames"] = len(frames)
    return frames, info


def mad(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.abs(first.astype(np.int16) - second.astype(np.int16)).mean())


def edge_energy(image: np.ndarray) -> float:
    gray = image.astype(np.float32).mean(axis=2)
    return float(np.abs(gray[:, 1:] - gray[:, :-1]).mean() + np.abs(gray[1:, :] - gray[:-1, :]).mean())


def resize(frame: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    return np.asarray(Image.fromarray(frame).resize(size, Image.Resampling.LANCZOS))


def analyze(source: list[np.ndarray], candidate: list[np.ndarray], info: dict[str, object]) -> dict[str, object]:
    if len(source) != len(candidate):
        raise RuntimeError("Frame count mismatch")
    downscaled = [resize(frame, (source[0].shape[1], source[0].shape[0])) for frame in candidate]
    reconstruction = np.array([mad(a, b) for a, b in zip(source, downscaled)])
    psnr = 20.0 * math.log10(255.0 / max(float(np.sqrt(np.mean(reconstruction**2))), 1e-8))
    native_steps = np.array([mad(candidate[i], candidate[i + 1]) for i in range(len(candidate) - 1)])
    source_steps = np.array([mad(source[i], source[i + 1]) for i in range(len(source) - 1)])
    temporal_residuals = []
    edge_temporal_residuals = []
    for index in range(len(source) - 1):
        source_delta = source[index + 1].astype(np.int16) - source[index].astype(np.int16)
        output_delta = downscaled[index + 1].astype(np.int16) - downscaled[index].astype(np.int16)
        temporal_residuals.append(float(np.abs(output_delta - source_delta).mean()))
        source_edge_delta = edge_energy(source[index + 1]) - edge_energy(source[index])
        output_edge_delta = edge_energy(downscaled[index + 1]) - edge_energy(downscaled[index])
        edge_temporal_residuals.append(abs(output_edge_delta - source_edge_delta))
    result = dict(info)
    result.update(
        {
            "reconstruction_mad_mean_at_source_size": float(reconstruction.mean()),
            "reconstruction_mad_max_at_source_size": float(reconstruction.max()),
            "reconstruction_psnr_db_approx": psnr,
            "native_motion_step_mean_mad": float(native_steps.mean()),
            "native_motion_step_p95_mad": float(np.percentile(native_steps, 95)),
            "native_motion_step_std_mad": float(native_steps.std()),
            "motion_amplification_vs_source": float(native_steps.mean() / source_steps.mean()),
            "temporal_residual_mean_mad_at_source_size": float(np.mean(temporal_residuals)),
            "temporal_residual_p95_mad_at_source_size": float(np.percentile(temporal_residuals, 95)),
            "edge_temporal_residual_mean": float(np.mean(edge_temporal_residuals)),
            "native_endpoint_boundary_mad": mad(candidate[-1], candidate[0]),
            "native_edge_energy_mean": float(np.mean([edge_energy(frame) for frame in candidate])),
            "black_frames": int(sum(float(frame.mean()) < 5.0 for frame in candidate)),
        }
    )
    return result


def build_sheet(groups: list[tuple[str, list[np.ndarray]]], path: Path) -> None:
    frame_count = len(groups[0][1])
    indexes = np.linspace(0, frame_count - 1, 5, dtype=int).tolist()
    tile = 300
    label_height = 28
    sheet = Image.new("RGB", (tile * len(indexes), (tile + label_height) * len(groups)), "#171717")
    draw = ImageDraw.Draw(sheet)
    for row, (label, frames) in enumerate(groups):
        height, width = frames[0].shape[:2]
        box = (
            round(width * 0.25),
            round(height * 0.05),
            round(width * 0.75),
            round(height * 0.65),
        )
        for column, index in enumerate(indexes):
            crop = Image.fromarray(frames[index]).crop(box).resize((tile, tile), Image.Resampling.LANCZOS)
            x = column * tile
            y = row * (tile + label_height) + label_height
            sheet.paste(crop, (x, y))
            draw.text((x + 8, y - label_height + 7), f"{label}  frame {index}", fill="white")
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=95)


def main() -> int:
    args = parse_args()
    source, source_info = decode(args.source)
    lanczos, lanczos_info = decode(args.lanczos)
    ai, ai_info = decode(args.ai)
    if len(source) < 5:
        raise RuntimeError(f"Expected at least five source frames, got {len(source)}")
    if not (len(source) == len(lanczos) == len(ai)):
        raise RuntimeError(
            f"Frame count mismatch: source={len(source)} lanczos={len(lanczos)} ai={len(ai)}"
        )
    results = {
        "source": source_info,
        "lanczos_4k": analyze(source, lanczos, lanczos_info),
        "realesrgan_4k": analyze(source, ai, ai_info),
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    build_sheet([("Source", source), ("Lanczos 4K", lanczos), ("RealESRGAN 4K", ai)], args.sheet_output)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"contact_sheet={args.sheet_output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
