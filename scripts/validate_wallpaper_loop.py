#!/usr/bin/env python3
"""Repeatedly decode a wallpaper loop for a requested virtual playback duration."""

from __future__ import annotations

import argparse
import json
import math
import time
import zlib
from pathlib import Path

import av
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--minutes", type=float, default=1.0)
    return parser.parse_args()


def mad(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.abs(first.astype(np.int16) - second.astype(np.int16)).mean())


def read_metadata(path: Path) -> dict[str, object]:
    with av.open(str(path)) as container:
        video = container.streams.video[0]
        stream_types = [stream.type for stream in container.streams]
        return {
            "codec": video.codec_context.name,
            "profile": video.codec_context.profile,
            "pixel_format": video.codec_context.pix_fmt,
            "width": video.codec_context.width,
            "height": video.codec_context.height,
            "fps": float(video.average_rate),
            "fps_text": str(video.average_rate),
            "frames": video.frames,
            "duration_seconds": float(video.duration * video.time_base),
            "stream_types": stream_types,
        }


def main() -> int:
    args = parse_args()
    if not args.video.is_file():
        raise FileNotFoundError(args.video)
    if args.minutes <= 0:
        raise ValueError("Validation duration must be positive.")

    metadata = read_metadata(args.video)
    if metadata["codec"] != "h264" or metadata["pixel_format"] != "yuv420p":
        raise RuntimeError("Wallpaper is not H.264/yuv420p.")
    if metadata["stream_types"] != ["video"]:
        raise RuntimeError("Wallpaper must contain exactly one silent video stream.")

    fps = float(metadata["fps"])
    target_frames = math.ceil(args.minutes * 60.0 * fps)
    cycles = math.ceil(target_frames / int(metadata["frames"]))
    decoded_total = 0
    pts_errors = 0
    black_frames = 0
    checksum_mismatches = 0
    reference_checksums: list[int] | None = None
    first_frame: np.ndarray | None = None
    last_frame: np.ndarray | None = None
    started = time.perf_counter()

    for cycle in range(cycles):
        checksums: list[int] = []
        previous_pts: int | None = None
        cycle_count = 0
        with av.open(str(args.video)) as container:
            for frame in container.decode(video=0):
                if previous_pts is not None and frame.pts is not None and frame.pts <= previous_pts:
                    pts_errors += 1
                previous_pts = frame.pts
                array = frame.to_ndarray(format="rgb24")
                if float(array.mean()) < 1.0 or float(array.std()) < 1.0:
                    black_frames += 1
                checksums.append(zlib.crc32(array))
                if first_frame is None:
                    first_frame = array.copy()
                last_frame = array
                cycle_count += 1
        if cycle_count != metadata["frames"]:
            raise RuntimeError(f"Cycle {cycle} decoded {cycle_count} frames; expected {metadata['frames']}.")
        if reference_checksums is None:
            reference_checksums = checksums
        elif checksums != reference_checksums:
            checksum_mismatches += 1
        decoded_total += cycle_count
        if (cycle + 1) % 25 == 0 or cycle + 1 == cycles:
            print(f"Validated {cycle + 1}/{cycles} cycles ({decoded_total} decoded frames)", flush=True)

    if first_frame is None or last_frame is None:
        raise RuntimeError("No frames were decoded.")

    header = args.video.read_bytes()[: 4 * 1024 * 1024]
    moov = header.find(b"moov")
    mdat = header.find(b"mdat")
    result = {
        "video": str(args.video.resolve()),
        "metadata": metadata,
        "requested_minutes": args.minutes,
        "target_frames": target_frames,
        "validated_cycles": cycles,
        "decoded_frames": decoded_total,
        "virtual_playback_seconds": decoded_total / fps,
        "decode_wall_seconds": time.perf_counter() - started,
        "pts_errors": pts_errors,
        "black_frames": black_frames,
        "checksum_mismatch_cycles": checksum_mismatches,
        "loop_boundary_mad": mad(last_frame, first_frame),
        "faststart": moov >= 0 and (mdat < 0 or moov < mdat),
        "passed": decoded_total >= target_frames
        and pts_errors == 0
        and black_frames == 0
        and checksum_mismatches == 0,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
