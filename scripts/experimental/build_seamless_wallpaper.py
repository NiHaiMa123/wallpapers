#!/usr/bin/env python3
"""Build a silent H.264 MP4 loop from a short source video.

Default ``--mode crossfade`` blends the tail onto the head. ``--mode mirror``
plays 0..N-1 then N-2..1 and does not mix pixels.
"""

from __future__ import annotations

import argparse
import json
import math
from fractions import Fraction
from pathlib import Path
import sys

import av
import numpy as np

# This script lives in scripts/experimental/, while loop_common.py stays in
# scripts/. Resolve the production scripts dir relative to this file so the
# import works from any working directory.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))
from loop_common import playback_indices  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--mode",
        choices=("crossfade", "mirror"),
        default="crossfade",
        help="crossfade blends the clip onto itself; mirror plays 0..N-1 then N-2..1",
    )
    parser.add_argument("--crossfade-frames", type=int, default=9)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--preset", default="slow")
    return parser.parse_args()


def srgb_to_linear(image: np.ndarray) -> np.ndarray:
    value = image.astype(np.float32) / 255.0
    return np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(image: np.ndarray) -> np.ndarray:
    value = np.where(image <= 0.0031308, image * 12.92, 1.055 * np.power(image, 1.0 / 2.4) - 0.055)
    return np.clip(np.rint(value * 255.0), 0, 255).astype(np.uint8)


def mean_absolute_difference(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.abs(first.astype(np.int16) - second.astype(np.int16)).mean())


def edge_energy(image: np.ndarray) -> float:
    gray = image.astype(np.float32).mean(axis=2)
    horizontal = np.abs(gray[:, 1:] - gray[:, :-1]).mean()
    vertical = np.abs(gray[1:, :] - gray[:-1, :]).mean()
    return float(horizontal + vertical)


def decode_video(path: Path) -> tuple[list[np.ndarray], Fraction]:
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        rate = Fraction(stream.average_rate)
        frames = [frame.to_ndarray(format="rgb24") for frame in container.decode(video=0)]
    if not frames:
        raise RuntimeError("Input video contains no decodable video frames.")
    return frames, rate


def make_mirror_loop(source: list[np.ndarray]) -> tuple[list[np.ndarray], dict[str, float]]:
    indices = playback_indices(len(source), "mirror")
    output = [source[index] for index in indices]
    steps = [
        mean_absolute_difference(output[index], output[(index + 1) % len(output)])
        for index in range(len(output))
    ]
    source_steps = [
        mean_absolute_difference(source[index], source[index + 1])
        for index in range(len(source) - 1)
    ]
    source_step_mean = float(np.mean(source_steps))
    last_step = source_steps[-1]
    metrics = {
        "mode": "mirror",
        "source_frames": len(source),
        "output_frames": len(output),
        "source_raw_boundary_mad": mean_absolute_difference(source[-1], source[0]),
        "encoded_loop_boundary_preencode_mad": steps[-1],
        "loop_step_mean_preencode_mad": float(np.mean(steps)),
        "loop_step_max_preencode_mad": max(steps),
        "source_step_mean_mad": source_step_mean,
        "source_step_last_mad": last_step,
        "source_step_last_ratio": last_step / source_step_mean if source_step_mean else None,
        "turn_jerk_proxy_mad": 2.0 * last_step,
    }
    return output, metrics


