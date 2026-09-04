#!/usr/bin/env python3
"""Judge whether a wallpaper clip's motion speed stays even over time.

Related published ideas (none are drop-in for LoopLock wallpapers):
- Visual Chronometer / PhyFPS intra-video CV: sliding-window physical-FPS stability.
- VBench motion smoothness and interpolation Temporal Smoothness: optical-flow magnitude.
- Loop Findr / AutoLoop: frame-difference or flow magnitude plus min/max motion gates.

This script stays local and cheap: locked-region MAD, mean color shift, and Farneback
flow magnitude. A wallpaper idle should keep a small, nearly constant speed except for
a mid-clip blink; freeze, late acceleration, and wrap jumps are reported explicitly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import av
import cv2
import numpy as np

DEFAULT_REGIONS = {
    "full": (0.0, 0.0, 1.0, 1.0),
    "hair": (0.42, 0.08, 0.78, 0.42),
    "crystal": (0.28, 0.58, 0.47, 0.90),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("videos", nargs="+", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--region",
        action="append",
        default=[],
        help="name=left,top,right,bottom as width/height fractions; repeatable",
    )
    parser.add_argument("--csv-dir", type=Path)
    parser.add_argument("--flow-width", type=int, default=480)
    parser.add_argument("--flag-cv", type=float, default=0.55)
    parser.add_argument("--flag-tail-fast", type=float, default=1.45)
    parser.add_argument("--flag-tail-slow", type=float, default=0.55)
    parser.add_argument("--flag-last-ratio", type=float, default=0.40)
    parser.add_argument("--flag-spike", type=float, default=4.0)
    parser.add_argument("--flag-wrap", type=float, default=2.5)
    return parser.parse_args()


def parse_regions(overrides: list[str]) -> dict[str, tuple[float, float, float, float]]:
    regions = dict(DEFAULT_REGIONS)
    for item in overrides:
        name, _, values = item.partition("=")
        parts = [float(value) for value in values.split(",")]
        if len(parts) != 4:
            raise ValueError(f"Bad region {item!r}; expected name=l,t,r,b")
        regions[name] = (parts[0], parts[1], parts[2], parts[3])
    return regions


def box_slice(box: tuple[float, float, float, float], width: int, height: int):
    left, top, right, bottom = box
    return (
        slice(int(top * height), max(int(bottom * height), int(top * height) + 1)),
        slice(int(left * width), max(int(right * width), int(left * width) + 1)),
    )


def mad(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.abs(first.astype(np.int16) - second.astype(np.int16)).mean())


def color_shift(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.abs(first.mean(axis=(0, 1)) - second.mean(axis=(0, 1))).mean())


def summarize(values: np.ndarray) -> dict[str, float]:
    if values.size == 0:
        return {}
    mean = float(values.mean())
    median = float(np.median(values))
    std = float(values.std())
    return {
        "mean": round(mean, 4),
        "median": round(median, 4),
        "std": round(std, 4),
        "cv": round(std / mean, 4) if mean > 1e-8 else None,
        "p10": round(float(np.percentile(values, 10)), 4),
        "p90": round(float(np.percentile(values, 90)), 4),
        "max": round(float(values.max()), 4),
        "min": round(float(values.min()), 4),
        "first": round(float(values[0]), 4),
        "last": round(float(values[-1]), 4),
        "last_ratio": round(float(values[-1] / mean), 4) if mean > 1e-8 else None,
        "last5_mean": round(float(values[-5:].mean()), 4) if values.size >= 5 else round(float(values.mean()), 4),
    }


def window_means(values: np.ndarray, count: int = 8) -> list[float]:
    if values.size == 0:
        return []
    edges = np.linspace(0, values.size, count + 1, dtype=int)
    return [round(float(values[edges[i] : edges[i + 1]].mean()), 4) for i in range(count) if edges[i + 1] > edges[i]]


def section_ratio(values: np.ndarray, start: float, end: float, ref_start: float, ref_end: float) -> float | None:
    def slice_mean(a: float, b: float) -> float:
        i0 = int(round(a * (values.size - 1)))
        i1 = int(round(b * (values.size - 1))) + 1
        return float(values[max(i0, 0) : min(i1, values.size)].mean())

    ref = slice_mean(ref_start, ref_end)
    if ref <= 1e-8:
        return None
    return round(slice_mean(start, end) / ref, 4)


def flags_for(
    speed: np.ndarray, wrap: float, median: float, thresholds: dict[str, float]
) -> list[str]:
    flags: list[str] = []
    if speed.size == 0 or median <= 1e-8:
        return ["no_motion"]
    mean = float(speed.mean())
    cv = float(speed.std() / mean) if mean > 1e-8 else 0.0
    tail = section_ratio(speed, 0.80, 1.00, 0.25, 0.75)
    last_ratio = float(speed[-1] / mean)
    if cv > thresholds["cv"]:
        flags.append("speed_unstable")
    if last_ratio < thresholds["last_ratio"]:
        flags.append("end_freeze")
    if tail is not None and tail > thresholds["tail_fast"]:
        flags.append("tail_too_fast")
    if tail is not None and tail < thresholds["tail_slow"]:
        flags.append("tail_too_slow")
    if float(speed.max()) > thresholds["spike"] * median:
        flags.append("motion_spike")
    if wrap > thresholds["wrap"] * max(median, 1e-8):
        flags.append("loop_wrap_jump")
    if not flags:
        flags.append("even_enough")
    return flags


def measure(
    video: Path,
    regions: dict[str, tuple[float, float, float, float]],
    flow_width: int,
    thresholds: dict[str, float],
) -> dict[str, Any]:
    first = None
    prev_rgb = None
    prev_gray = None
    last = None
    frames = 0
    global_steps: list[float] = []
    region_mad: dict[str, list[float]] = {name: [] for name in regions}
    region_color: dict[str, list[float]] = {name: [] for name in regions}
    region_flow: dict[str, list[float]] = {name: [] for name in regions}

    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        width, height = stream.codec_context.width, stream.codec_context.height
        fps = float(stream.average_rate) if stream.average_rate is not None else None
        boxes = {name: box_slice(box, width, height) for name, box in regions.items()}
        scale = flow_width / float(width)
        flow_size = (flow_width, max(int(round(height * scale)), 1))
        for frame in container.decode(video=0):
            rgb = frame.to_ndarray(format="rgb24")
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            small = cv2.resize(gray, flow_size, interpolation=cv2.INTER_AREA)
            frames += 1
            if first is None:
                first = rgb.copy()
            if prev_rgb is not None:
                global_steps.append(mad(prev_rgb, rgb))
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray, small, None, 0.5, 3, 15, 3, 5, 1.2, 0
                )
                mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
                for name, region in boxes.items():
                    region_mad[name].append(mad(prev_rgb[region], rgb[region]))
                    region_color[name].append(color_shift(prev_rgb[region], rgb[region]))
                    fy, fx = region
                    sy = slice(
                        int(fy.start * scale),
                        max(int(fy.stop * scale), int(fy.start * scale) + 1),
                    )
                    sx = slice(
                        int(fx.start * scale),
                        max(int(fx.stop * scale), int(fx.start * scale) + 1),
                    )
                    region_flow[name].append(float(mag[sy, sx].mean()))
            prev_rgb = rgb
            prev_gray = small
            last = rgb

    if first is None or last is None:
        raise RuntimeError(f"{video} decoded no frames")

    wrap = mad(first, last)
    speed = np.array(region_flow.get("hair") or global_steps, dtype=np.float64)
    median = float(np.median(speed)) if speed.size else 0.0
    result: dict[str, Any] = {
        "video": str(video.resolve()),
        "name": video.name,
        "frames": frames,
        "width": width,
        "height": height,
        "fps": fps,
        "wrap_mad": round(wrap, 4),
        "global_mad": summarize(np.array(global_steps, dtype=np.float64)),
        "speed_windows": window_means(speed),
        "head_vs_mid": section_ratio(speed, 0.00, 0.20, 0.25, 0.75),
        "tail_vs_mid": section_ratio(speed, 0.80, 1.00, 0.25, 0.75),
        "flags": flags_for(speed, wrap, median, thresholds),
        "flag_thresholds": thresholds,
        "regions": {},
        "series": {
            "global_mad": [round(float(x), 4) for x in global_steps],
        },
    }
    for name in regions:
        mad_arr = np.array(region_mad[name], dtype=np.float64)
        color_arr = np.array(region_color[name], dtype=np.float64)
        flow_arr = np.array(region_flow[name], dtype=np.float64)
        result["regions"][name] = {
            "mad": summarize(mad_arr),
            "color_shift": summarize(color_arr),
            "flow_mag": summarize(flow_arr),
        }
        result["series"][f"{name}_mad"] = [round(float(x), 4) for x in mad_arr]
        result["series"][f"{name}_color_shift"] = [round(float(x), 4) for x in color_arr]
        result["series"][f"{name}_flow_mag"] = [round(float(x), 4) for x in flow_arr]
    return result


def write_csv(row: dict[str, Any], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{Path(row['name']).stem}_speed.csv"
    length = max(len(values) for values in row["series"].values())
    with path.open("w", encoding="utf-8") as handle:
        handle.write("step," + ",".join(row["series"].keys()) + "\n")
        for index in range(length):
            cells = [str(index)]
            for values in row["series"].values():
                cells.append("" if index >= len(values) else str(values[index]))
            handle.write(",".join(cells) + "\n")
    return path


def print_row(row: dict[str, Any]) -> None:
    hair = row["regions"].get("hair", {}).get("flow_mag", {})
    crystal = row["regions"].get("crystal", {}).get("flow_mag", {})
    print(f"==== {row['name']}")
    print(
        f"  frames={row['frames']} fps={row['fps']} wrap={row['wrap_mad']} "
        f"flags={','.join(row['flags'])}"
    )
    print(
        f"  hair_flow mean={hair.get('mean')} cv={hair.get('cv')} "
        f"last_ratio={hair.get('last_ratio')} tail/mid={row['tail_vs_mid']} "
        f"windows={row['speed_windows']}"
    )
    print(
        f"  crystal_flow mean={crystal.get('mean')} cv={crystal.get('cv')} "
        f"max={crystal.get('max')}"
    )


def main() -> int:
    args = parse_args()
    regions = parse_regions(args.region)
    thresholds = {
        "cv": args.flag_cv,
        "tail_fast": args.flag_tail_fast,
        "tail_slow": args.flag_tail_slow,
        "last_ratio": args.flag_last_ratio,
        "spike": args.flag_spike,
        "wrap": args.flag_wrap,
    }
    rows = []
    for video in args.videos:
        if not video.is_file():
            raise FileNotFoundError(video)
        print(f"analyzing {video.name}", flush=True)
        row = measure(video, regions, args.flow_width, thresholds)
        if args.csv_dir:
            row["csv"] = str(write_csv(row, args.csv_dir))
        rows.append(row)
        print_row(row)
    if args.report:
        slim = []
        for row in rows:
            slim.append({key: value for key, value in row.items() if key != "series"})
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(slim, indent=2), encoding="utf-8")
        print(f"report={args.report.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
