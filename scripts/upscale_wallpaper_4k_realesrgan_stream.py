#!/usr/bin/env python3
"""Stream RealESRGAN frames through tiled GPU inference into a 4K H.264 file."""

from __future__ import annotations

import argparse
import json
import sys
import time
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import psutil
import torch
from PIL import Image
from spandrel import ModelLoader

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
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--width", type=int, default=3840)
    parser.add_argument("--height", type=int, default=2160)
    parser.add_argument("--expected-fps", type=float, default=24.0)
    parser.add_argument("--tile", type=int, default=384)
    parser.add_argument("--overlap", type=int, default=32)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--preset", default="medium")
    parser.add_argument("--tune", default="animation")
    parser.add_argument("--h264-profile", default="high")
    parser.add_argument("--h264-level", default="5.1")
    parser.add_argument("--abort-ram-gib", type=float, default=31.0)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--scope", choices=("full", "smoke"), default="full")
    return parser.parse_args()


def load_model(path: Path, device: torch.device):
    state = torch.load(path, map_location="cpu", weights_only=True)
    if isinstance(state, dict):
        if "params_ema" in state:
            state = state["params_ema"]
        elif "params" in state:
            state = state["params"]
    model = ModelLoader().load_from_state_dict(state).eval()
    model.to(device=device, dtype=torch.float16)
    return model


def positions(size: int, tile: int, overlap: int) -> list[int]:
    if size <= tile:
        return [0]
    stride = tile - overlap
    result = list(range(0, size - tile + 1, stride))
    final = size - tile
    if result[-1] != final:
        result.append(final)
    return result


def feather(height: int, width: int, overlap: int, top: bool, bottom: bool, left: bool, right: bool) -> torch.Tensor:
    weight_y = torch.ones(height, dtype=torch.float32)
    weight_x = torch.ones(width, dtype=torch.float32)
    if overlap > 0:
        if overlap > height or overlap > width:
            raise ValueError("Scaled overlap exceeds restored tile dimensions")
        ramp = torch.linspace(1.0 / (overlap + 1), 1.0, overlap, dtype=torch.float32)
        if top:
            weight_y[:overlap] = ramp
        if bottom:
            weight_y[-overlap:] = torch.flip(ramp, dims=[0])
        if left:
            weight_x[:overlap] = ramp
        if right:
            weight_x[-overlap:] = torch.flip(ramp, dims=[0])
    return weight_y[:, None] * weight_x[None, :]


@torch.inference_mode()
def upscale_frame(model, rgb: np.ndarray, device: torch.device, tile: int, overlap: int) -> tuple[Image.Image, int]:
    source = torch.from_numpy(rgb.copy()).permute(2, 0, 1).unsqueeze(0).to(device=device, dtype=torch.float16) / 255.0
    _, _, height, width = source.shape
    scale = int(round(float(model.scale)))
    if scale <= 0:
        raise RuntimeError(f"Invalid model scale: {model.scale!r}")
    output = torch.zeros((3, height * scale, width * scale), dtype=torch.float32)
    weights = torch.zeros((height * scale, width * scale), dtype=torch.float32)
    ys = positions(height, tile, overlap)
    xs = positions(width, tile, overlap)
    feather_size = overlap * scale

    for y in ys:
        for x in xs:
            patch = source[:, :, y : min(y + tile, height), x : min(x + tile, width)]
            restored = model(patch).clamp_(0, 1).squeeze(0).float().cpu()
            out_h, out_w = restored.shape[-2:]
            y0, x0 = y * scale, x * scale
            weight = feather(
                out_h,
                out_w,
                feather_size,
                top=y > 0,
                bottom=y + patch.shape[-2] < height,
                left=x > 0,
                right=x + patch.shape[-1] < width,
            )
            output[:, y0 : y0 + out_h, x0 : x0 + out_w] += restored * weight
            weights[y0 : y0 + out_h, x0 : x0 + out_w] += weight
            del patch, restored, weight

    output /= weights.clamp_min_(1e-6).unsqueeze(0)
    array = (output.permute(1, 2, 0).clamp_(0, 1).numpy() * 255.0 + 0.5).astype(np.uint8)
    del source, output, weights
    return Image.fromarray(array), scale


