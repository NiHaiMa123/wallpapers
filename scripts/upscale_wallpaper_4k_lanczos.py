#!/usr/bin/env python3
"""Build a conservative, temporally exact 4K wallpaper baseline with Lanczos."""

from __future__ import annotations

import argparse
import json
import sys
import time
from fractions import Fraction
from pathlib import Path

import av
import psutil
from PIL import Image

from upscale_4k_common import (
    ResourceTracker,
    environment_info,
    load_profile,
    make_partial_path,
    publish_partial,
    probe_video,
    sha256_file,
    utc_now,
    validate_dimensions,
    validate_source_and_targets,
    validate_video,
    write_failure_report,
    write_json_partial,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--run-report", type=Path)
    parser.add_argument("--profile-file", type=Path)
    parser.add_argument("--profile-name")
    parser.add_argument("--width", type=int, default=3840)
    parser.add_argument("--height", type=int, default=2160)
    parser.add_argument("--expected-fps", type=float, default=24.0)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--preset", default="medium")
    parser.add_argument("--tune", default="animation")
    parser.add_argument("--h264-profile", default="high")
    parser.add_argument("--h264-level", default="5.1")
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--scope", choices=("full", "smoke"), default="full")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.run_report is None:
        args.run_report = args.output.with_name(f"{args.output.stem}_RUN.json")
    validate_dimensions(args.width, args.height)
    if args.max_frames < 0:
        raise ValueError("--max-frames cannot be negative")
    validate_source_and_targets(args.input, args.output, args.run_report)
    profile = load_profile(args.profile_file, args.profile_name)
    if profile is not None and profile.get("method") != "lanczos":
        raise ValueError(f"Profile {args.profile_name!r} is not a Lanczos profile")

    source_info = probe_video(args.input)
    if source_info["decoded_frames"] <= 0 or source_info["fps"] is None:
        raise RuntimeError("Input video contains no valid frames or frame rate")
    if not source_info["silent"]:
        raise RuntimeError("Input wallpaper must contain exactly one silent video stream")
    if abs(float(source_info["fps"]) - args.expected_fps) >= 1e-6:
        raise RuntimeError(f"Input fps {source_info['fps']} does not match expected fps {args.expected_fps}")
    expected_frames = int(source_info["decoded_frames"])
    if args.max_frames:
        expected_frames = min(expected_frames, args.max_frames)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.run_report.parent.mkdir(parents=True, exist_ok=True)
    partial_video = make_partial_path(args.output)
    tracker = ResourceTracker()
    process = psutil.Process()
    cpu_before = process.cpu_times()
    started_at = utc_now()
    started = time.perf_counter()
    decoded = 0

    try:
        with av.open(str(args.input)) as source:
            source_video = source.streams.video[0]
            if source_video.average_rate is None:
                raise RuntimeError("Input video has no average frame rate")
            rate = Fraction(source_video.average_rate)
            with av.open(str(partial_video), mode="w", options={"movflags": "+faststart"}) as target:
                output = target.add_stream("libx264", rate=rate)
                output.width = args.width
                output.height = args.height
                output.pix_fmt = "yuv420p"
                output.options = {
                    "crf": str(args.crf),
                    "preset": args.preset,
                    "tune": args.tune,
                    "profile": args.h264_profile,
                    "level": args.h264_level,
                    "movflags": "+faststart",
                }
                for index, frame in enumerate(source.decode(video=0)):
                    if args.max_frames and index >= args.max_frames:
                        break
                    rgb = frame.to_image().resize((args.width, args.height), Image.Resampling.LANCZOS)
                    enlarged = av.VideoFrame.from_image(rgb)
                    enlarged.pts = index
                    enlarged.time_base = Fraction(rate.denominator, rate.numerator)
                    for packet in output.encode(enlarged):
                        target.mux(packet)
                    decoded += 1
                    tracker.sample()
                for packet in output.encode():
                    target.mux(packet)

        validation = validate_video(
            partial_video,
            width=args.width,
            height=args.height,
            fps=args.expected_fps,
            expected_frames=expected_frames,
        )
        if not validation["passed"]:
            raise RuntimeError(f"Lanczos output validation failed: {validation['validation_errors']}")

        elapsed = time.perf_counter() - started
        cpu_after = process.cpu_times()
        tracker.sample()
        output_sha256 = sha256_file(partial_video)
        validation["path"] = str(args.output.resolve())
        validation["sha256"] = output_sha256
        report = {
            "schema_version": 1,
            "status": "success",
            "method": "lanczos",
            "scope": args.scope,
            "complete_video": expected_frames == int(source_info["decoded_frames"]),
            "started_at_utc": started_at,
            "finished_at_utc": utc_now(),
            "command": [sys.executable, *sys.argv],
            "profile": profile,
            "source": source_info,
            "output": {
                "path": str(args.output.resolve()),
                "sha256": output_sha256,
                "validation": validation,
            },
            "encoding": {
                "width": args.width,
                "height": args.height,
                "fps": args.expected_fps,
                "crf": args.crf,
                "preset": args.preset,
                "tune": args.tune,
                "h264_profile": args.h264_profile,
                "h264_level": args.h264_level,
                "max_frames": args.max_frames,
            },
            "performance": {
                "elapsed_seconds": elapsed,
                "seconds_per_frame": elapsed / max(decoded, 1),
                "cpu_user_seconds": cpu_after.user - cpu_before.user,
                "cpu_system_seconds": cpu_after.system - cpu_before.system,
                **tracker.result(),
                "gpu": "not_used",
            },
            "environment": environment_info(),
        }
        partial_report = write_json_partial(args.run_report, report)
        publish_partial(partial_video, args.output)
        publish_partial(partial_report, args.run_report)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        print(f"output={args.output.resolve()}", flush=True)
        print(f"run_report={args.run_report.resolve()}", flush=True)
        return 0
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "status": "failed",
            "method": "lanczos",
            "scope": args.scope,
            "started_at_utc": started_at,
            "failed_at_utc": utc_now(),
            "command": [sys.executable, *sys.argv],
            "error_type": type(exc).__name__,
            "error": str(exc),
            "partial_video": str(partial_video.resolve()) if partial_video.exists() else None,
            "processed_frames": decoded,
            "performance": tracker.result(),
        }
        write_failure_report(args.run_report, failure)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
