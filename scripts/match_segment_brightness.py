#!/usr/bin/env python3
"""Match a frame range's brightness to a reference range (per-channel mean/std).

Use case: RIFE wrap interpolants (or any retimed tail) come out darker than the
source clip. This lifts the dark segment onto the reference segment's color
statistics with a linear per-channel map, so the seam stops flashing dark.
Non-target frames pass through untouched (re-encoded identically).
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


def parse_range(value: str) -> tuple[int, int]:
    start_text, end_text = value.split("-", 1)
    start, end = int(start_text), int(end_text)
    if end < start:
        raise ValueError(f"Invalid descending frame range: {value}")
    return start, end


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--ref-range",
        required=True,
        help="Frames whose color stats are the target, e.g. 170-174",
    )
    parser.add_argument(
        "--target-range",
        required=True,
        help="Frames to remap, e.g. 175-180",
    )
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
    ref_start, ref_end = parse_range(args.ref_range)
    tgt_start, tgt_end = parse_range(args.target_range)

    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        fps = stream.average_rate
        width, height = stream.codec_context.width, stream.codec_context.height
        frames = [frame.to_ndarray(format="rgb24") for frame in container.decode(video=0)]
    count = len(frames)
    if count < 2:
        raise RuntimeError("Need at least two frames")
    for label, (start, end) in (("ref", (ref_start, ref_end)), ("target", (tgt_start, tgt_end))):
        if start < 0 or end >= count:
            raise ValueError(f"{label} range {start}-{end} outside 0-{count - 1}")
    if ref_end >= tgt_start and tgt_end >= ref_start:
        raise ValueError("ref-range and target-range must not overlap")

    ref_stack = np.stack([frames[i].astype(np.float64) for i in range(ref_start, ref_end + 1)])
    ref_mean = ref_stack.mean(axis=(0, 1, 2))
    ref_std = ref_stack.std(axis=(0, 1, 2))
    before: list[list[float]] = []
    after: list[list[float]] = []
    mapped = []
    for index, rgb in enumerate(frames):
        if tgt_start <= index <= tgt_end:
            before.append([round(float(rgb[:, :, c].mean()), 3) for c in range(3)])
            raw = rgb.astype(np.float64)
            cur_mean = raw.mean(axis=(0, 1))
            cur_std = raw.std(axis=(0, 1))
            scale = np.where(cur_std > 1e-6, ref_std / np.maximum(cur_std, 1e-6), 1.0)
            fixed = (raw - cur_mean) * scale + ref_mean
            fixed = np.clip(np.rint(fixed), 0, 255).astype(np.uint8)
            after.append([round(float(fixed[:, :, c].mean()), 3) for c in range(3)])
            mapped.append(fixed)
        else:
            mapped.append(rgb)

    rate = Fraction(str(float(fps))).limit_denominator()
    output.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(output), "w", options={"movflags": "+faststart"}) as container:
        stream = container.add_stream("libx264", rate=rate)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": str(args.crf), "preset": "slow", "tune": "animation", "profile": "high"}
        for out_i, rgb in enumerate(mapped):
            frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            converted = frame.reformat(width=width, height=height, format="yuv420p")
            converted.pts = out_i
            converted.time_base = Fraction(rate.denominator, rate.numerator)
            for packet in stream.encode(converted):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)

    report = {
        "schema_version": 1,
        "status": "success",
        "method": "segment_brightness_mean_std_match",
        "source": str(source),
        "source_sha256": sha256(source),
        "output": str(output),
        "output_sha256": sha256(output),
        "source_frames": count,
        "ref_range": [ref_start, ref_end],
        "target_range": [tgt_start, tgt_end],
        "ref_mean_rgb": [round(float(v), 3) for v in ref_mean.tolist()],
        "ref_std_rgb": [round(float(v), 3) for v in ref_std.tolist()],
        "target_mean_before": before,
        "target_mean_after": after,
        "crf": args.crf,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
