#!/usr/bin/env python3
"""Retime a silent video by changing cadence without creating synthetic frames."""

from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path

import av


def parse_index_spec(value: str) -> set[int]:
    indexes: set[int] = set()
    if not value.strip():
        return indexes
    for part in value.split(","):
        part = part.strip()
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if end < start:
                raise ValueError(f"Invalid descending frame range: {part}")
            indexes.update(range(start, end + 1))
        else:
            indexes.add(int(part))
    return indexes


def parse_range(value: str) -> tuple[int, int]:
    start_text, end_text = value.split("-", 1)
    start = int(start_text)
    end = int(end_text)
    if end < start:
        raise ValueError(f"Invalid descending frame range: {value}")
    return start, end


def stride_drop_indexes(start: int, end: int, last_frame: int, stride: int) -> set[int]:
    if stride != 2:
        raise ValueError("Only --drop-stride 2 is supported (keep 1,3,5,7 / drop 2,4,6).")
    drops: set[int] = set()
    for index in range(start, end + 1):
        if index == last_frame:
            continue
        if (index - start) % stride == 1:
            drops.add(index)
    return drops


def count_video_frames(path: Path) -> int:
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        if stream.frames and stream.frames > 0:
            return int(stream.frames)
        return sum(1 for _ in container.decode(video=0))


def count_video_frames(path: Path) -> int:
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        if stream.frames and stream.frames > 0:
            return int(stream.frames)
        return sum(1 for _ in container.decode(video=0))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--fps", type=float, required=True)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--drop-frames", default="")
    parser.add_argument(
        "--drop-stride",
        type=int,
        default=0,
        help="With --drop-range, drop every other frame (2) inside the range. "
        "Keeps range start, drops start+1, keeps start+2, and so on. "
        "Never drops the last frame of the video.",
    )
    parser.add_argument(
        "--drop-range",
        default="",
        help="Inclusive start-end used by --drop-stride, e.g. 141-166",
    )
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--allow-drop-last",
        action="store_true",
        help="Permit dropping the last frame of the video. Without this, "
        "requesting the last frame exits with an error: LoopLock clips anchor "
        "the loop on it and dropping it silently breaks the seam.",
    )
    args = parser.parse_args()

    source = Path(args.input).resolve()
    output = Path(args.output).resolve()
    report_path = Path(args.report).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    for path in (output, report_path):
        if path.exists():
            raise FileExistsError(f"Refusing to replace: {path}")

    rate = Fraction(str(args.fps))
    source_frame_count = count_video_frames(source)
    requested_drops = parse_index_spec(args.drop_frames)
    if args.drop_stride:
        if not args.drop_range:
            raise ValueError("--drop-stride requires --drop-range start-end")
        range_start, range_end = parse_range(args.drop_range)
        requested_drops.update(
            stride_drop_indexes(range_start, range_end, source_frame_count - 1, args.drop_stride)
        )
    elif args.drop_range:
        raise ValueError("--drop-range requires --drop-stride")
    dropped_indexes = {index for index in requested_drops if 0 <= index < source_frame_count}
    ignored_indexes = sorted(set(requested_drops) - dropped_indexes)
    if ignored_indexes:
        print(
            f"warning: ignoring {len(ignored_indexes)} out-of-range "
            f"drop index(es): {ignored_indexes}"
        )
    last_frame = source_frame_count - 1
    if last_frame in dropped_indexes and not args.allow_drop_last:
        raise ValueError(
            f"Refusing to drop last frame ({last_frame}) without --allow-drop-last: "
            "LoopLock clips anchor the loop on it"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    frames = 0
    with av.open(str(source)) as input_container, av.open(
        str(output), "w", options={"movflags": "+faststart"}
    ) as output_container:
        input_stream = input_container.streams.video[0]
        if input_stream.average_rate is None:
            raise RuntimeError("Source video reports no frame rate")
        source_fps = float(input_stream.average_rate)
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
        for index, frame in enumerate(input_container.decode(video=0)):
            if index in dropped_indexes:
                continue
            converted = frame.reformat(
                width=stream.width, height=stream.height, format="yuv420p"
            )
            converted.pts = frames
            converted.time_base = Fraction(rate.denominator, rate.numerator)
            for packet in stream.encode(converted):
                output_container.mux(packet)
            frames += 1
        for packet in stream.encode():
            output_container.mux(packet)

    source_duration = source_frame_count / source_fps
    output_duration = frames / args.fps
    report = {
        "schema_version": 1,
        "status": "success",
        "method": "cadence_retime_without_interpolation",
        "source": str(source),
        "source_sha256": sha256(source),
        "source_frames": source_frame_count,
        "source_fps": source_fps,
        "output": str(output),
        "output_sha256": sha256(output),
        "output_fps": args.fps,
        "frames": frames,
        "dropped_frame_indexes": sorted(dropped_indexes),
        "dropped_frames": len(dropped_indexes),
        "ignored_out_of_range": ignored_indexes,
        "allow_drop_last": bool(args.allow_drop_last),
        "drop_stride": args.drop_stride or None,
        "drop_range": args.drop_range or None,
        "duration_seconds": output_duration,
        "speed_ratio": args.fps / source_fps,
        "effective_speed_ratio": output_duration / source_duration,
        "codec": "libx264",
        "crf": args.crf,
        "preset": "slow",
        "tune": "animation",
        "interpolation": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
