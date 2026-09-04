#!/usr/bin/env python3
"""Validate a MiniMax H3 native-1080p PNG frame sequence before it is encoded.

The streaming route replaces ComfyUI's whole-batch ``CreateVideo`` node with a
per-frame ``SaveImage``, so the frame directory becomes the real deliverable of
the generation stage. This checker refuses to let a broken sequence reach the
encoder: it walks the directory in index order, keeps at most three frames in
memory at a time, and reports the first gap, duplicate, wrong size, unreadable
file or black frame it finds.

Native ``SaveImage`` numbers a batch from 1, so a complete run of N frames is
``frame_00001_.png`` through ``frame_{N:05}_.png``. ``--counter-origin`` exists
for sequences written by a different output node.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from upscale_4k_common import (  # noqa: E402
    ResourceTracker,
    atomic_write_json,
    environment_info,
    sha256_file,
    utc_now,
)

BLACK_FRAME_MEAN_MAX = 5.0
FLAT_FRAME_STD_MAX = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("frame_dir", type=Path, help="Directory holding one run's PNG frames")
    parser.add_argument("--expected-frames", type=int, required=True)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--counter-origin", type=int, default=1)
    parser.add_argument("--pattern", default=r"^frame_(\d{5})_\.png$")
    parser.add_argument("--report", type=Path, help="Write the JSON report here (refuses to overwrite)")
    parser.add_argument("--hash-frames", action="store_true", help="Also SHA-256 every frame (slow)")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def mad(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.abs(first.astype(np.int16) - second.astype(np.int16)).mean())


def edge_energy(image: np.ndarray) -> float:
    gray = image.astype(np.float32).mean(axis=2)
    return float(np.abs(gray[:, 1:] - gray[:, :-1]).mean() + np.abs(gray[1:, :] - gray[:-1, :]).mean())


def collect_frames(frame_dir: Path, pattern: str) -> tuple[dict[int, Path], list[str]]:
    if not frame_dir.is_dir():
        raise NotADirectoryError(frame_dir)
    matcher = re.compile(pattern)
    indexed: dict[int, Path] = {}
    duplicates: list[str] = []
    strays: list[str] = []
    for entry in sorted(frame_dir.iterdir()):
        if not entry.is_file():
            strays.append(entry.name)
            continue
        found = matcher.match(entry.name)
        if not found:
            strays.append(entry.name)
            continue
        index = int(found.group(1))
        if index in indexed:
            duplicates.append(entry.name)
            continue
        indexed[index] = entry
    return indexed, strays + duplicates


def index_problems(indexed: dict[int, Path], expected: int, origin: int) -> dict[str, Any]:
    wanted = list(range(origin, origin + expected))
    missing = [index for index in wanted if index not in indexed]
    extra = sorted(index for index in indexed if index not in set(wanted))
    return {
        "expected_first_index": origin,
        "expected_last_index": origin + expected - 1,
        "found_first_index": min(indexed) if indexed else None,
        "found_last_index": max(indexed) if indexed else None,
        "missing_indexes": missing[:32],
        "missing_count": len(missing),
        "first_missing_index": missing[0] if missing else None,
        "unexpected_indexes": extra[:32],
        "unexpected_count": len(extra),
    }


def scan_sequence(
    indexed: dict[int, Path],
    order: list[int],
    *,
    width: int,
    height: int,
    hash_frames: bool,
    tracker: ResourceTracker,
) -> dict[str, Any]:
    subject = (slice(int(height * 0.02), int(height * 0.99)), slice(int(width * 0.25), int(width * 0.75)))
    background = np.ones((height, width), dtype=bool)
    background[subject] = False

    wrong_size: list[dict[str, Any]] = []
    unreadable: list[dict[str, Any]] = []
    black: list[int] = []
    flat: list[int] = []
    steps: list[float] = []
    means: list[float] = []
    edges: list[float] = []
    hashes: dict[str, str] = {}
    total_bytes = 0
    first_frame: np.ndarray | None = None
    previous: np.ndarray | None = None
    last_frame: np.ndarray | None = None

    for position, index in enumerate(order):
        path = indexed[index]
        total_bytes += path.stat().st_size
        if hash_frames:
            hashes[path.name] = sha256_file(path)
        try:
            with Image.open(path) as handle:
                handle.load()
                size = handle.size
                frame = np.asarray(handle.convert("RGB"))
        except Exception as exc:  # a truncated or corrupt PNG must not reach the encoder
            unreadable.append({"index": index, "name": path.name, "error": f"{type(exc).__name__}: {exc}"})
            previous = None
            continue
        if size != (width, height):
            wrong_size.append({"index": index, "name": path.name, "size": list(size)})

        frame_mean = float(frame.mean())
        means.append(frame_mean)
        edges.append(edge_energy(frame))
        if frame_mean < BLACK_FRAME_MEAN_MAX:
            black.append(index)
        if float(frame.std()) < FLAT_FRAME_STD_MAX:
            flat.append(index)
        if previous is not None and previous.shape == frame.shape:
            steps.append(mad(previous, frame))
        if position == 0:
            first_frame = frame
        previous = frame
        last_frame = frame
        tracker.sample()

    step_array = np.array(steps, dtype=np.float64)
    endpoints: dict[str, Any] = {"full_mad": None, "subject_mad": None, "background_mad": None}
    if first_frame is not None and last_frame is not None and first_frame.shape == last_frame.shape:
        endpoints = {
            "full_mad": mad(first_frame, last_frame),
            "subject_mad": mad(first_frame[subject], last_frame[subject]),
            "background_mad": mad(first_frame[background], last_frame[background]),
        }

    return {
        "wrong_size_frames": wrong_size,
        "unreadable_frames": unreadable,
        "black_frame_indexes": black,
        "flat_frame_indexes": flat,
        "total_frame_bytes": total_bytes,
        "frame_sha256": hashes or None,
        "frame_mean_min": min(means) if means else None,
        "frame_mean_max": max(means) if means else None,
        "edge_energy_mean": float(np.mean(edges)) if edges else None,
        "motion_step_mean_mad": float(step_array.mean()) if step_array.size else None,
        "motion_step_p95_mad": float(np.percentile(step_array, 95)) if step_array.size else None,
        "motion_step_max_mad": float(step_array.max()) if step_array.size else None,
        "endpoint": endpoints,
    }


def main() -> int:
    args = parse_args()
    if args.expected_frames <= 0:
        raise ValueError("--expected-frames must be positive")
    tracker = ResourceTracker()
    frame_dir = args.frame_dir.resolve()
    indexed, unexpected_files = collect_frames(frame_dir, args.pattern)
    indexes = index_problems(indexed, args.expected_frames, args.counter_origin)
    order = sorted(index for index in indexed if index in set(range(args.counter_origin, args.counter_origin + args.expected_frames)))
    scan = scan_sequence(
        indexed,
        order,
        width=args.width,
        height=args.height,
        hash_frames=args.hash_frames,
        tracker=tracker,
    )

    checks = {
        "frame_count": len(indexed) == args.expected_frames,
        "contiguous_indexes": indexes["missing_count"] == 0 and indexes["unexpected_count"] == 0,
        "no_unexpected_files": not unexpected_files,
        "all_frames_readable": not scan["unreadable_frames"],
        "all_frames_correct_size": not scan["wrong_size_frames"],
        "no_black_frames": not scan["black_frame_indexes"],
        "no_flat_frames": not scan["flat_frame_indexes"],
    }
    errors = [name for name, passed in checks.items() if not passed]
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "h3_frame_sequence_validation",
        "checked_at_utc": utc_now(),
        "command": [sys.executable, *sys.argv],
        "frame_dir": str(frame_dir),
        "expected": {
            "frames": args.expected_frames,
            "width": args.width,
            "height": args.height,
            "counter_origin": args.counter_origin,
            "pattern": args.pattern,
        },
        "found_frames": len(indexed),
        "unexpected_files": unexpected_files[:32],
        "indexes": indexes,
        "metrics": scan,
        "checks": checks,
        "validation_errors": errors,
        "passed": not errors,
        "performance": tracker.result(),
        "environment": environment_info(),
    }
    if args.report is not None:
        atomic_write_json(args.report, report)
        report["report_path"] = str(args.report.resolve())
    if not args.quiet:
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    else:
        print(f"passed={report['passed']} frames={len(indexed)}/{args.expected_frames} errors={errors}", flush=True)
    return 0 if report["passed"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
