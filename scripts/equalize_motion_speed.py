#!/usr/bin/env python3
"""Retimes a clip to nearly constant visual speed at a fixed FPS.

Slow intervals are skipped (deletion). Fast intervals, including the loop wrap
from last frame to first, are stretched by sampling RIFE in-betweens. Sampling
is equal arc-length on locked-region optical-flow magnitude.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--rife-video", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--wrap-rife-video", type=Path,
                        help="Non-cyclic RIFE of last+first source frames, used when --loop")
    parser.add_argument("--fps", type=float, default=24.0)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--keep-duration", action="store_true")
    parser.add_argument("--flow-width", type=int, default=480)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument(
        "--region",
        required=True,
        help="Locked motion-measurement region as left,top,right,bottom fractions "
        "(e.g. 0.42,0.08,0.78,0.42). No default: it must match the subject of "
        "THIS video, otherwise the speed estimate measures the wrong thing.",
    )
    parser.add_argument(
        "--metric",
        choices=("max", "appearance", "flow"),
        default="max",
        help="Per-frame speed: appearance MAD, optical flow, or max(flow, appearance/4)",
    )
    parser.add_argument(
        "--wrap-budget-mode",
        choices=("path", "coarse"),
        default="path",
        help="path: budget wrap frames from measured micro-steps along the wrap "
        "interpolants (same scale as in-clip steps). coarse: legacy single "
        "last->first step (underestimates curved wrap paths).",
    )
    parser.add_argument("--write-wrap-pair", type=Path,
                        help="Write a 2-frame last-then-first video from --source and exit")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_box(text: str) -> tuple[float, float, float, float]:
    parts = [float(item) for item in text.split(",")]
    if len(parts) != 4:
        raise ValueError("region must be left,top,right,bottom")
    return parts[0], parts[1], parts[2], parts[3]


def box_slice(box: tuple[float, float, float, float], width: int, height: int):
    left, top, right, bottom = box
    return (
        slice(int(top * height), max(int(bottom * height), int(top * height) + 1)),
        slice(int(left * width), max(int(right * width), int(left * width) + 1)),
    )


def write_wrap_pair(source: Path, output: Path) -> dict:
    frames = []
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate) if stream.average_rate is not None else 24.0
        for frame in container.decode(video=0):
            frames.append(frame)
        if len(frames) < 2:
            raise RuntimeError("Source needs at least two frames")
        first, last = frames[0], frames[-1]
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise FileExistsError(output)
        rate = Fraction(str(fps))
        with av.open(str(output), "w", options={"movflags": "+faststart"}) as out:
            ostream = out.add_stream("libx264", rate=rate)
            ostream.width = stream.codec_context.width
            ostream.height = stream.codec_context.height
            ostream.pix_fmt = "yuv420p"
            ostream.options = {"crf": "18", "preset": "slow", "tune": "animation", "profile": "high"}
            for index, item in enumerate((last, first)):
                converted = item.reformat(
                    width=ostream.width, height=ostream.height, format="yuv420p"
                )
                converted.pts = index
                converted.time_base = Fraction(rate.denominator, rate.numerator)
                for packet in ostream.encode(converted):
                    out.mux(packet)
            for packet in ostream.encode():
                out.mux(packet)
    return {"frames": 2, "order": ["last", "first"], "output": str(output.resolve())}


def iter_rgb(video: Path):
    with av.open(str(video)) as container:
        for frame in container.decode(video=0):
            yield frame.to_ndarray(format="rgb24")


def flow_mag(prev_small: np.ndarray, cur_small: np.ndarray, sy, sx) -> float:
    flow = cv2.calcOpticalFlowFarneback(prev_small, cur_small, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    return float(mag[sy, sx].mean())


def shrink_gray(rgb: np.ndarray, flow_size: tuple[int, int]) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return cv2.resize(gray, flow_size, interpolation=cv2.INTER_AREA)


def shrink_rgb(rgb: np.ndarray, flow_size: tuple[int, int]) -> np.ndarray:
    return cv2.resize(rgb, flow_size, interpolation=cv2.INTER_AREA)


def collect_dense(
    linear_video: Path,
    wrap_video: Path | None,
    loop: bool,
    source_frames: int,
) -> list[tuple[Path, int]]:
    """Map dense index -> (video, local index).

    Cyclic 4x of N source frames is N*4 long; the last 4 frames are the wrap.
    Linear path keeps [0, N*4 - 4], ending on the last source frame.
    Wrap RIFE of last+first is non-cyclic: local 0=last, last=first. Keep 1..-2
    so the seam is ground down without duplicating last or first.
    """
    linear_count = 0
    with av.open(str(linear_video)) as container:
        linear_count = sum(1 for _ in container.decode(video=0))
    mapping: list[tuple[Path, int]] = []
    if loop and wrap_video is not None:
        if linear_count % source_frames != 0:
            raise RuntimeError(
                f"Cannot align RIFE video to source: {linear_count} dense frames "
                f"is not a multiple of {source_frames} source frames; "
                "refusing silent fallback that would misalign the wrap seam"
            )
        multiplier = linear_count // source_frames
        # Keep through the last source frame, drop the cyclic wrap tail.
        linear_keep = linear_count - multiplier + 1
    else:
        linear_keep = linear_count
    mapping.extend((linear_video, index) for index in range(linear_keep))
    wrap_kept = 0
    if loop and wrap_video is not None:
        wrap_count = 0
        with av.open(str(wrap_video)) as container:
            wrap_count = sum(1 for _ in container.decode(video=0))
        # Keep interior interpolants only.
        interior = range(1, max(wrap_count - 1, 1))
        mapping.extend((wrap_video, index) for index in interior)
        wrap_kept = len(list(interior))
    if not mapping:
        raise RuntimeError("Dense mapping is empty")
    return mapping


def step_value(flow: float, appearance: float, metric: str) -> float:
    if metric == "flow":
        return float(flow)
    if metric == "appearance":
        return float(appearance)
    return float(max(flow, appearance / 4.0))


def measure_mapping(
    mapping: list[tuple[Path, int]],
    box: tuple[float, float, float, float],
    flow_width: int,
    close_loop: bool = False,
    metric: str = "max",
) -> np.ndarray:
    gray_by: dict[str, list[np.ndarray]] = {}
    rgb_by: dict[str, list[np.ndarray]] = {}
    width = height = 0
    flow_size = (flow_width, 1)
    for path in dict.fromkeys(item[0] for item in mapping):
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            width, height = stream.codec_context.width, stream.codec_context.height
            scale = flow_width / float(width)
            flow_size = (flow_width, max(int(round(height * scale)), 1))
        grays = []
        rgbs = []
        for rgb in iter_rgb(path):
            grays.append(shrink_gray(rgb, flow_size))
            rgbs.append(shrink_rgb(rgb, flow_size))
        gray_by[str(path)] = grays
        rgb_by[str(path)] = rgbs
    fy, fx = box_slice(box, width, height)
    scale = flow_width / float(width)
    sy = slice(int(fy.start * scale), max(int(fy.stop * scale), int(fy.start * scale) + 1))
    sx = slice(int(fx.start * scale), max(int(fx.stop * scale), int(fx.start * scale) + 1))
    grays = [gray_by[str(path)][index] for path, index in mapping]
    rgbs = [rgb_by[str(path)][index] for path, index in mapping]
    steps = []
    for i in range(len(grays) - 1):
        flow = flow_mag(grays[i], grays[i + 1], sy, sx)
        appearance = float(
            np.abs(rgbs[i][sy, sx].astype(np.int16) - rgbs[i + 1][sy, sx].astype(np.int16)).mean()
        )
        # Cross-dissolve wrap interpolants have little coherent flow but real MAD.
        steps.append(step_value(flow, appearance, metric))
    if close_loop and grays:
        flow = flow_mag(grays[-1], grays[0], sy, sx)
        appearance = float(
            np.abs(rgbs[-1][sy, sx].astype(np.int16) - rgbs[0][sy, sx].astype(np.int16)).mean()
        )
        steps.append(step_value(flow, appearance, metric))
    return np.array(steps, dtype=np.float64)


def appearance_step(rgb_a: np.ndarray, rgb_b: np.ndarray, sy, sx) -> float:
    return float(np.abs(rgb_a[sy, sx].astype(np.int16) - rgb_b[sy, sx].astype(np.int16)).mean())


def output_frame_count(
    keep_duration: bool,
    source_frames: int,
    source_fps: float,
    output_fps: float,
    total: float,
    target_step: float,
    loop: bool,
) -> int:
    if keep_duration:
        return max(2, int(round(source_frames / max(source_fps, 1e-8) * output_fps)))
    n_out = max(2, int(round(total / max(target_step, 1e-8))))
    if not loop:
        n_out += 1
    return n_out


def plan_indices(
    steps: np.ndarray,
    keep_duration: bool,
    source_frames: int,
    loop: bool,
    source_fps: float = 24.0,
    output_fps: float = 24.0,
    wrap_closed: bool = False,
) -> dict:
    if steps.size == 0:
        raise RuntimeError("No motion steps to equalize")
    cumulative = np.concatenate(([0.0], np.cumsum(steps)))
    total = float(cumulative[-1])
    if total <= 1e-8:
        raise RuntimeError("Clip has no measurable motion")
    healthy = steps[steps > np.percentile(steps, 20)]
    target_step = float(np.median(healthy)) if healthy.size else float(np.median(steps))
    # wrap_closed adds last->first as a virtual extra index after the last real frame.
    last_dense = int(steps.size)
    last_keep = last_dense - 1 if wrap_closed else last_dense
    n_out = output_frame_count(
        keep_duration, source_frames, source_fps, output_fps, total, target_step, loop
    )
    if loop:
        samples = np.linspace(0.0, total, n_out, endpoint=False)
    else:
        samples = np.linspace(0.0, total, n_out, endpoint=True)
    pos = np.interp(samples, cumulative, np.arange(len(cumulative), dtype=np.float64))
    raw = np.clip(np.rint(pos).astype(np.int64), 0, last_keep)
    selected: list[int] = []
    for index in raw.tolist():
        if not selected or selected[-1] != int(index):
            selected.append(int(index))
    if selected[0] != 0:
        selected.insert(0, 0)
    if not loop and selected[-1] != last_keep:
        selected.append(last_keep)
    covered = set(selected)
    skipped = [index for index in range(last_keep + 1) if index not in covered]
    return {
        "target_step": target_step,
        "total_motion": total,
        "requested_frames": n_out,
        "selected": selected,
        "skipped_dense_indexes": skipped,
        "wrap_motion": float(steps[-1]) if wrap_closed else (
            float(steps[-min(16, steps.size):].sum()) if loop else None
        ),
    }


def plan_loop_indices(
    linear_steps: np.ndarray,
    wrap_total: float,
    wrap_count: int,
    keep_duration: bool,
    source_frames: int,
    source_fps: float = 24.0,
    output_fps: float = 24.0,
) -> dict:
    """Budget output frames between the linear path and the wrap seam.

    wrap_total must be on the same scale as linear_steps (sum of micro-steps),
    not a single coarse last->first jump: a direct endpoint distance
    systematically underestimates curved wrap paths (triangle inequality) and
    starves the seam of frames.
    """
    if linear_steps.size == 0:
        raise RuntimeError("No linear motion steps")
    cumulative = np.concatenate(([0.0], np.cumsum(linear_steps)))
    linear_total = float(cumulative[-1])
    total = linear_total + max(float(wrap_total), 0.0)
    if total <= 1e-8:
        raise RuntimeError("Clip has no measurable motion")
    healthy = linear_steps[linear_steps > np.percentile(linear_steps, 20)]
    target_step = float(np.median(healthy)) if healthy.size else float(np.median(linear_steps))
    n_out = output_frame_count(
        keep_duration, source_frames, source_fps, output_fps, total, target_step, loop=True
    )
    # Proportional share: under --keep-duration n_out is fixed by duration, so an
    # absolute round(wrap_total / target_step) would oversample the seam (it assumes
    # n_out came from total_motion). Without --keep-duration both forms agree.
    n_wrap_out = 0
    if wrap_count > 0:
        n_wrap_out = min(
            wrap_count, max(1, int(round(n_out * wrap_total / max(total, 1e-8))))
        )
    n_linear_out = max(2, n_out - n_wrap_out)
    linear_last = int(linear_steps.size)
    selected: list[int] = []
    linear_samples = np.linspace(0.0, linear_total, n_linear_out, endpoint=True)
    for sample in linear_samples:
        pos = float(np.interp(sample, cumulative, np.arange(len(cumulative), dtype=np.float64)))
        index = int(np.clip(np.rint(pos), 0, linear_last))
        if not selected or selected[-1] != index:
            selected.append(index)
    wrap_used = 0
    if n_wrap_out > 0:
        wrap_picks = np.linspace(0, wrap_count - 1, n_wrap_out, endpoint=True)
        for pick in wrap_picks:
            index = linear_last + 1 + int(np.clip(np.rint(pick), 0, wrap_count - 1))
            if not selected or selected[-1] != index:
                selected.append(index)
                wrap_used += 1
    return {
        "target_step": target_step,
        "total_motion": total,
        "requested_frames": n_out,
        "selected": selected,
        "skipped_dense_indexes": [],
        "wrap_motion": wrap_total,
        "wrap_used": wrap_used,
    }


def encode_mapping(
    mapping: list[tuple[Path, int]],
    selected: list[int],
    output: Path,
    fps: float,
    crf: int,
) -> int:
    needed_local: dict[Path, set[int]] = {}
    for dense_index in selected:
        path, local = mapping[dense_index]
        needed_local.setdefault(path, set()).add(local)
    decoded = {}
    width = height = 0
    for path, indexes in needed_local.items():
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            width, height = stream.codec_context.width, stream.codec_context.height
            for local, frame in enumerate(container.decode(video=0)):
                if local in indexes:
                    decoded[(str(path), local)] = frame
    rate = Fraction(str(fps))
    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with av.open(str(output), "w", options={"movflags": "+faststart"}) as output_container:
        stream = output_container.add_stream("libx264", rate=rate)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": str(crf), "preset": "slow", "tune": "animation", "profile": "high"}
        for out_i, dense_index in enumerate(selected):
            path, local = mapping[dense_index]
            frame = decoded[(str(path), local)]
            converted = frame.reformat(width=stream.width, height=stream.height, format="yuv420p")
            converted.pts = out_i
            converted.time_base = Fraction(rate.denominator, rate.numerator)
            for packet in stream.encode(converted):
                output_container.mux(packet)
            written += 1
        for packet in stream.encode():
            output_container.mux(packet)
    return written


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if args.write_wrap_pair:
        info = write_wrap_pair(source, args.write_wrap_pair.resolve())
        print(json.dumps(info, indent=2))
        return 0
    if args.rife_video is None or args.output is None or args.report is None:
        raise ValueError("--rife-video, --output and --report are required unless --write-wrap-pair")

    rife_video = args.rife_video.resolve()
    output = args.output.resolve()
    report_path = args.report.resolve()
    wrap_video = args.wrap_rife_video.resolve() if args.wrap_rife_video else None
    if not rife_video.is_file():
        raise FileNotFoundError(rife_video)
    if wrap_video is not None and not wrap_video.is_file():
        raise FileNotFoundError(wrap_video)
    if wrap_video is not None and not args.loop:
        raise ValueError("--wrap-rife-video requires --loop")
    for path in (output, report_path):
        if path.exists():
            raise FileExistsError(f"Refusing to replace: {path}")

    with av.open(str(source)) as container:
        src_stream = container.streams.video[0]
        source_frames = int(src_stream.frames or sum(1 for _ in container.decode(video=0)))
        source_fps = float(src_stream.average_rate) if src_stream.average_rate is not None else args.fps

    mapping = collect_dense(rife_video, wrap_video, args.loop, source_frames)
    close_loop = bool(args.loop and wrap_video is None)
    wrap_micro_sum: float | None = None
    wrap_final_hop: float | None = None
    coarse_last_first: float | None = None
    steps = measure_mapping(
        mapping,
        parse_box(args.region),
        args.flow_width,
        close_loop=close_loop,
        metric=args.metric,
    )
    linear_len = sum(1 for path, _ in mapping if path == rife_video)
    wrap_count = len(mapping) - linear_len
    if args.loop and wrap_video is not None:
        if linear_len < 2:
            raise RuntimeError("Linear dense path is too short")
        linear_steps = steps[: linear_len - 1]
        box = parse_box(args.region)

        def rgb_at(dense_index: int) -> np.ndarray:
            path, local = mapping[dense_index]
            for index, rgb in enumerate(iter_rgb(path)):
                if index == local:
                    return rgb
            raise RuntimeError(f"Could not decode frame {local} of {path}")

        first_rgb = rgb_at(0)
        last_linear_rgb = rgb_at(linear_len - 1)

        def hop_motion(rgb_a: np.ndarray, rgb_b: np.ndarray) -> float:
            fy, fx = box_slice(box, rgb_a.shape[1], rgb_a.shape[0])
            appearance = appearance_step(rgb_a, rgb_b, fy, fx)
            flow_size = (
                args.flow_width,
                max(int(round(rgb_a.shape[0] * args.flow_width / rgb_a.shape[1])), 1),
            )
            small_a = shrink_gray(rgb_a, flow_size)
            small_b = shrink_gray(rgb_b, flow_size)
            scale = args.flow_width / float(rgb_a.shape[1])
            sy = slice(
                int(fy.start * scale), max(int(fy.stop * scale), int(fy.start * scale) + 1)
            )
            sx = slice(
                int(fx.start * scale), max(int(fx.stop * scale), int(fx.start * scale) + 1)
            )
            return step_value(flow_mag(small_a, small_b, sy, sx), appearance, args.metric)

        # Legacy reference: single coarse last-linear -> first jump.
        coarse_last_first = hop_motion(last_linear_rgb, first_rgb)
        if args.wrap_budget_mode == "coarse":
            wrap_total = coarse_last_first
            wrap_micro_sum = 0.0
            wrap_final_hop = coarse_last_first
        else:
            # Path scale: measured micro-steps along the wrap interpolants
            # (last_linear -> wrap interiors) plus the final hop into first.
            # Same units as linear_total, unlike the single coarse jump which
            # underestimates curved wrap paths (triangle inequality).
            wrap_micro = steps[linear_len - 1 :]
            wrap_micro_sum = float(wrap_micro.sum()) if wrap_micro.size else 0.0
            seam_start_rgb = rgb_at(len(mapping) - 1) if wrap_count > 0 else last_linear_rgb
            wrap_final_hop = hop_motion(seam_start_rgb, first_rgb)
            wrap_total = wrap_micro_sum + wrap_final_hop
        plan = plan_loop_indices(
            linear_steps,
            wrap_total,
            wrap_count,
            args.keep_duration,
            source_frames,
            source_fps=source_fps,
            output_fps=args.fps,
        )
    else:
        plan = plan_indices(
            steps,
            args.keep_duration,
            source_frames,
            loop=args.loop,
            source_fps=source_fps,
            output_fps=args.fps,
            wrap_closed=close_loop,
        )
    written = encode_mapping(mapping, plan["selected"], output, args.fps, args.crf)
    wrap_selected = sum(1 for index in plan["selected"] if mapping[index][0] != rife_video)
    report = {
        "schema_version": 1,
        "status": "success",
        "method": "equal_motion_arc_length_retime_with_wrap_interp",
        "source": str(source),
        "source_sha256": sha256(source),
        "rife_video": str(rife_video),
        "wrap_rife_video": None if wrap_video is None else str(wrap_video),
        "output": str(output),
        "output_sha256": sha256(output),
        "fps": args.fps,
        "loop": args.loop,
        "keep_duration": args.keep_duration,
        "region": args.region,
        "metric": args.metric,
        "source_frames": source_frames,
        "source_fps": source_fps,
        "dense_frames": len(mapping),
        "linear_dense_frames": linear_len,
        "wrap_dense_frames": len(mapping) - linear_len,
        "output_frames": written,
        "duration_seconds": written / args.fps,
        "target_step_flow": plan["target_step"],
        "total_motion": plan["total_motion"],
        "wrap_interval_flow": plan["wrap_motion"],
        "wrap_budget_mode": args.wrap_budget_mode if (args.loop and wrap_video is not None) else None,
        "wrap_micro_sum": wrap_micro_sum,
        "wrap_final_hop": wrap_final_hop,
        "wrap_coarse_last_to_first": coarse_last_first,
        "requested_frames": plan["requested_frames"],
        "wrap_frames_used": wrap_selected,
        "skipped_dense_count": len(plan["skipped_dense_indexes"]),
        "selected_dense_indexes": plan["selected"],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    printable = {key: value for key, value in report.items() if key != "selected_dense_indexes"}
    print(json.dumps(printable, indent=2))
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
