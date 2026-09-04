#!/usr/bin/env python3
"""Rank H3 seed candidates for a seamless-loop wallpaper master.

Watching six 3-second clips blind is a poor use of a human. This measures the
four things that actually disqualify a candidate for looping, so only the top
one or two need a real viewing:

* loop closure    - how far the last frame drifted from the first, split into
                    subject and background the same way analyze_text_to_live2d.py does.
                    Used for return-to-start ranking; ignored as a cost under mirror
                    playback, where the last frame is supposed to be an extrema;
* rigid regions   - motion inside boxes that are supposed to be scenery. For the
                    Keqing night-garden shot that is the translucent crystal ribbon
                    in the lower foreground and the petals resting on the stone floor;
* blink           - how much of the eye band's dark iris and pupil area survives. Closing
                    an eyelid replaces dark iris with skin-toned lid, so a complete blink
                    makes the dark fraction collapse towards zero while a half-closed lid
                    only dents it. Tracking luma alone gets this backwards, since a closing
                    eye makes the band brighter, not darker;
* travel          - whether a region ends where it started, which catches petals or
                    particles that drift one way across the clip. Still fatal under
                    mirror playback: reverse playback would make fallen petals fly up;
* turning extrema - last adjacent-frame MAD relative to the clip mean. Mirror playback
                    reverses at the last source frame, so that frame needs near-zero
                    velocity or the turn will hitch. First-order MAD does not spike at
                    the turn; the visible hitch is the second difference, whose proxy
                    is twice the last step.

The default boxes are eyeballed from one fixed composition and a locked-off
camera. They are indicative, not a gate: override them for any other shot, and
confirm the shortlist by eye before committing to an expensive master.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import av
import numpy as np

LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float64)

# Fractions of width/height: (left, top, right, bottom). Verified against frame 0 of
# the keqing_gpt_reference_16x9 composition: the eye box holds both eyes with almost no
# bangs, and the crystal box holds the translucent foreground ribbon while staying left
# of her legs, which do move and would otherwise contaminate a "rigid region" reading.
DEFAULT_REGIONS = {
    "eye_band": (0.505, 0.185, 0.575, 0.225),
    "foreground_crystal": (0.28, 0.58, 0.47, 0.90),
    "ground_petals": (0.00, 0.80, 1.00, 1.00),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("videos", nargs="+", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--region", action="append", default=[],
                        help="name=left,top,right,bottom as width/height fractions; repeatable, replaces a default")
    parser.add_argument(
        "--loop-mode",
        choices=("return", "mirror"),
        default="mirror",
        help="return ranks first-to-last closure; mirror ranks turning-point extrema",
    )
    parser.add_argument("--sort-by", default="loop_score",
                        choices=("loop_score", "endpoint_full_mad", "foreground_crystal_step_mad",
                                 "motion_step_last_ratio"))
    return parser.parse_args()


def parse_regions(overrides: list[str]) -> dict[str, tuple[float, float, float, float]]:
    regions = dict(DEFAULT_REGIONS)
    for item in overrides:
        name, _, values = item.partition("=")
        parts = [float(value) for value in values.split(",")]
        if len(parts) != 4:
            raise ValueError(f"--region {item!r} needs four fractions")
        left, top, right, bottom = parts
        if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
            raise ValueError(f"--region {item!r} is not an ordered box inside [0,1]")
        regions[name.strip()] = (left, top, right, bottom)
    return regions


def box_slice(box: tuple[float, float, float, float], width: int, height: int):
    left, top, right, bottom = box
    return (slice(int(top * height), max(int(bottom * height), int(top * height) + 1)),
            slice(int(left * width), max(int(right * width), int(left * width) + 1)))


def mad(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.abs(first - second).mean())


def measure(video: Path, regions: dict[str, tuple[float, float, float, float]]) -> dict[str, Any]:
    """Stream the clip once, keeping only the first frame, the previous frame and per-frame scalars."""
    first: np.ndarray | None = None
    previous: np.ndarray | None = None
    last: np.ndarray | None = None
    steps: list[float] = []
    region_steps: dict[str, list[float]] = {name: [] for name in regions}
    eye_dark_fraction: list[float] = []
    eye_threshold: float | None = None
    frames = 0

    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        width, height = stream.codec_context.width, stream.codec_context.height
        fps = float(stream.average_rate) if stream.average_rate is not None else None
        boxes = {name: box_slice(box, width, height) for name, box in regions.items()}
        for frame in container.decode(video=0):
            current = frame.to_ndarray(format="rgb24").astype(np.float64)
            frames += 1
            if first is None:
                first = current
            if previous is not None:
                steps.append(mad(previous, current))
                for name, region in boxes.items():
                    region_steps[name].append(mad(previous[region], current[region]))
            if "eye_band" in boxes:
                band = current[boxes["eye_band"]] @ LUMA
                if eye_threshold is None:
                    # Everything darker than the open eye's 30th percentile is iris, pupil
                    # and lash. A closing lid covers those pixels with bright skin.
                    eye_threshold = float(np.percentile(band, 30))
                eye_dark_fraction.append(float((band < eye_threshold).mean()))
            previous = current
            last = current

    if first is None or last is None:
        raise RuntimeError(f"{video} decoded no frames")

    subject = (slice(int(height * 0.02), int(height * 0.99)), slice(int(width * 0.25), int(width * 0.75)))
    background = np.ones((height, width), dtype=bool)
    background[subject] = False

    result: dict[str, Any] = {
        "video": str(video.resolve()),
        "name": video.name,
        "frames": frames,
        "width": width,
        "height": height,
        "fps": fps,
        "endpoint_full_mad": mad(first, last),
        "endpoint_subject_mad": mad(first[subject], last[subject]),
        "endpoint_background_mad": mad(first[background], last[background]),
        "motion_step_mean_mad": float(np.mean(steps)) if steps else None,
        "motion_step_max_mad": float(np.max(steps)) if steps else None,
        "motion_step_first_mad": float(steps[0]) if steps else None,
        "motion_step_last_mad": float(steps[-1]) if steps else None,
        "motion_step_last_ratio": (
            float(steps[-1] / np.mean(steps)) if steps and np.mean(steps) else None
        ),
        "motion_step_last5_mean_mad": float(np.mean(steps[-5:])) if len(steps) >= 5 else None,
        "turn_jerk_proxy_mad": float(2.0 * steps[-1]) if steps else None,
    }

    for name, region in boxes.items():
        values = np.array(region_steps[name], dtype=np.float64)
        result[f"{name}_step_mad"] = float(values.mean()) if values.size else None
        result[f"{name}_endpoint_mad"] = mad(first[region], last[region])

    if eye_dark_fraction:
        series = np.array(eye_dark_fraction, dtype=np.float64)
        open_level = max(series[0], 1e-6)
        openness = series / open_level
        closed_index = int(openness.argmin())
        result["eye_open_dark_fraction"] = float(series[0])
        result["eye_min_openness"] = float(openness.min())
        result["eye_min_openness_frame"] = closed_index
        result["eye_openness_at_last_frame"] = float(openness[-1])
        result["eye_closed_at_boundary"] = bool(closed_index < 3 or closed_index > frames - 4)
    return result


def loop_score_return(row: dict[str, Any]) -> float:
    """Lower is better. Ranks clips that must return to the first frame."""
    score = float(row["endpoint_full_mad"])
    score += 2.0 * float(row.get("foreground_crystal_step_mad") or 0.0)
    score += 1.0 * float(row.get("ground_petals_endpoint_mad") or 0.0)
    last_eye = row.get("eye_openness_at_last_frame")
    if last_eye is not None:
        score += 5.0 * abs(1.0 - float(last_eye))
    return score


def loop_score_mirror(row: dict[str, Any]) -> float:
    """Lower is better. Ranks clips whose last frame is a motion extrema.

    endpoint_full_mad is not a cost: the last frame is supposed to differ from the
    first. Petal travel still is, because reverse playback cannot hide gravity.
    last_step_ratio near 1 means the clip is still moving at full speed into the
    turn; near 0 means it has already stopped.
    """
    score = 2.0 * float(row.get("foreground_crystal_step_mad") or 0.0)
    score += 1.5 * float(row.get("ground_petals_endpoint_mad") or 0.0)
    last_ratio = row.get("motion_step_last_ratio")
    if last_ratio is not None:
        score += 3.0 * float(last_ratio)
    if row.get("eye_min_openness") is not None:
        score += 2.0 * float(row["eye_min_openness"])
    last_eye = row.get("eye_openness_at_last_frame")
    if last_eye is not None:
        score += 5.0 * abs(1.0 - float(last_eye))
    if row.get("eye_closed_at_boundary"):
        score += 5.0
    return score


def loop_score(row: dict[str, Any], mode: str) -> float:
    if mode == "mirror":
        return loop_score_mirror(row)
    if mode == "return":
        return loop_score_return(row)
    raise ValueError(f"unknown loop mode: {mode!r}")


def main() -> int:
    args = parse_args()
    regions = parse_regions(args.region)
    rows = [measure(video, regions) for video in args.videos]
    for row in rows:
        row["loop_mode"] = args.loop_mode
        row["loop_score"] = loop_score(row, args.loop_mode)
    rows.sort(key=lambda row: row[args.sort_by])

    header = (f"{'candidate':<52}{'score':>7}{'endMAD':>8}{'lastR':>7}{'crystal':>9}"
              f"{'ground':>8}{'eyeMin':>8}{'frame':>7}{'lastEye':>9}")
    print(header)
    print("-" * len(header))
    for row in rows:
        name = row["name"]
        if len(name) > 51:
            name = name[:24] + "..." + name[-24:]
        print(f"{name:<52}"
              f"{row['loop_score']:>7.2f}"
              f"{row['endpoint_full_mad']:>8.2f}"
              f"{(row.get('motion_step_last_ratio') if row.get('motion_step_last_ratio') is not None else -1):>7.2f}"
              f"{(row.get('foreground_crystal_step_mad') or 0):>9.3f}"
              f"{(row.get('ground_petals_endpoint_mad') or 0):>8.2f}"
              f"{(row.get('eye_min_openness') if row.get('eye_min_openness') is not None else -1):>8.2f}"
              f"{(row.get('eye_min_openness_frame') if row.get('eye_min_openness_frame') is not None else -1):>7d}"
              f"{(row.get('eye_openness_at_last_frame') if row.get('eye_openness_at_last_frame') is not None else -1):>9.2f}")

    print(f"\nloop-mode = {args.loop_mode} (lower score is better)")
    print("columns: lastR   = last adjacent-frame MAD / clip mean; want << 1 so the turn is an extrema")
    print("         crystal = mean adjacent-frame motion inside the rigid foreground box (want ~0)")
    print("         ground  = first-to-last drift of the floor band (catches petals that travelled)")
    print("         eyeMin  = smallest surviving fraction of the open eye's dark area.")
    print("                   ~1.00 means the eyes never closed; lower means more closed.")
    print("                   The scale is relative and uncalibrated: no clip with a verified")
    print("                   fully-closed blink exists for this composition yet, so compare")
    print("                   candidates against each other rather than against a threshold")
    print("         frame   = frame index of that minimum; at either boundary it breaks the loop")
    print("         lastEye = eye openness on the final frame; ~1.00 with a mid-clip blink")
    if args.loop_mode == "return":
        print("         endMAD  = first-to-last drift; this is the primary cost in return mode")
    else:
        print("         endMAD  = first-to-last drift; reported but not scored in mirror mode")
    print("\nThese boxes assume the fixed Keqing night-garden composition and a locked-off camera.")
    print("Treat the ranking as a shortlist, then watch the top candidate before spending a 1080p master.")

    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 2,
            "kind": "h3_loop_candidate_screening",
            "command": [sys.executable, *sys.argv],
            "loop_mode": args.loop_mode,
            "regions": {name: list(box) for name, box in regions.items()},
            "sorted_by": args.sort_by,
            "candidates": rows,
        }
        args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nreport={args.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
