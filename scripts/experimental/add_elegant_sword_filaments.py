#!/usr/bin/env python3
"""Composite tightly controlled traveling lightning bundles beside a fixed sword.

The effect is intentionally deterministic: three short packets cross the blade,
never park at the tip, and leave both loop boundaries dark.  Coordinates target
the locked 1024x576 Keqing composition used by this project.
"""

from __future__ import annotations

import argparse
import json
import math
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


DEFAULT_PASSES = ((8, 18), (30, 40), (52, 62))


def point_on_blade(guard: np.ndarray, tip: np.ndarray, position: float, normal_offset: float) -> np.ndarray:
    direction = tip - guard
    length = float(np.linalg.norm(direction))
    tangent = direction / max(length, 1.0)
    normal = np.array([-tangent[1], tangent[0]], dtype=np.float32)
    return guard + direction * position + normal * normal_offset


def smoothstep(value: float) -> float:
    value = min(max(value, 0.0), 1.0)
    return value * value * (3.0 - 2.0 * value)


def packet_overlay(
    width: int,
    height: int,
    frame_index: int,
    passes: tuple[tuple[int, int], ...],
    guard: np.ndarray,
    tip: np.ndarray,
    scale: int = 4,
) -> Image.Image:
    active: tuple[int, int, int] | None = None
    for pass_index, (start, end) in enumerate(passes):
        if start <= frame_index <= end:
            active = (pass_index, start, end)
            break
    if active is None:
        return Image.new("RGBA", (width, height), (0, 0, 0, 0))

    pass_index, start, end = active
    phase = (frame_index - start) / max(end - start, 1)
    # The packet center travels continuously.  Fade at entry and exit so no frame
    # holds a fully visible filament at the tip.
    center = 0.06 + 0.90 * phase
    envelope = smoothstep(min(phase / 0.16, (1.0 - phase) / 0.16))

    # A tiny common motion follows the permitted sword pivot without making the
    # effect visibly swim.  Both endpoints return to their initial state at frame 72.
    cycle = 2.0 * math.pi * frame_index / 72.0
    shifted_guard = guard + np.array([1.2 * math.sin(cycle), 0.8 * math.sin(cycle + 0.4)])
    shifted_tip = tip + np.array([1.8 * math.sin(cycle - 0.25), 1.2 * math.sin(cycle)])

    glow = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    core = Image.new("RGBA", glow.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    core_draw = ImageDraw.Draw(core)

    # Three close filaments form one readable bundle.  Their kinks are shallow and
    # temporally animated, while the group remains directional and uncluttered.
    strand_specs = (
        # normal offset, length scale, longitudinal shift, core alpha, glow alpha
        (-2.6, 0.70, -0.016, 116, 38),
        (0.0, 1.00, 0.000, 220, 72),
        (2.8, 0.62, 0.026, 128, 42),
    )
    for strand, (base_offset, length_scale, longitudinal_shift, core_strength, glow_strength) in enumerate(strand_specs):
        segment_length = 0.145 * length_scale
        strand_center = center + longitudinal_shift
        start_t = max(0.015, strand_center - segment_length * 0.5)
        end_t = min(0.985, strand_center + segment_length * 0.5)
        points: list[tuple[int, int]] = []
        samples = 6
        for sample in range(samples):
            local = sample / (samples - 1)
            position = start_t + (end_t - start_t) * local
            wave_phase = pass_index * 1.7 + strand * 1.15 + frame_index * 0.34 + local * 5.2
            kink = 3.1 * math.sin(wave_phase) + 1.25 * math.sin(wave_phase * 1.9)
            point = point_on_blade(shifted_guard, shifted_tip, position, 7.0 + base_offset + kink)
            points.append((round(point[0] * scale), round(point[1] * scale)))

        alpha = round(core_strength * envelope)
        glow_alpha = round(glow_strength * envelope)
        glow_draw.line(points, fill=(118, 46, 255, glow_alpha), width=round(2.6 * scale), joint="curve")
        # Draw segment by segment so the filament subtly tapers instead of reading
        # as a uniform parallel rail.
        for segment_index in range(len(points) - 1):
            taper = 0.62 + 0.38 * segment_index / max(len(points) - 2, 1)
            segment_alpha = round(alpha * taper)
            segment_width = max(2, round((0.68 + 0.30 * taper) * scale))
            core_draw.line(
                (points[segment_index], points[segment_index + 1]),
                fill=(226, 198, 255, segment_alpha),
                width=segment_width,
            )

    glow = glow.filter(ImageFilter.GaussianBlur(radius=1.25 * scale))
    combined = Image.alpha_composite(glow, core)
    return combined.resize((width, height), Image.Resampling.LANCZOS)


def screen_composite(base: np.ndarray, overlay: Image.Image) -> np.ndarray:
    over = np.asarray(overlay).astype(np.float32) / 255.0
    rgb = base.astype(np.float32) / 255.0
    color = over[..., :3]
    alpha = over[..., 3:4]
    screened = 1.0 - (1.0 - rgb) * (1.0 - color)
    result = rgb * (1.0 - alpha) + screened * alpha
    return np.clip(result * 255.0 + 0.5, 0, 255).astype(np.uint8)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--guard", nargs=2, type=float, default=(590.0, 178.0), metavar=("X", "Y"))
    parser.add_argument("--tip", nargs=2, type=float, default=(145.0, 300.0), metavar=("X", "Y"))
    parser.add_argument("--crf", type=int, default=17)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    report_path = args.report or args.output.with_suffix(".json")
    if report_path.exists():
        raise FileExistsError(report_path)

    with av.open(str(args.input)) as source:
        source_stream = source.streams.video[0]
        fps = source_stream.average_rate or Fraction(24, 1)
        width = source_stream.codec_context.width
        height = source_stream.codec_context.height
        frames = [frame.to_ndarray(format="rgb24") for frame in source.decode(video=0)]
    if not frames:
        raise RuntimeError("input decoded no frames")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    guard = np.asarray(args.guard, dtype=np.float32)
    tip = np.asarray(args.tip, dtype=np.float32)
    with av.open(str(args.output), mode="w", options={"movflags": "+faststart"}) as target:
        stream = target.add_stream("libx264", rate=fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": str(args.crf), "preset": "slow", "tune": "animation", "profile": "high"}
        for index, base in enumerate(frames):
            overlay = packet_overlay(width, height, index, DEFAULT_PASSES, guard, tip)
            composited = screen_composite(base, overlay)
            video_frame = av.VideoFrame.from_ndarray(composited, format="rgb24")
            video_frame.pts = index
            video_frame.time_base = Fraction(fps.denominator, fps.numerator)
            for packet in stream.encode(video_frame):
                target.mux(packet)
        for packet in stream.encode():
            target.mux(packet)

    report = {
        "schema_version": 1,
        "kind": "elegant_sword_filament_composite",
        "input": str(args.input.resolve()),
        "output": str(args.output.resolve()),
        "frames": len(frames),
        "fps": float(fps),
        "size": [width, height],
        "guard": list(args.guard),
        "tip": list(args.tip),
        "passes": [list(item) for item in DEFAULT_PASSES],
        "bundle_strands": 3,
        "boundary_dark_frames": {"start": [0, 7], "end": [63, len(frames) - 1]},
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"output={args.output.resolve()}")
    print(f"report={report_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
