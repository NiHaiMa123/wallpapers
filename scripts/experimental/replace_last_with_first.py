#!/usr/bin/env python3
"""Copy the first frame onto the last frame so the file loop point has zero appearance jump."""

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


def mad(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", required=True, type=Path)
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

    frames = []
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate) if stream.average_rate is not None else 24.0
        width = stream.codec_context.width
        height = stream.codec_context.height
        for frame in container.decode(video=0):
            frames.append(frame.to_ndarray(format="rgb24"))
    if len(frames) < 2:
        raise RuntimeError("Need at least two frames")
    before_wrap = mad(frames[-1], frames[0])
    before_last_step = mad(frames[-2], frames[-1])
    frames[-1] = frames[0].copy()
    after_last_step = mad(frames[-2], frames[-1])

    rate = Fraction(str(fps))
    output.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(output), "w", options={"movflags": "+faststart"}) as out:
        ostream = out.add_stream("libx264", rate=rate)
        ostream.width = width
        ostream.height = height
        ostream.pix_fmt = "yuv420p"
        ostream.options = {"crf": str(args.crf), "preset": "slow", "tune": "animation", "profile": "high"}
        for index, rgb in enumerate(frames):
            frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            converted = frame.reformat(width=width, height=height, format="yuv420p")
            converted.pts = index
            converted.time_base = Fraction(rate.denominator, rate.numerator)
            for packet in ostream.encode(converted):
                out.mux(packet)
        for packet in ostream.encode():
            out.mux(packet)

    report = {
        "schema_version": 1,
        "status": "success",
        "method": "replace_last_frame_with_first",
        "source": str(source),
        "source_sha256": sha256(source),
        "output": str(output),
        "output_sha256": sha256(output),
        "frames": len(frames),
        "fps": fps,
        "wrap_mad_before": before_wrap,
        "wrap_mad_after": 0.0,
        "last_step_mad_before": before_last_step,
        "last_step_mad_after": after_last_step,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
