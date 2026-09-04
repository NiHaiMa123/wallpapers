#!/usr/bin/env python3
"""Stream a MiniMax H3 native-1080p PNG frame sequence into a silent H.264 MP4.

This is the external half of the streaming output route. ComfyUI writes one PNG
per frame and unloads its models; this script then reads those PNGs strictly in
index order, encodes each one immediately, and never holds the whole sequence in
memory. Peak RAM here is expected to stay flat as the frame count grows, which
is the property ``CreateVideo``'s whole-batch buffer did not have.

``--loop-mode mirror`` reorders that same PNG list as 0..N-1 then N-2..1 before
encoding. It is still streaming: each source PNG is opened only when its
playback slot is reached, including on the reverse pass.

The MP4 is written to a ``.part.mp4`` sibling, validated against the encoding
contract, compared back against the source PNGs, and only then renamed to its
final name. A failed encode leaves the partial file and the PNGs in place.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
import numpy as np
import psutil
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loop_common import encoded_length, playback_indices  # noqa: E402
from upscale_4k_common import (  # noqa: E402
    ResourceTracker,
    environment_info,
    make_partial_path,
    publish_partial,
    sha256_file,
    utc_now,
    validate_video,
    write_failure_report,
    write_json_partial,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("frame_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-frames", type=int, required=True)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=float, default=24.0)
    parser.add_argument("--counter-origin", type=int, default=1)
    parser.add_argument("--pattern", default=r"^frame_(\d{5})_\.png$")
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--encoder-preset", default="slow")
    parser.add_argument("--tune", default="animation")
    parser.add_argument("--h264-profile", default="high")
    parser.add_argument("--h264-level", default="4.2")
    parser.add_argument("--run-report", type=Path)
    parser.add_argument("--min-mean-psnr", type=float, default=34.0,
                        help="Floor for RGB-domain PSNR; diagnostic, the luma gate is the primary one")
    parser.add_argument("--min-mean-luma-psnr", type=float, default=38.0,
                        help="Primary gate: BT.601 luma PSNR, immune to the 4:2:0 chroma penalty")
    parser.add_argument("--max-mean-mad", type=float, default=3.5)
    parser.add_argument("--verify-sample", type=int, default=0,
                        help="Compare only every Nth frame against its PNG (0 = compare every frame)")
    parser.add_argument(
        "--loop-mode",
        choices=("linear", "mirror"),
        default="linear",
        help="linear encodes 0..N-1; mirror encodes 0..N-1 then N-2..1 (period 2N-2)",
    )
    return parser.parse_args()


def _psnr(mse: float) -> float:
    return float("inf") if mse == 0.0 else 10.0 * float(np.log10(255.0 * 255.0 / mse))


def resolve_sequence(frame_dir: Path, pattern: str, expected: int, origin: int) -> list[Path]:
    if not frame_dir.is_dir():
        raise NotADirectoryError(frame_dir)
    matcher = re.compile(pattern)
    indexed: dict[int, Path] = {}
    for entry in sorted(frame_dir.iterdir()):
        if not entry.is_file():
            continue
        found = matcher.match(entry.name)
        if found:
            indexed[int(found.group(1))] = entry
    wanted = list(range(origin, origin + expected))
    missing = [index for index in wanted if index not in indexed]
    if missing:
        raise RuntimeError(f"Frame sequence is incomplete: first missing index {missing[0]} of {len(missing)}")
    if len(indexed) != expected:
        extra = sorted(set(indexed) - set(wanted))
        raise RuntimeError(f"Frame directory holds {len(indexed)} frames, expected {expected}; unexpected indexes {extra[:8]}")
    return [indexed[index] for index in wanted]


def encode_sequence(
    frames: list[Path],
    partial: Path,
    args: argparse.Namespace,
    tracker: ResourceTracker,
) -> list[dict[str, float]]:
    """Encode one PNG at a time and sample RAM every frame."""
    rate = Fraction(args.fps).limit_denominator(1000)
    timeline: list[dict[str, float]] = []
    process = psutil.Process()
    started = time.perf_counter()
    with av.open(str(partial), mode="w", options={"movflags": "+faststart"}) as target:
        stream = target.add_stream("libx264", rate=rate)
        stream.width = args.width
        stream.height = args.height
        stream.pix_fmt = "yuv420p"
        stream.options = {
            "crf": str(args.crf),
            "preset": args.encoder_preset,
            "tune": args.tune,
            "profile": args.h264_profile,
            "level": args.h264_level,
            "movflags": "+faststart",
        }
        for index, path in enumerate(frames):
            with Image.open(path) as handle:
                image = handle.convert("RGB")
                if image.size != (args.width, args.height):
                    raise RuntimeError(f"{path.name} is {image.size}, expected {(args.width, args.height)}")
                video_frame = av.VideoFrame.from_image(image)
            video_frame.pts = index
            video_frame.time_base = Fraction(rate.denominator, rate.numerator)
            for packet in stream.encode(video_frame):
                target.mux(packet)
            del video_frame
            tracker.sample()
            timeline.append({
                "frame": index + 1,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "system_ram_gib": round(psutil.virtual_memory().used / 2**30, 3),
                "process_ram_gib": round(process.memory_info().rss / 2**30, 3),
            })
        for packet in stream.encode():
            target.mux(packet)
    tracker.sample()
    return timeline


def compare_against_frames(video: Path, frames: list[Path], sample: int) -> dict[str, Any]:
    """Decode the encoded MP4 and measure how far each frame drifted from its PNG."""
    luma_weights = np.array([0.299, 0.587, 0.114], dtype=np.float64)
    psnrs: list[float] = []
    luma_psnrs: list[float] = []
    mads: list[float] = []
    compared = 0
    decoded = 0
    with av.open(str(video)) as container:
        for index, decoded_frame in enumerate(container.decode(video=0)):
            decoded += 1
            if index >= len(frames):
                break
            if sample and index % sample:
                continue
            candidate = decoded_frame.to_ndarray(format="rgb24").astype(np.float64)
            with Image.open(frames[index]) as handle:
                reference = np.asarray(handle.convert("RGB")).astype(np.float64)
            difference = candidate - reference
            mse = float((difference ** 2).mean())
            luma_difference = (candidate @ luma_weights) - (reference @ luma_weights)
            luma_mse = float((luma_difference ** 2).mean())
            mads.append(float(np.abs(difference).mean()))
            psnrs.append(_psnr(mse))
            luma_psnrs.append(_psnr(luma_mse))
            compared += 1
    finite = [value for value in psnrs if value != float("inf")]
    finite_luma = [value for value in luma_psnrs if value != float("inf")]
    return {
        "decoded_frames": decoded,
        "compared_frames": compared,
        "sample_stride": sample or 1,
        "psnr_mean_db": float(np.mean(finite)) if finite else None,
        "psnr_min_db": float(np.min(finite)) if finite else None,
        "luma_psnr_mean_db": float(np.mean(finite_luma)) if finite_luma else None,
        "luma_psnr_min_db": float(np.min(finite_luma)) if finite_luma else None,
        "mad_mean": float(np.mean(mads)) if mads else None,
        "mad_max": float(np.max(mads)) if mads else None,
    }


def main() -> int:
    args = parse_args()
    if args.expected_frames <= 0:
        raise ValueError("--expected-frames must be positive")
    if args.output.exists():
        raise FileExistsError(f"Output already exists: {args.output}")
    if args.run_report is None:
        args.run_report = args.output.with_name(f"{args.output.stem}_ENCODE.json")
    if args.run_report.exists():
        raise FileExistsError(f"Run report already exists: {args.run_report}")

    source_frames = resolve_sequence(args.frame_dir, args.pattern, args.expected_frames, args.counter_origin)
    indices = playback_indices(len(source_frames), args.loop_mode)
    frames = [source_frames[index] for index in indices]
    playback_count = encoded_length(len(source_frames), args.loop_mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.run_report.parent.mkdir(parents=True, exist_ok=True)
    partial = make_partial_path(args.output)
    tracker = ResourceTracker()
    started_at = utc_now()
    started = time.perf_counter()

    try:
        timeline = encode_sequence(frames, partial, args, tracker)
        encode_seconds = time.perf_counter() - started
        validation = validate_video(
            partial,
            width=args.width,
            height=args.height,
            fps=args.fps,
            expected_frames=playback_count,
        )
        comparison = compare_against_frames(partial, frames, args.verify_sample)
        tracker.sample()

        gate_errors = list(validation["validation_errors"])
        if comparison["luma_psnr_mean_db"] is not None and comparison["luma_psnr_mean_db"] < args.min_mean_luma_psnr:
            gate_errors.append("luma_psnr_mean_below_gate")
        if comparison["psnr_mean_db"] is not None and comparison["psnr_mean_db"] < args.min_mean_psnr:
            gate_errors.append("psnr_mean_below_gate")
        if comparison["mad_mean"] is not None and comparison["mad_mean"] > args.max_mean_mad:
            gate_errors.append("mad_mean_above_gate")
        if gate_errors:
            raise RuntimeError(f"Encoded video failed acceptance: {gate_errors}")

        first_half = [row["system_ram_gib"] for row in timeline[: max(len(timeline) // 2, 1)]]
        second_half = [row["system_ram_gib"] for row in timeline[max(len(timeline) // 2, 1):]] or first_half
        validation["path"] = str(args.output.resolve())
        validation["sha256"] = sha256_file(partial)
        report = {
            "schema_version": 1,
            "kind": "h3_frame_sequence_encode",
            "status": "success",
            "started_at_utc": started_at,
            "finished_at_utc": utc_now(),
            "command": [sys.executable, *sys.argv],
            "frame_dir": str(args.frame_dir.resolve()),
            "loop_mode": args.loop_mode,
            "source_frame_count": len(source_frames),
            "frame_count": len(frames),
            "playback_indices_head": indices[:8],
            "playback_indices_tail": indices[-8:],
            "first_frame": frames[0].name,
            "last_frame": frames[-1].name,
            "encoding": {
                "codec": "libx264",
                "width": args.width,
                "height": args.height,
                "fps": args.fps,
                "pixel_format": "yuv420p",
                "crf": args.crf,
                "encoder_preset": args.encoder_preset,
                "tune": args.tune,
                "h264_profile": args.h264_profile,
                "h264_level": args.h264_level,
                "faststart": True,
                "audio": False,
            },
            "output": {
                "path": str(args.output.resolve()),
                "sha256": validation["sha256"],
                "validation": validation,
            },
            "fidelity": comparison,
            "gates": {
                "min_mean_luma_psnr_db": args.min_mean_luma_psnr,
                "min_mean_psnr_db": args.min_mean_psnr,
                "max_mean_mad": args.max_mean_mad,
            },
            "performance": {
                "encode_seconds": round(encode_seconds, 3),
                "seconds_per_frame": round(encode_seconds / max(len(frames), 1), 4),
                "system_ram_gib_first_half_mean": round(float(np.mean(first_half)), 3),
                "system_ram_gib_second_half_mean": round(float(np.mean(second_half)), 3),
                "system_ram_gib_growth_across_run": round(float(np.mean(second_half) - np.mean(first_half)), 3),
                **tracker.result(),
            },
            "ram_timeline": timeline,
            "environment": environment_info(),
        }
        partial_report = write_json_partial(args.run_report, report)
        publish_partial(partial, args.output)
        publish_partial(partial_report, args.run_report)
        print(json.dumps({key: value for key, value in report.items() if key != "ram_timeline"},
                         ensure_ascii=False, indent=2), flush=True)
        print(f"output={args.output.resolve()}", flush=True)
        print(f"run_report={args.run_report.resolve()}", flush=True)
        return 0
    except Exception as exc:
        write_failure_report(args.run_report, {
            "schema_version": 1,
            "kind": "h3_frame_sequence_encode",
            "status": "failed",
            "started_at_utc": started_at,
            "failed_at_utc": utc_now(),
            "command": [sys.executable, *sys.argv],
            "frame_dir": str(args.frame_dir.resolve()),
            "loop_mode": args.loop_mode,
            "expected_frames": args.expected_frames,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "partial_video": str(partial.resolve()) if partial.exists() else None,
            "performance": tracker.result(),
        })
        raise


if __name__ == "__main__":
    raise SystemExit(main())
