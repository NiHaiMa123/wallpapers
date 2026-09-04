#!/usr/bin/env python3
"""Quantify the human-review criteria of step 10 phase 6 as machine metrics.

Each metric maps to one thing a viewer would look for while watching the loop:
detail gain, texture crawl, contour breathing, flicker, and loop boundary pulse.
Frames are streamed so peak RAM stays low even at 4K.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterator

import av
import numpy as np
from PIL import Image

from upscale_4k_common import ResourceTracker, atomic_write_json, sha256_file, utc_now

GRID = (9, 16)
STATIC_THRESHOLD = 2.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--lanczos", type=Path, required=True)
    parser.add_argument("--ai", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--stdout-only", action="store_true")
    parser.add_argument("--detail-gain-min", type=float, default=0.15)
    parser.add_argument("--crawl-ratio-max", type=float, default=1.30)
    return parser.parse_args()


def frames_of(path: Path) -> Iterator[np.ndarray]:
    with av.open(str(path)) as container:
        for frame in container.decode(video=0):
            yield frame.to_ndarray(format="rgb24")


def to_source_size(frame: np.ndarray, source_size: tuple[int, int]) -> np.ndarray:
    if frame.shape[1] == source_size[0] and frame.shape[0] == source_size[1]:
        return frame
    return np.asarray(Image.fromarray(frame).resize(source_size, Image.Resampling.LANCZOS))


def gray(frame: np.ndarray) -> np.ndarray:
    return frame.astype(np.float32).mean(axis=2)


def edge_energy(plane: np.ndarray) -> float:
    return float(np.abs(plane[:, 1:] - plane[:, :-1]).mean() + np.abs(plane[1:, :] - plane[:-1, :]).mean())


def laplacian_variance(plane: np.ndarray) -> float:
    inner = plane[1:-1, 1:-1]
    lap = plane[:-2, 1:-1] + plane[2:, 1:-1] + plane[1:-1, :-2] + plane[1:-1, 2:] - 4.0 * inner
    return float(lap.var())


def grid_means(values: np.ndarray) -> np.ndarray:
    rows, cols = GRID
    height, width = values.shape
    trimmed = values[: height // rows * rows, : width // cols * cols]
    return trimmed.reshape(rows, trimmed.shape[0] // rows, cols, trimmed.shape[1] // cols).mean(axis=(1, 3))


def summarize(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(array.mean()),
        "std": float(array.std()),
        "p95": float(np.percentile(array, 95)),
        "max": float(array.max()),
        "peak_to_peak": float(array.max() - array.min()),
    }


def relative(candidate: float, reference: float) -> float | None:
    return float(candidate / reference) if reference > 1e-9 else None


def collect(source_path: Path, candidate_path: Path, tracker: ResourceTracker) -> dict[str, Any]:
    native_edge: list[float] = []
    native_lap: list[float] = []
    native_luma: list[float] = []
    native_step: list[float] = []
    source_step: list[float] = []
    residual: list[float] = []
    crawl: list[float] = []
    static_fraction: list[float] = []
    motion_cosine: list[float] = []
    luma_step: list[float] = []
    source_luma_step: list[float] = []
    grid_total = np.zeros(GRID, dtype=np.float64)
    grid_frames = 0

    previous_source: np.ndarray | None = None
    previous_down: np.ndarray | None = None
    first_native: np.ndarray | None = None
    last_native: np.ndarray | None = None
    count = 0

    for source_frame, candidate_frame in zip(frames_of(source_path), frames_of(candidate_path)):
        native_plane = gray(candidate_frame)
        native_edge.append(edge_energy(native_plane))
        native_lap.append(laplacian_variance(native_plane))
        native_luma.append(float(native_plane.mean()))
        if first_native is None:
            first_native = candidate_frame.copy()
        if last_native is not None:
            native_step.append(float(np.abs(candidate_frame.astype(np.int16) - last_native).mean()))
        last_native = candidate_frame.astype(np.int16)

        source_size = (source_frame.shape[1], source_frame.shape[0])
        down = to_source_size(candidate_frame, source_size).astype(np.int16)
        current_source = source_frame.astype(np.int16)
        if previous_source is not None and previous_down is not None:
            source_delta = current_source - previous_source
            candidate_delta = down - previous_down
            source_step.append(float(np.abs(source_delta).mean()))
            difference = np.abs(candidate_delta - source_delta).astype(np.float32)
            residual.append(float(difference.mean()))
            grid_total += grid_means(difference.mean(axis=2))
            grid_frames += 1

            static = np.abs(source_delta).max(axis=2) < STATIC_THRESHOLD
            static_fraction.append(float(static.mean()))
            if static.any():
                crawl.append(float(np.abs(candidate_delta).mean(axis=2)[static].mean()))

            flat_source = source_delta.reshape(-1).astype(np.float64)
            flat_candidate = candidate_delta.reshape(-1).astype(np.float64)
            norm = np.linalg.norm(flat_source) * np.linalg.norm(flat_candidate)
            if norm > 1e-9:
                motion_cosine.append(float(float(flat_source @ flat_candidate) / norm))
            luma_step.append(abs(float(down.mean()) - float(previous_down.mean())))
            source_luma_step.append(abs(float(current_source.mean()) - float(previous_source.mean())))

        previous_source = current_source
        previous_down = down
        count += 1
        tracker.sample()

    if first_native is None or last_native is None:
        raise RuntimeError(f"No frames decoded from {candidate_path}")

    boundary = float(np.abs(last_native - first_native.astype(np.int16)).mean())
    step_median = float(np.median(native_step)) if native_step else 0.0
    return {
        "path": str(candidate_path.resolve()),
        "sha256": sha256_file(candidate_path),
        "frames": count,
        "detail": {
            "native_edge_energy": summarize(native_edge),
            "native_laplacian_variance": summarize(native_lap),
        },
        "texture_crawl_in_source_static_areas": summarize(crawl) if crawl else None,
        "static_area_fraction_mean": float(np.mean(static_fraction)) if static_fraction else None,
        "contour_breathing": {
            "edge_energy_relative_std": relative(float(np.std(native_edge)), float(np.mean(native_edge))),
            "edge_energy_peak_to_peak": float(max(native_edge) - min(native_edge)),
        },
        "flicker": {
            "luma_step_at_source_size": summarize(luma_step) if luma_step else None,
            "source_luma_step": summarize(source_luma_step) if source_luma_step else None,
        },
        "temporal_residual_at_source_size": summarize(residual) if residual else None,
        "motion": {
            "native_step_mad": summarize(native_step) if native_step else None,
            "source_step_mad": summarize(source_step) if source_step else None,
            "amplification_vs_source": relative(float(np.mean(native_step)), float(np.mean(source_step)))
            if native_step and source_step
            else None,
            "direction_cosine_vs_source": summarize(motion_cosine) if motion_cosine else None,
        },
        "loop_boundary": {
            "endpoint_mad": boundary,
            "median_step_mad": step_median,
            "pulse_ratio": relative(boundary, step_median),
        },
        "residual_grid_mean": (grid_total / grid_frames).tolist() if grid_frames else None,
    }


def hotspots(lanczos_grid: list[list[float]] | None, ai_grid: list[list[float]] | None, top: int = 4) -> list[dict[str, Any]]:
    if lanczos_grid is None or ai_grid is None:
        return []
    delta = np.asarray(ai_grid) - np.asarray(lanczos_grid)
    rows, cols = delta.shape
    order = np.argsort(delta.reshape(-1))[::-1][:top]
    vertical = ["top", "upper", "middle", "lower", "bottom"]
    result = []
    for flat in order:
        row, col = divmod(int(flat), cols)
        result.append(
            {
                "grid_row": row,
                "grid_col": col,
                "vertical_band": vertical[min(int(row / rows * len(vertical)), len(vertical) - 1)],
                "horizontal_fraction": round((col + 0.5) / cols, 3),
                "extra_residual_vs_lanczos": round(float(delta[row, col]), 5),
            }
        )
    return result


def build_verdict(lanczos: dict[str, Any], ai: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    edge_gain = ai["detail"]["native_edge_energy"]["mean"] / lanczos["detail"]["native_edge_energy"]["mean"] - 1.0
    lap_gain = (
        ai["detail"]["native_laplacian_variance"]["mean"] / lanczos["detail"]["native_laplacian_variance"]["mean"] - 1.0
    )
    crawl_ratio = ai["texture_crawl_in_source_static_areas"]["mean"] / lanczos["texture_crawl_in_source_static_areas"]["mean"]
    breathing_ratio = ai["contour_breathing"]["edge_energy_relative_std"] / lanczos["contour_breathing"]["edge_energy_relative_std"]
    flicker_ratio = ai["flicker"]["luma_step_at_source_size"]["mean"] / lanczos["flicker"]["luma_step_at_source_size"]["mean"]
    pulse_ratio = ai["loop_boundary"]["pulse_ratio"] / lanczos["loop_boundary"]["pulse_ratio"]
    conservative_gain = min(edge_gain, lap_gain)
    checks = {
        "detail_gain_is_clear": conservative_gain >= args.detail_gain_min,
        "no_extra_texture_crawl": crawl_ratio <= args.crawl_ratio_max,
        "no_extra_contour_breathing": breathing_ratio <= args.crawl_ratio_max,
        "no_extra_flicker": flicker_ratio <= args.crawl_ratio_max,
        "loop_boundary_not_worse": pulse_ratio <= 1.10,
    }
    return {
        "comparisons": {
            "edge_energy_gain": edge_gain,
            "laplacian_variance_gain": lap_gain,
            "conservative_detail_gain": conservative_gain,
            "texture_crawl_ratio": crawl_ratio,
            "contour_breathing_ratio": breathing_ratio,
            "flicker_ratio": flicker_ratio,
            "loop_boundary_pulse_ratio": pulse_ratio,
        },
        "thresholds": {
            "detail_gain_min": args.detail_gain_min,
            "artifact_ratio_max": args.crawl_ratio_max,
            "loop_boundary_pulse_ratio_max": 1.10,
        },
        "checks": checks,
        "recommended_default_profile": "ai_detail_default" if all(checks.values()) else "temporal_safe",
        "decision_rule": "Switching to ai_detail_default requires every check to pass; an unclear result keeps temporal_safe.",
    }


def main() -> int:
    args = parse_args()
    if args.stdout_only and args.json_output is not None:
        raise ValueError("--stdout-only and --json-output cannot be used together")
    for path in (args.source, args.lanczos, args.ai):
        if not path.is_file():
            raise FileNotFoundError(path)
    if args.json_output is not None and args.json_output.exists():
        raise FileExistsError(f"Review report already exists: {args.json_output}")

    tracker = ResourceTracker()
    started_at = utc_now()
    lanczos = collect(args.source, args.lanczos, tracker)
    ai = collect(args.source, args.ai, tracker)
    if lanczos["frames"] != ai["frames"]:
        raise RuntimeError("Candidates decoded a different number of frames")

    result = {
        "schema_version": 1,
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "review_kind": "machine_proxy_for_human_dynamic_review",
        "source": {"path": str(args.source.resolve()), "sha256": sha256_file(args.source)},
        "candidates": {"temporal_safe_lanczos": lanczos, "ai_detail_realesrgan": ai},
        "residual_hotspots_ai_over_lanczos": hotspots(lanczos["residual_grid_mean"], ai["residual_grid_mean"]),
        "verdict": build_verdict(lanczos, ai, args),
        "resource_usage": tracker.result(),
        "caveat": "These are machine proxies. They cannot replace watching the loop; they only narrow what to look at.",
    }
    if args.json_output is not None:
        atomic_write_json(args.json_output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