def make_loop(source: list[np.ndarray], overlap: int) -> tuple[list[np.ndarray], dict[str, float]]:
    if overlap < 2 or overlap * 3 >= len(source):
        raise ValueError("Crossfade must be at least 2 frames and smaller than one third of the clip.")

    output = [frame.copy() for frame in source[overlap : len(source) - overlap]]
    fade_sharpness: list[float] = []
    for index in range(overlap):
        alpha = (index + 1) / (overlap + 1)
        tail = srgb_to_linear(source[len(source) - overlap + index])
        head = srgb_to_linear(source[index])
        blended = linear_to_srgb((1.0 - alpha) * tail + alpha * head)
        output.append(blended)
        fade_sharpness.append(edge_energy(blended))

    steps = [
        mean_absolute_difference(output[index], output[(index + 1) % len(output)])
        for index in range(len(output))
    ]
    source_steps = [
        mean_absolute_difference(source[index], source[index + 1])
        for index in range(len(source) - 1)
    ]
    normal_sharpness = [edge_energy(frame) for frame in output[: len(output) - overlap]]
    metrics = {
        "mode": "crossfade",
        "source_frames": len(source),
        "output_frames": len(output),
        "source_raw_boundary_mad": mean_absolute_difference(source[-1], source[0]),
        "encoded_loop_boundary_preencode_mad": steps[-1],
        "loop_step_mean_preencode_mad": float(np.mean(steps)),
        "loop_step_max_preencode_mad": max(steps),
        "source_step_mean_mad": float(np.mean(source_steps)),
        "crossfade_min_sharpness_ratio": min(fade_sharpness) / float(np.mean(normal_sharpness)),
    }
    return output, metrics


def encode_video(frames: list[np.ndarray], rate: Fraction, path: Path, crf: int, preset: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    height, width = frames[0].shape[:2]
    with av.open(str(path), mode="w", options={"movflags": "+faststart"}) as container:
        stream = container.add_stream("libx264", rate=rate)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.options = {
            "crf": str(crf),
            "preset": preset,
            "tune": "animation",
            "profile": "high",
            "level": "4.1",
            "movflags": "+faststart",
        }
        for index, array in enumerate(frames):
            frame = av.VideoFrame.from_ndarray(array, format="rgb24")
            frame.pts = index
            frame.time_base = Fraction(rate.denominator, rate.numerator)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def validate_encoded(path: Path) -> dict[str, object]:
    with av.open(str(path)) as container:
        video = container.streams.video[0]
        streams = [stream.type for stream in container.streams]
        decoded = [frame.to_ndarray(format="rgb24") for frame in container.decode(video=0)]
        result: dict[str, object] = {
            "codec": video.codec_context.name,
            "profile": video.codec_context.profile,
            "pixel_format": video.codec_context.pix_fmt,
            "width": video.codec_context.width,
            "height": video.codec_context.height,
            "rate": str(video.average_rate),
            "duration_seconds": float(video.duration * video.time_base),
            "declared_frames": video.frames,
            "decoded_frames": len(decoded),
            "streams": streams,
            "silent": streams == ["video"],
            "encoded_boundary_mad": mean_absolute_difference(decoded[-1], decoded[0]),
            "file_bytes": path.stat().st_size,
        }

    header = path.read_bytes()[: 4 * 1024 * 1024]
    moov = header.find(b"moov")
    mdat = header.find(b"mdat")
    result["faststart"] = moov >= 0 and (mdat < 0 or moov < mdat)
    return result


def main() -> int:
    args = parse_args()
    if not args.input.is_file():
        raise FileNotFoundError(args.input)
    source, rate = decode_video(args.input)
    if args.mode == "mirror":
        output, metrics = make_mirror_loop(source)
    else:
        output, metrics = make_loop(source, args.crossfade_frames)
    encode_video(output, rate, args.output, args.crf, args.preset)
    validation = validate_encoded(args.output)
    if validation["decoded_frames"] != len(output):
        raise RuntimeError("Encoded frame count does not match the generated loop.")
    if not validation["silent"]:
        raise RuntimeError("Output unexpectedly contains a non-video stream.")
    print(
        json.dumps(
            {
                "input": str(args.input.resolve()),
                "output": str(args.output.resolve()),
                "mode": args.mode,
                "crossfade_frames": None if args.mode == "mirror" else args.crossfade_frames,
                "fps": str(rate),
                "metrics": metrics,
                "validation": validation,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
