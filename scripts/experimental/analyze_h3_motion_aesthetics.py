#!/usr/bin/env python3
"""Measure motion hierarchy and sword-lightning rhythm in fixed Keqing H3 clips.

This is a shortlist tool, not a substitute for watching the result.  Its boxes are
specific to the locked 1024x576 Keqing composition used by this project.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import av
import numpy as np


LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)

# Fractions of width/height.  Hair and cloth are deliberately split around the
# character core so their secondary motion is not mistaken for whole-body travel.
REGIONS = {
    "face_anchor": (0.485, 0.125, 0.575, 0.305),
    "root_anchor": (0.465, 0.500, 0.545, 0.790),
    "hair_left": (0.325, 0.060, 0.475, 0.355),
    "hair_right": (0.570, 0.055, 0.710, 0.365),
    "cloth_left": (0.375, 0.345, 0.475, 0.625),
    "cloth_right": (0.550, 0.340, 0.660, 0.625),
    "body_core": (0.465, 0.310, 0.565, 0.790),
    "crystal_base": (0.135, 0.585, 0.455, 0.965),
    "eye_band": (0.505, 0.180, 0.575, 0.230),
    "sword_effect": (0.165, 0.180, 0.690, 0.535),
}


def box_slice(box: tuple[float, float, float, float], width: int, height: int):
    left, top, right, bottom = box
    return (
        slice(round(top * height), max(round(bottom * height), round(top * height) + 1)),
        slice(round(left * width), max(round(right * width), round(left * width) + 1)),
    )


def load_video(path: Path) -> tuple[np.ndarray, float | None]:
    frames: list[np.ndarray] = []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate) if stream.average_rate is not None else None
        for frame in container.decode(video=0):
            frames.append(frame.to_ndarray(format="rgb24"))
    if not frames:
        raise RuntimeError(f"{path} decoded no frames")
    return np.stack(frames), fps


def lightning_mask(frame: np.ndarray, baseline: np.ndarray) -> np.ndarray:
    rgb = frame.astype(np.float32)
    base = baseline.astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    luma = rgb @ LUMA
    base_luma = base @ LUMA
    purple = ((r + b) * 0.5 - g > 22.0) & (b > g + 14.0) & (r > g + 6.0)
    # Requiring both absolute brightness and rise over frame zero removes most
    # static purple hair/clothing while retaining the generated glow.
    return purple & (luma > 132.0) & (luma - base_luma > 20.0)


def masked_step_mad(frames: np.ndarray, region, effect_masks: np.ndarray) -> float:
    gray = frames.astype(np.float32) @ LUMA
    values: list[float] = []
    for index in range(1, len(frames)):
        valid = ~(effect_masks[index - 1][region] | effect_masks[index][region])
        diff = np.abs(gray[index][region] - gray[index - 1][region])
        values.append(float(diff[valid].mean()) if valid.any() else float(diff.mean()))
    return float(np.mean(values))


def track_patch(frames: np.ndarray, box, search_px: int = 12) -> dict[str, float]:
    """Track a stable patch against frame zero with small normalized-MAE search."""
    gray = frames.astype(np.float32) @ LUMA
    # Half scale makes the exhaustive local search cheap and suppresses texture noise.
    small = gray[:, ::2, ::2]
    height, width = small.shape[1:]
    ys, xs = box_slice(box, width, height)
    template = small[0, ys, xs]
    template = template - template.mean()
    radius = max(1, search_px // 2)
    shifts: list[tuple[float, float]] = []
    for frame in small:
        best_error = float("inf")
        best = (0, 0)
        for dy in range(-radius, radius + 1):
            y0, y1 = ys.start + dy, ys.stop + dy
            if y0 < 0 or y1 > height:
                continue
            for dx in range(-radius, radius + 1):
                x0, x1 = xs.start + dx, xs.stop + dx
                if x0 < 0 or x1 > width:
                    continue
                patch = frame[y0:y1, x0:x1]
                patch = patch - patch.mean()
                error = float(np.mean(np.abs(patch - template)))
                if error < best_error:
                    best_error = error
                    best = (dx * 2, dy * 2)
        shifts.append(best)
    shifts_array = np.asarray(shifts, dtype=np.float32)
    radial = np.linalg.norm(shifts_array, axis=1)
    return {
        "shift_peak_px": float(radial.max()),
        "shift_mean_px": float(radial.mean()),
        "shift_x_range_px": float(np.ptp(shifts_array[:, 0])),
        "shift_y_range_px": float(np.ptp(shifts_array[:, 1])),
    }


def longest_run(values: np.ndarray) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def active_runs(values: np.ndarray) -> int:
    padded = np.pad(values.astype(np.int8), (1, 1))
    return int(np.count_nonzero(np.diff(padded) == 1))


def parse_identity(path: Path) -> tuple[int | None, float | None]:
    match = re.search(r"_s(\d{3})_seed(\d+)_", path.name)
    if not match:
        return None, None
    return int(match.group(2)), int(match.group(1)) / 100.0


def measure(path: Path) -> dict[str, Any]:
    frames_u8, fps = load_video(path)
    frames = frames_u8.astype(np.float32)
    count, height, width, _ = frames.shape
    boxes = {name: box_slice(box, width, height) for name, box in REGIONS.items()}
    baseline = frames_u8[0]
    effect_masks = np.stack([lightning_mask(frame, baseline) for frame in frames_u8])

    motion = {
        name: masked_step_mad(frames, region, effect_masks)
        for name, region in boxes.items()
        if name not in {"eye_band", "sword_effect"}
    }
    hair_motion = (motion["hair_left"] + motion["hair_right"]) * 0.5
    cloth_motion = (motion["cloth_left"] + motion["cloth_right"]) * 0.5
    root_motion = max(motion["root_anchor"], 1e-6)

    sword = boxes["sword_effect"]
    sword_masks = effect_masks[:, sword[0], sword[1]]
    occupancies = sword_masks.mean(axis=(1, 2))
    gray = frames @ LUMA
    rise = np.maximum(gray - gray[0], 0.0)
    energies = np.array([
        float(rise[index][sword][sword_masks[index]].mean()) if sword_masks[index].any() else 0.0
        for index in range(count)
    ])

    # Project effect pixels along the descending blade axis, then count active
    # longitudinal bins.  A uniform neon sheath has high coverage and one run;
    # separated bursts leave gaps and form multiple runs.
    sh, sw = sword_masks.shape[1:]
    yy, xx = np.mgrid[0:sh, 0:sw]
    x0, y0 = 0.05 * sw, 0.78 * sh
    x1, y1 = 0.94 * sw, 0.08 * sh
    vx, vy = x1 - x0, y1 - y0
    projection = ((xx - x0) * vx + (yy - y0) * vy) / max(vx * vx + vy * vy, 1.0)
    bins = np.clip((projection * 24).astype(int), 0, 23)
    coverages: list[float] = []
    run_counts: list[int] = []
    for mask in sword_masks:
        active = np.array([np.count_nonzero(mask & (bins == index)) >= 4 for index in range(24)])
        coverages.append(float(active.mean()))
        run_counts.append(active_runs(active))
    coverages_array = np.asarray(coverages)
    peak_frame = int(np.argmax(energies))

    eye = boxes["eye_band"]
    eye_gray = gray[:, eye[0], eye[1]]
    threshold = float(np.percentile(eye_gray[0], 30))
    dark_fraction = (eye_gray < threshold).mean(axis=(1, 2))
    openness = dark_fraction / max(float(dark_fraction[0]), 1e-6)
    half_level = (1.0 + float(openness.min())) * 0.5
    blink_active = openness < half_level

    seed, strength = parse_identity(path)
    endpoint = np.abs(frames[-1] - frames[0])
    result: dict[str, Any] = {
        "video": str(path.resolve()),
        "name": path.name,
        "seed": seed,
        "lora_strength": strength,
        "frames": count,
        "fps": fps,
        "endpoint_full_mad": float(endpoint.mean()),
        "crystal_step_mad": motion["crystal_base"],
        "body_core_step_mad": motion["body_core"],
        "root_step_mad": motion["root_anchor"],
        "hair_step_mad": hair_motion,
        "cloth_step_mad": cloth_motion,
        "hair_to_root_ratio": hair_motion / root_motion,
        "cloth_to_root_ratio": cloth_motion / root_motion,
        "face_tracking": track_patch(frames_u8, REGIONS["face_anchor"]),
        "root_tracking": track_patch(frames_u8, REGIONS["root_anchor"]),
        "blink_min_openness": float(openness.min()),
        "blink_min_frame": int(np.argmin(openness)),
        "blink_half_depth_frames": int(np.count_nonzero(blink_active)),
        "blink_longest_half_depth_run": longest_run(blink_active),
        "lightning_peak_frame": peak_frame,
        "lightning_energy_peak": float(energies.max()),
        "lightning_energy_mean": float(energies.mean()),
        "lightning_peak_to_mean": float(energies.max() / max(energies.mean(), 1e-6)),
        "lightning_occupancy_peak": float(occupancies.max()),
        "lightning_occupancy_mean": float(occupancies.mean()),
        "lightning_coverage_at_peak": float(coverages_array[peak_frame]),
        "lightning_coverage_mean": float(coverages_array.mean()),
        "lightning_runs_at_peak": int(run_counts[peak_frame]),
        "lightning_low_state_first_last": float((energies[0] + energies[-1]) * 0.5),
        "lightning_energy_series": energies.round(4).tolist(),
        "lightning_coverage_series": coverages_array.round(4).tolist(),
    }
    return result


def zscore(rows: list[dict[str, Any]], getter) -> np.ndarray:
    values = np.asarray([getter(row) for row in rows], dtype=np.float64)
    std = values.std()
    return (values - values.mean()) / (std if std > 1e-9 else 1.0)


def rank(rows: list[dict[str, Any]]) -> None:
    # Relative, deliberately modest-weight ranking.  Dense contact sheets remain the
    # final judge; this merely rejects motion hierarchy failures consistently.
    score = np.zeros(len(rows), dtype=np.float64)
    score -= 1.2 * zscore(rows, lambda r: r["face_tracking"]["shift_peak_px"])
    score -= 1.0 * zscore(rows, lambda r: r["root_tracking"]["shift_peak_px"])
    score -= 0.7 * zscore(rows, lambda r: r["root_step_mad"])
    score += 0.8 * zscore(rows, lambda r: r["hair_to_root_ratio"])
    score += 0.7 * zscore(rows, lambda r: r["cloth_to_root_ratio"])
    score += 1.0 * zscore(rows, lambda r: r["lightning_peak_to_mean"])
    score -= 0.8 * zscore(rows, lambda r: r["lightning_coverage_mean"])
    score -= 0.7 * zscore(rows, lambda r: r["crystal_step_mad"])
    score -= 0.5 * zscore(rows, lambda r: r["endpoint_full_mad"])
    score -= 0.5 * zscore(rows, lambda r: r["blink_longest_half_depth_run"])
    for row, value in zip(rows, score):
        row["automatic_aesthetic_shortlist_score"] = float(value)
    rows.sort(key=lambda row: row["automatic_aesthetic_shortlist_score"], reverse=True)
    for index, row in enumerate(rows, 1):
        row["automatic_rank"] = index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("videos", nargs="+", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    rows = [measure(path) for path in args.videos]
    rank(rows)

    print(
        f"{'rank':>4} {'seed':>10} {'LoRA':>5} {'score':>7} {'facePx':>7} {'rootPx':>7} "
        f"{'hair/root':>9} {'cloth/root':>10} {'burst':>7} {'avgCov':>7} {'blink':>6} {'end':>6}"
    )
    for row in rows:
        print(
            f"{row['automatic_rank']:>4} {row['seed']:>10} {row['lora_strength']:>5.2f} "
            f"{row['automatic_aesthetic_shortlist_score']:>7.2f} "
            f"{row['face_tracking']['shift_peak_px']:>7.2f} "
            f"{row['root_tracking']['shift_peak_px']:>7.2f} "
            f"{row['hair_to_root_ratio']:>9.2f} {row['cloth_to_root_ratio']:>10.2f} "
            f"{row['lightning_peak_to_mean']:>7.2f} {row['lightning_coverage_mean']:>7.3f} "
            f"{row['blink_longest_half_depth_run']:>6d} {row['endpoint_full_mad']:>6.2f}"
        )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "kind": "h3_motion_aesthetic_shortlist",
        "warning": "Composition-specific automatic shortlist; confirm visual rhythm at normal speed.",
        "regions": {name: list(box) for name, box in REGIONS.items()},
        "candidates": rows,
    }
    args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report={args.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
