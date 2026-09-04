#!/usr/bin/env python3
"""Densify first, then drop frames so loop speed stays close to in-clip speed.

Fast intervals, including last->first, get extra optical-flow interpolants.
Slow interpolants are discarded by equal-arc sampling with endpoint=False, so
the last kept frame still has residual speed into the first frame.

LIMITATION: the motion proxy is global full-resolution MAD with no region
lock, so background shimmer or compression flicker counts as motion. Prefer
equalize_motion_speed.py (locked region + flow) when the subject occupies a
known box; use this script when no external RIFE clip is available.

MEMORY: the source is decoded streaming (never a full-res list), and the
dense sequence spills to a temp mp4 instead of living in RAM. Only a handful
of full-res frames (first/last/previous/current) are resident, so 4K and long
clips stay flat in memory. The temp file is removed on exit, success or not.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mad(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


def source_info(path: Path) -> tuple[float, int, int]:
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate) if stream.average_rate is not None else 90.0
        return fps, stream.codec_context.width, stream.codec_context.height


def iter_source_rgb(path: Path):
    """Yield full-res RGB frames one at a time (streaming, no list)."""
    with av.open(str(path)) as container:
        for frame in container.decode(video=0):
            yield frame.to_ndarray(format="rgb24")


def flow_pair(prev: np.ndarray, nxt: np.ndarray) -> np.ndarray:
    gray_a = cv2.cvtColor(prev, cv2.COLOR_RGB2GRAY)
    gray_b = cv2.cvtColor(nxt, cv2.COLOR_RGB2GRAY)
    return cv2.calcOpticalFlowFarneback(gray_a, gray_b, None, 0.5, 5, 21, 3, 7, 1.5, 0)


def warp(image: np.ndarray, flow: np.ndarray, amount: float) -> np.ndarray:
    height, width = flow.shape[:2]
    grid_x, grid_y = np.meshgrid(
        np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32)
    )
    map_x = (grid_x + flow[..., 0] * amount).astype(np.float32)
    map_y = (grid_y + flow[..., 1] * amount).astype(np.float32)
    return cv2.remap(
        image, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
    )


def interpolate_pair(first: np.ndarray, last: np.ndarray, count: int) -> list[np.ndarray]:
    if count <= 0:
        return []
    forward = flow_pair(first, last)
    backward = flow_pair(last, first)
    frames = []
    for index in range(1, count + 1):
        amount = index / (count + 1)
        from_first = warp(first, forward, amount)
        from_last = warp(last, backward, 1.0 - amount)
        blended = (1.0 - amount) * from_first.astype(np.float32) + amount * from_last.astype(np.float32)
        frames.append(np.clip(blended, 0, 255).astype(np.uint8))
    return frames


def extra_count(step: float, target: float) -> int:
    return max(0, int(round(step / max(target, 1e-8))) - 1)


def plan_loop(steps: np.ndarray, n_out: int, last_keep: int) -> list[int]:
    cumulative = np.concatenate(([0.0], np.cumsum(steps)))
    total = float(cumulative[-1])
    samples = np.linspace(0.0, total, n_out, endpoint=False)
    pos = np.interp(samples, cumulative, np.arange(len(cumulative), dtype=np.float64))
    raw = np.clip(np.rint(pos).astype(np.int64), 0, last_keep)
    selected: list[int] = []
    for index in raw.tolist():
        if not selected or selected[-1] != int(index):
            selected.append(int(index))
    if selected[0] != 0:
        selected.insert(0, 0)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--fps", type=float, default=90.0)
    parser.add_argument("--crf", type=int, default=10)
    parser.add_argument(
        "--dense-crf",
        type=int,
        default=12,
        help="CRF for the temporary dense spill file. Planning steps are measured "
        "on raw pixels before the spill, so this only affects final pixels.",
    )
    parser.add_argument("--wrap-multiplier", type=float, default=4.0)
    parser.add_argument(
        "--min-wrap",
        type=int,
        default=0,
        help="Floor on wrap interpolants. Default 0 (inject only what the wrap "
        "motion asks for); a static seam gets no forced ghost blends.",
    )
    parser.add_argument(
        "--max-dense-frames",
        type=int,
        default=20000,
        help="Sanity bound on the dense spill size (frames).",
    )
    parser.add_argument("--preview-dir", type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    report_path = args.report.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    for path in (output, report_path):
        if path.exists():
            raise FileExistsError(f"Refusing to replace: {path}")
    if args.csv is not None and args.csv.exists():
        raise FileExistsError(args.csv)
    if args.preview_dir is not None and args.preview_dir.exists() and any(args.preview_dir.iterdir()):
        raise FileExistsError(args.preview_dir)

    source_fps, width, height = source_info(source)

    # Pass 0 (streaming): in-clip MADs, frame count, first/last frames.
    # Only scalar MADs accumulate; a single frame is resident at a time
    # (plus one kept copy of the first frame for the wrap interpolants).
    in_clip: list[float] = []
    first_rgb: np.ndarray | None = None
    prev: np.ndarray | None = None
    source_count = 0
    for rgb in iter_source_rgb(source):
        if first_rgb is None:
            first_rgb = rgb.copy()
        if prev is not None:
            in_clip.append(mad(prev, rgb))
        prev = rgb
        source_count += 1
    if source_count < 2 or first_rgb is None or prev is None:
        raise RuntimeError("Need at least two frames")
    last_rgb = prev
    in_clip_arr = np.array(in_clip, dtype=np.float64)
    wrap_before = mad(last_rgb, first_rgb)
    healthy = in_clip_arr[in_clip_arr > np.percentile(in_clip_arr, 20)]
    target = float(np.median(healthy) if healthy.size else np.median(in_clip_arr))
    extra_counts = [extra_count(step, target) for step in in_clip]
    in_clip_extra = sum(extra_counts)
    wrap_extra = max(args.min_wrap, int(round(wrap_before / max(target, 1e-8) * args.wrap_multiplier)))
    dense_estimate = source_count + in_clip_extra + wrap_extra
    resident_gib = dense_estimate * width * height * 3 / (1024**3)
    print(
        f"dense estimate: {dense_estimate} frames "
        f"(~{resident_gib:.2f} GiB if resident; spilling to temp)"
    )
    if dense_estimate > args.max_dense_frames:
        raise RuntimeError(
            f"Dense estimate {dense_estimate} exceeds --max-dense-frames {args.max_dense_frames}"
        )

    tmp_path = Path(tempfile.NamedTemporaryFile(
        delete=False, suffix=".mp4", prefix="eqloop_dense_"
    ).name)
    try:
        # Pass 1 (streaming): generate the dense sequence into the temp file.
        # Steps are measured on RAW pixels before the spill, so planning is
        # identical to the old in-RAM version; only final pixels pass through
        # the temp codec.
        rate = Fraction(str(args.fps)).limit_denominator()
        dense_steps: list[float] = []
        dense_count = 0
        last_raw: np.ndarray | None = None
        with av.open(str(tmp_path), "w", options={"movflags": "+faststart"}) as container:
            stream = container.add_stream("libx264", rate=rate)
            stream.width = width
            stream.height = height
            stream.pix_fmt = "yuv420p"
            stream.options = {
                "crf": str(args.dense_crf),
                "preset": "veryfast",
                "tune": "animation",
                "profile": "high",
            }

            def emit(raw: np.ndarray) -> None:
                nonlocal dense_count, last_raw
                if last_raw is not None:
                    dense_steps.append(mad(last_raw, raw))
                frame = av.VideoFrame.from_ndarray(raw, format="rgb24")
                converted = frame.reformat(width=width, height=height, format="yuv420p")
                converted.pts = dense_count
                converted.time_base = Fraction(rate.denominator, rate.numerator)
                for packet in stream.encode(converted):
                    container.mux(packet)
                dense_count += 1
                last_raw = raw

            prev = None
            pair_index = 0
            for cur in iter_source_rgb(source):
                if prev is None:
                    emit(cur)
                else:
                    for mid in interpolate_pair(prev, cur, extra_counts[pair_index]):
                        emit(mid)
                    emit(cur)
                    pair_index += 1
                prev = cur
            for mid in interpolate_pair(last_rgb, first_rgb, wrap_extra):
                emit(mid)
            for packet in stream.encode():
                container.mux(packet)
        if last_raw is None:
            raise RuntimeError("Dense spill is empty")
        dense_steps.append(mad(last_raw, first_rgb))

        steps = np.array(dense_steps, dtype=np.float64)
        n_out = max(2, int(round(source_count / max(source_fps, 1e-8) * args.fps)))
        selected = plan_loop(steps, n_out, last_keep=dense_count - 1)

        # Pass 2 (streaming): pick selected dense frames out of temp, encode final.
        by_index: dict[int, list[int]] = {}
        for out_i, dense_index in enumerate(selected):
            by_index.setdefault(int(dense_index), []).append(out_i)
        emitted = 0
        first_two: list[np.ndarray] = []
        prev_emit: np.ndarray | None = None
        last_emit: np.ndarray | None = None
        output.parent.mkdir(parents=True, exist_ok=True)
        with av.open(str(tmp_path)) as in_container, av.open(
            str(output), "w", options={"movflags": "+faststart"}
        ) as out_container:
            ostream = out_container.add_stream("libx264", rate=rate)
            ostream.width = width
            ostream.height = height
            ostream.pix_fmt = "yuv420p"
            ostream.options = {
                "crf": str(args.crf),
                "preset": "slow",
                "tune": "animation",
                "profile": "high",
            }
            for dense_index, frame in enumerate(in_container.decode(video=0)):
                if dense_index not in by_index:
                    continue
                rgb = frame.to_ndarray(format="rgb24")
                for out_i in by_index[dense_index]:
                    converted = frame.reformat(width=width, height=height, format="yuv420p")
                    converted.pts = out_i
                    converted.time_base = Fraction(rate.denominator, rate.numerator)
                    for packet in ostream.encode(converted):
                        out_container.mux(packet)
                    if emitted < 2:
                        first_two.append(rgb.copy())
                    prev_emit, last_emit = last_emit, rgb.copy()
                    emitted += 1
            for packet in ostream.encode():
                out_container.mux(packet)
        if emitted != len(selected):
            raise RuntimeError(f"Emitted {emitted} frames, selected {len(selected)}")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    wrap_start = dense_count - wrap_extra
    wrap_kept = sum(1 for index in selected if index >= wrap_start)
    rgb_last_step = mad(prev_emit, last_emit) if prev_emit is not None and last_emit is not None and emitted > 1 else None
    rgb_first_step = mad(first_two[0], first_two[1]) if len(first_two) > 1 else None
    rgb_wrap = mad(last_emit, first_rgb) if last_emit is not None else None

    if args.csv is not None:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", encoding="utf-8") as handle:
            handle.write("dense_index,mad,kind\n")
            for index, value in enumerate(steps.tolist()):
                kind = "wrap" if index >= wrap_start else "in_clip"
                handle.write(f"{index},{value:.6f},{kind}\n")

    if args.preview_dir is not None:
        from PIL import Image

        args.preview_dir.mkdir(parents=True, exist_ok=True)
        if len(first_two) > 0:
            Image.fromarray(first_two[0]).save(args.preview_dir / "out_first.png")
        if len(first_two) > 1:
            Image.fromarray(first_two[1]).save(args.preview_dir / "out_second.png")
        if prev_emit is not None:
            Image.fromarray(prev_emit).save(args.preview_dir / "out_second_last.png")
        if last_emit is not None:
            Image.fromarray(last_emit).save(args.preview_dir / "out_last.png")

    report = {
        "schema_version": 1,
        "status": "success",
        "method": "densify_then_equal_arc_drop_loop",
        "motion_proxy": "global_mad_fullres_no_region_lock",
        "source": str(source),
        "source_sha256": sha256(source),
        "output": str(output),
        "output_sha256": sha256(output),
        "source_frames": source_count,
        "source_fps": source_fps,
        "dense_frames": dense_count,
        "dense_spilled_to_temp": True,
        "dense_crf": args.dense_crf,
        "max_dense_frames": args.max_dense_frames,
        "in_clip_extra_interpolants": in_clip_extra,
        "wrap_interpolants": wrap_extra,
        "wrap_frames_kept": wrap_kept,
        "last_selected_dense_index": selected[-1],
        "output_frames": emitted,
        "output_fps": args.fps,
        "duration_seconds": emitted / args.fps,
        "in_clip_mad_mean": float(in_clip_arr.mean()),
        "target_step_mad": target,
        "wrap_mad_before": wrap_before,
        "requested_frames": n_out,
        "rgb_last_step": rgb_last_step,
        "rgb_first_step": rgb_first_step,
        "rgb_last_to_first": rgb_wrap,
        "crf": args.crf,
        "selected_dense_indexes": selected,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    printable = {key: value for key, value in report.items() if key != "selected_dense_indexes"}
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(printable, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
