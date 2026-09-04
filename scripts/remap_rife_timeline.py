#!/usr/bin/env python3
"""Convert an integer-multiplier RIFE clip to a target FPS with tail-aware timing."""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path

import av
import numpy as np


def decode_motion(video: Path) -> tuple[list[np.ndarray], float]:
    frames: list[np.ndarray] = []
    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate)
        for frame in container.decode(video=0):
            image = frame.to_image()
            image.thumbnail((480, 270))
            frames.append(np.asarray(image.convert("L"), dtype=np.float32))
    return frames, fps


def detect_tail_start(
    steps: np.ndarray, search_start_ratio: float, threshold_ratio: float
) -> tuple[int, float]:
    search_start = max(1, int(len(steps) * search_start_ratio))
    reference = float(np.median(steps[:search_start]))
    threshold = reference * threshold_ratio
    for index in range(search_start, max(search_start, len(steps) - 2)):
        if float(np.mean(steps[index : index + 3])) <= threshold:
            return index, threshold
    return len(steps), threshold


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--rife-video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--multiplier", type=int, default=4)
    parser.add_argument("--target-fps", type=float, default=60)
    parser.add_argument("--speed", type=float, default=0.8)
    parser.add_argument("--tail-duration-factor", type=float, default=0.6)
    parser.add_argument(
        "--tail-search-start",
        type=float,
        default=0.70,
        help="Only search for the freeze tail at/after this fraction of the clip.",
    )
    parser.add_argument(
        "--tail-threshold-ratio",
        type=float,
        default=0.30,
        help="A 3-frame mean at/below median(pre-tail) * this ratio opens the tail.",
    )
    parser.add_argument(
        "--allow-duplicates",
        action="store_true",
        help="Silence the duplicate-RIFE-frame warning. Nearest-frame resampling "
        "must repeat frames when slowing down; each repeat is a micro-freeze.",
    )
    parser.add_argument("--cyclic", action="store_true")
    parser.add_argument("--crf", type=int, default=18)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    rife_video = Path(args.rife_video).resolve()
    output = Path(args.output).resolve()
    report_path = Path(args.report).resolve()
    for path in (source, rife_video):
        if not path.is_file():
            raise FileNotFoundError(path)
    for path in (output, report_path):
        if path.exists():
            raise FileExistsError(f"Refusing to replace: {path}")

    source_frames, source_fps = decode_motion(source)
    if len(source_frames) < 2:
        raise RuntimeError("Source video has fewer than two frames")
    linear_steps = np.asarray(
        [np.mean(np.abs(b - a)) for a, b in zip(source_frames, source_frames[1:])],
        dtype=np.float64,
    )
    tail_start, tail_threshold = detect_tail_start(
        linear_steps, args.tail_search_start, args.tail_threshold_ratio
    )
    if args.cyclic:
        boundary_step = float(np.mean(np.abs(source_frames[-1] - source_frames[0])))
        steps = np.concatenate((linear_steps, [boundary_step]))
    else:
        boundary_step = None
        steps = linear_steps
    weights = np.ones(len(steps), dtype=np.float64)
    tail_stop = len(linear_steps)
    if tail_start < tail_stop:
        weights[tail_start:tail_stop] = args.tail_duration_factor
    cumulative = np.concatenate(([0.0], np.cumsum(weights)))

    source_intervals = len(source_frames) if args.cyclic else len(source_frames) - 1
    source_interval_seconds = source_intervals / source_fps
    target_interval_seconds = source_interval_seconds / args.speed
    target_frames = round(target_interval_seconds * args.target_fps)
    if not args.cyclic:
        target_frames += 1
    target_clock = np.linspace(
        0.0, cumulative[-1], target_frames, endpoint=not args.cyclic
    )
    source_axis_length = len(source_frames) + 1 if args.cyclic else len(source_frames)
    source_positions = np.interp(
        target_clock,
        cumulative,
        np.arange(source_axis_length, dtype=np.float64),
    )
    rife_indices = np.rint(source_positions * args.multiplier).astype(np.int64)
    if args.cyclic:
        expected_rife_frames = len(source_frames) * args.multiplier
        rife_indices %= expected_rife_frames
    else:
        expected_rife_frames = (len(source_frames) - 1) * args.multiplier + 1
        rife_indices = np.clip(rife_indices, 0, expected_rife_frames - 1)

    output.parent.mkdir(parents=True, exist_ok=True)
    selected = list(enumerate(rife_indices.tolist()))
    selected_by_index: dict[int, list[int]] = {}
    for output_index, rife_index in selected:
        selected_by_index.setdefault(rife_index, []).append(output_index)

    decoded_rife_frames = 0
    written_frames = 0
    rate = Fraction(str(args.target_fps)).limit_denominator()
    with av.open(str(rife_video)) as input_container, av.open(
        str(output), "w", options={"movflags": "+faststart"}
    ) as output_container:
        input_stream = input_container.streams.video[0]
        stream = output_container.add_stream("libx264", rate=rate)
        stream.width = input_stream.width
        stream.height = input_stream.height
        stream.pix_fmt = "yuv420p"
        stream.options = {
            "crf": str(args.crf),
            "preset": "slow",
            "tune": "animation",
            "profile": "high",
        }
        for rife_index, frame in enumerate(input_container.decode(video=0)):
            decoded_rife_frames += 1
            if rife_index not in selected_by_index:
                continue
            for output_index in selected_by_index[rife_index]:
                converted = frame.reformat(
                    width=stream.width, height=stream.height, format="yuv420p"
                )
                converted.pts = output_index
                converted.time_base = Fraction(rate.denominator, rate.numerator)
                for packet in stream.encode(converted):
                    output_container.mux(packet)
                written_frames += 1
        for packet in stream.encode():
            output_container.mux(packet)

    if decoded_rife_frames != expected_rife_frames:
        raise RuntimeError(
            f"RIFE frame count mismatch: decoded {decoded_rife_frames}, expected {expected_rife_frames}"
        )
    if written_frames != target_frames:
        raise RuntimeError(f"Output frame count mismatch: wrote {written_frames}, expected {target_frames}")

    duplicate_steps = int(np.sum(np.diff(rife_indices) == 0))
    if duplicate_steps and not args.allow_duplicates:
        print(
            f"warning: {duplicate_steps}/{target_frames} output frames repeat the "
            "previous RIFE frame (nearest-frame slowdown micro-freeze)"
        )
    tail_steps = linear_steps[tail_start:]
    tail_step_mean: float | None = float(np.mean(tail_steps)) if tail_steps.size else None

    report = {
        "schema_version": 1,
        "status": "success",
        "source": str(source),
        "rife_video": str(rife_video),
        "output": str(output),
        "source_frames": len(source_frames),
        "source_fps": source_fps,
        "rife_multiplier": args.multiplier,
        "rife_frames": decoded_rife_frames,
        "target_frames": target_frames,
        "target_fps": args.target_fps,
        "target_duration_seconds": target_frames / args.target_fps,
        "requested_speed": args.speed,
        "cyclic": args.cyclic,
        "tail_start_interval": tail_start,
        "tail_duration_factor": args.tail_duration_factor,
        "tail_search_start": args.tail_search_start,
        "tail_threshold_ratio": args.tail_threshold_ratio,
        "allow_duplicates": bool(args.allow_duplicates),
        "tail_motion_threshold": tail_threshold,
        "source_step_mean_mad": float(np.mean(steps)),
        "source_tail_step_mean_mad": tail_step_mean,
        "source_boundary_step_mad": boundary_step,
        "selected_rife_index_min_step": int(np.min(np.diff(rife_indices))),
        "selected_rife_index_max_step": int(np.max(np.diff(rife_indices))),
        "selected_rife_duplicate_steps": duplicate_steps,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
