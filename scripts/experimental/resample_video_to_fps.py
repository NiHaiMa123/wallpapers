#!/usr/bin/env python3
"""Resample a silent clip to a target FPS by nearest-frame selection.

Optionally drop the last frame after selection. This does not create new
pixels; use it after RIFE when the integer multiplier FPS is not the
delivery FPS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path

import av
import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--fps", type=float, required=True)
    parser.add_argument("--drop-last", action="store_true")
    parser.add_argument("--crf", type=int, default=18)
    args = parser.parse_args()

    source = args.input.resolve()
    output = args.output.resolve()
    report_path = args.report.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    for path in (output, report_path):
        if path.exists():
            raise FileExistsError(f"Refusing to replace: {path}")
    if args.fps <= 0:
        raise ValueError("fps must be positive")

    source_frames = 0
    source_fps = None
    width = height = None
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        source_fps = float(stream.average_rate)
        width = stream.codec_context.width
        height = stream.codec_context.height
        source_frames = sum(1 for _ in container.decode(video=0))
    if source_frames < 2 or source_fps is None:
        raise RuntimeError("Need a video with at least two frames")

    duration = source_frames / source_fps
    target_frames = max(2, int(round(duration * args.fps)))
    source_index = np.clip(
        np.rint(np.arange(target_frames) * source_fps / args.fps).astype(np.int64),
        0,
        source_frames - 1,
    )
    if args.drop_last:
        source_index = source_index[:-1]
        target_frames = int(source_index.size)
    selected_by_index: dict[int, list[int]] = {}
    for output_index, rife_index in enumerate(source_index.tolist()):
        selected_by_index.setdefault(int(rife_index), []).append(output_index)

    written = 0
    rate = Fraction(str(args.fps)).limit_denominator()
    output.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(source)) as input_container, av.open(
        str(output), "w", options={"movflags": "+faststart"}
    ) as output_container:
        stream = output_container.add_stream("libx264", rate=rate)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.options = {
            "crf": str(args.crf),
            "preset": "slow",
            "tune": "animation",
            "profile": "high",
        }
        for index, frame in enumerate(input_container.decode(video=0)):
            if index not in selected_by_index:
                continue
            for output_index in selected_by_index[index]:
                converted = frame.reformat(
                    width=width, height=height, format="yuv420p"
                )
                converted.pts = output_index
                converted.time_base = Fraction(rate.denominator, rate.numerator)
                for packet in stream.encode(converted):
                    output_container.mux(packet)
                written += 1
        for packet in stream.encode():
            output_container.mux(packet)

    if written != target_frames:
        raise RuntimeError(f"Wrote {written} frames, expected {target_frames}")

    diffs = np.diff(source_index)
    report = {
        "schema_version": 1,
        "status": "success",
        "method": "nearest_frame_fps_resample",
        "source": str(source),
        "source_sha256": sha256(source),
        "output": str(output),
        "output_sha256": sha256(output),
        "source_frames": source_frames,
        "source_fps": source_fps,
        "target_fps": args.fps,
        "target_frames": target_frames,
        "drop_last": bool(args.drop_last),
        "duration_seconds": target_frames / args.fps,
        "selected_index_min_step": int(np.min(diffs)) if diffs.size else 0,
        "selected_index_max_step": int(np.max(diffs)) if diffs.size else 0,
        "selected_duplicate_steps": int(np.sum(diffs == 0)) if diffs.size else 0,
        "codec": "libx264",
        "crf": args.crf,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