def main() -> int:
    args = parse_args()
    if args.run_report is None:
        args.run_report = args.output.with_name(f"{args.output.stem}_RUN.json")
    validate_dimensions(args.width, args.height)
    if not args.model.is_file():
        raise FileNotFoundError(args.model)
    if args.overlap < 0 or args.tile <= args.overlap:
        raise ValueError("tile must be larger than overlap")
    if args.max_frames < 0:
        raise ValueError("--max-frames cannot be negative")
    if args.abort_ram_gib <= 0:
        raise ValueError("--abort-ram-gib must be positive")
    validate_source_and_targets(args.input, args.output, args.run_report)
    profile = load_profile(args.profile_file, args.profile_name)
    if profile is not None and profile.get("method") != "realesrgan_stream":
        raise ValueError(f"Profile {args.profile_name!r} is not a RealESRGAN profile")

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

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for RealESRGAN streaming upscale")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.run_report.parent.mkdir(parents=True, exist_ok=True)
    partial_video = make_partial_path(args.output)
    tracker = ResourceTracker()
    process = psutil.Process()
    cpu_before = process.cpu_times()
    started_at = utc_now()
    started = time.perf_counter()
    input_frames = 0
    resized_frames = 0
    model_scale: int | None = None
    peak_total_gpu_used_gib = 0.0
    device = torch.device("cuda")

    def sample_gpu() -> None:
        nonlocal peak_total_gpu_used_gib
        free_bytes, total_bytes = torch.cuda.mem_get_info(device)
        peak_total_gpu_used_gib = max(peak_total_gpu_used_gib, (total_bytes - free_bytes) / 2**30)

    try:
        torch.cuda.reset_peak_memory_stats(device)
        if psutil.virtual_memory().used / 2**30 >= args.abort_ram_gib:
            raise MemoryError("System RAM safety threshold was already reached before model loading")
        model = load_model(args.model, device)
        model_scale = int(round(float(model.scale)))
        tracker.sample()
        sample_gpu()
        if psutil.virtual_memory().used / 2**30 >= args.abort_ram_gib:
            raise MemoryError("System RAM safety threshold reached after model loading")

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
                    system_ram = psutil.virtual_memory().used / 2**30
                    if system_ram >= args.abort_ram_gib:
                        raise MemoryError(f"System RAM safety threshold reached: {system_ram:.2f} GiB")
                    restored, frame_scale = upscale_frame(
                        model,
                        frame.to_ndarray(format="rgb24"),
                        device,
                        args.tile,
                        args.overlap,
                    )
                    if model_scale is None:
                        model_scale = frame_scale
                    elif model_scale != frame_scale:
                        raise RuntimeError("Model scale changed between frames")
                    if restored.size != (args.width, args.height):
                        restored = restored.resize((args.width, args.height), Image.Resampling.LANCZOS)
                        resized_frames += 1
                    video_frame = av.VideoFrame.from_image(restored)
                    video_frame.pts = index
                    video_frame.time_base = Fraction(rate.denominator, rate.numerator)
                    for packet in output.encode(video_frame):
                        target.mux(packet)
                    input_frames += 1
                    tracker.sample()
                    sample_gpu()
                    print(f"frame={input_frames} elapsed={time.perf_counter() - started:.1f}s", flush=True)
                    del restored, video_frame
                for packet in output.encode():
                    target.mux(packet)

        torch.cuda.synchronize(device)
        validation = validate_video(
            partial_video,
            width=args.width,
            height=args.height,
            fps=args.expected_fps,
            expected_frames=expected_frames,
        )
        if not validation["passed"]:
            raise RuntimeError(f"RealESRGAN output validation failed: {validation['validation_errors']}")

        elapsed = time.perf_counter() - started
        cpu_after = process.cpu_times()
        tracker.sample()
        sample_gpu()
        output_sha256 = sha256_file(partial_video)
        validation["path"] = str(args.output.resolve())
        validation["sha256"] = output_sha256
        environment = environment_info()
        environment.update(
            {
                "torch": torch.__version__,
                "cuda_runtime": torch.version.cuda,
                "gpu_name": torch.cuda.get_device_name(device),
            }
        )
        report = {
            "schema_version": 1,
            "status": "success",
            "method": "realesrgan_stream",
            "scope": args.scope,
            "complete_video": expected_frames == int(source_info["decoded_frames"]),
            "started_at_utc": started_at,
            "finished_at_utc": utc_now(),
            "command": [sys.executable, *sys.argv],
            "profile": profile,
            "source": source_info,
            "model": {
                "path": str(args.model.resolve()),
                "sha256": sha256_file(args.model),
                "scale": model_scale,
            },
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
                "tile": args.tile,
                "overlap": args.overlap,
                "abort_ram_gib": args.abort_ram_gib,
                "frames_resized_after_model": resized_frames,
                "model_native_output_for_1024x576": [1024 * int(model_scale or 0), 576 * int(model_scale or 0)],
            },
            "performance": {
                "elapsed_seconds": elapsed,
                "seconds_per_frame": elapsed / max(input_frames, 1),
                "cpu_user_seconds": cpu_after.user - cpu_before.user,
                "cpu_system_seconds": cpu_after.system - cpu_before.system,
                **tracker.result(),
                "peak_gpu_allocated_gib": torch.cuda.max_memory_allocated(device) / 2**30,
                "peak_gpu_reserved_gib": torch.cuda.max_memory_reserved(device) / 2**30,
                "peak_total_gpu_used_gib_sampled": peak_total_gpu_used_gib,
            },
            "environment": environment,
        }
        partial_report = write_json_partial(args.run_report, report)
        publish_partial(partial_video, args.output)
        publish_partial(partial_report, args.run_report)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        print(f"output={args.output.resolve()}", flush=True)
        print(f"run_report={args.run_report.resolve()}", flush=True)
        return 0
    except Exception as exc:
        tracker.sample()
        if torch.cuda.is_available():
            try:
                sample_gpu()
            except Exception:
                pass
        failure = {
            "schema_version": 1,
            "status": "failed",
            "method": "realesrgan_stream",
            "scope": args.scope,
            "started_at_utc": started_at,
            "failed_at_utc": utc_now(),
            "command": [sys.executable, *sys.argv],
            "error_type": type(exc).__name__,
            "error": str(exc),
            "partial_video": str(partial_video.resolve()) if partial_video.exists() else None,
            "processed_frames": input_frames,
            "model_scale": model_scale,
            "performance": {
                **tracker.result(),
                "peak_total_gpu_used_gib_sampled": peak_total_gpu_used_gib,
            },
        }
        write_failure_report(args.run_report, failure)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
