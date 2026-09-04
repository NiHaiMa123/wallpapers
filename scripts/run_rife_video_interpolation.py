#!/usr/bin/env python3
"""Run ComfyUI 0.34 native RIFE interpolation on a video from its input folder."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path


def request_json(url: str, *, data: dict | None = None, timeout: int = 30):
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
        return json.loads(payload.decode("utf-8")) if payload else {}


def used_gib(stats: dict, *, vram: bool) -> float:
    if vram:
        device = stats["devices"][0]
        return (device["vram_total"] - device["vram_free"]) / 2**30
    system = stats["system"]
    return (system["ram_total"] - system["ram_free"]) / 2**30


def release(api: str) -> tuple[float | None, float | None]:
    try:
        request_json(f"{api}/free", data={"unload_models": True, "free_memory": True})
        time.sleep(3)
        stats = request_json(f"{api}/system_stats")
        return used_gib(stats, vram=False), used_gib(stats, vram=True)
    except Exception:
        return None, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-name", required=True, help="Video name relative to the ComfyUI input folder")
    parser.add_argument("--output-prefix", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--model", default="rife_v4.26.safetensors")
    parser.add_argument("--multiplier", type=int, choices=range(2, 17), default=4)
    parser.add_argument("--output-fps", type=float, default=96.0)
    parser.add_argument("--max-input-frames", type=int, default=0)
    parser.add_argument("--cyclic", action="store_true")
    parser.add_argument(
        "--wrap-ends",
        action="store_true",
        help="Interpolate the last frame then the first frame of the loaded video",
    )
    parser.add_argument("--expected-input-frames", type=int, default=0)
    parser.add_argument("--abort-ram-gib", type=float, default=31.0)
    parser.add_argument("--api", default="http://127.0.0.1:8188")
    args = parser.parse_args()

    report_path = Path(args.report).resolve()
    if report_path.exists():
        raise FileExistsError(f"Refusing to replace run report: {report_path}")

    object_info = request_json(f"{args.api}/object_info")
    system_stats = request_json(f"{args.api}/system_stats")
    required = {
        "LoadVideo",
        "GetVideoComponents",
        "FrameInterpolationModelLoader",
        "FrameInterpolate",
        "CreateVideo",
        "SaveVideo",
    }
    if args.max_input_frames:
        required.add("ImageFromBatch")
    if args.cyclic:
        required.update({"ImageBatch", "ImageFromBatch"})
        if args.expected_input_frames <= 0 and args.max_input_frames <= 0:
            raise ValueError("--cyclic requires --expected-input-frames or --max-input-frames")
    if args.wrap_ends:
        required.update({"ImageBatch", "ImageFromBatch"})
        if args.expected_input_frames <= 0 and args.max_input_frames <= 0:
            raise ValueError("--wrap-ends requires --expected-input-frames or --max-input-frames")
        if args.cyclic:
            raise ValueError("--wrap-ends cannot be combined with --cyclic")
    missing = sorted(required.difference(object_info))
    if missing:
        raise RuntimeError(f"Missing ComfyUI nodes: {missing}")

    workflow: dict[str, dict] = {
        "1": {
            "class_type": "FrameInterpolationModelLoader",
            "inputs": {"model_name": args.model},
        },
        "2": {"class_type": "LoadVideo", "inputs": {"file": args.input_name}},
        "3": {"class_type": "GetVideoComponents", "inputs": {"video": ["2", 0]}},
        "4": {
            "class_type": "FrameInterpolate",
            "inputs": {
                "interp_model": ["1", 0],
                "images": ["3", 0],
                "multiplier": args.multiplier,
            },
        },
        "5": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["4", 0], "fps": args.output_fps, "bit_depth": 8},
        },
        "6": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["5", 0],
                "filename_prefix": args.output_prefix,
                "format": "mp4",
                "codec": "auto",
            },
        },
    }
    if args.max_input_frames:
        workflow["7"] = {
            "class_type": "ImageFromBatch",
            "inputs": {
                "image": ["3", 0],
                "batch_index": 0,
                "length": args.max_input_frames,
            },
        }
        workflow["4"]["inputs"]["images"] = ["7", 0]
    source_images = workflow["4"]["inputs"]["images"]
    if args.cyclic:
        input_frames = args.max_input_frames or args.expected_input_frames
        workflow["8"] = {
            "class_type": "ImageFromBatch",
            "inputs": {"image": source_images, "batch_index": 0, "length": 1},
        }
        workflow["9"] = {
            "class_type": "ImageBatch",
            "inputs": {"image1": source_images, "image2": ["8", 0]},
        }
        workflow["4"]["inputs"]["images"] = ["9", 0]
        workflow["10"] = {
            "class_type": "ImageFromBatch",
            "inputs": {
                "image": ["4", 0],
                "batch_index": 0,
                "length": input_frames * args.multiplier,
            },
        }
        workflow["5"]["inputs"]["images"] = ["10", 0]
    if args.wrap_ends:
        input_frames = args.max_input_frames or args.expected_input_frames
        workflow["11"] = {
            "class_type": "ImageFromBatch",
            "inputs": {
                "image": source_images,
                "batch_index": input_frames - 1,
                "length": 1,
            },
        }
        workflow["12"] = {
            "class_type": "ImageFromBatch",
            "inputs": {"image": source_images, "batch_index": 0, "length": 1},
        }
        workflow["13"] = {
            "class_type": "ImageBatch",
            "inputs": {"image1": ["11", 0], "image2": ["12", 0]},
        }
        workflow["4"]["inputs"]["images"] = ["13", 0]

    client_id = f"codex-rife-{uuid.uuid4()}"
    submitted = request_json(
        f"{args.api}/prompt", data={"prompt": workflow, "client_id": client_id}
    )
    if submitted.get("node_errors"):
        raise RuntimeError(json.dumps(submitted["node_errors"], ensure_ascii=False, indent=2))
    prompt_id = submitted["prompt_id"]
    print(f"Submitted prompt: {prompt_id}", flush=True)

    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    peak_ram = 0.0
    peak_vram = 0.0
    next_report = 0.0
    status = "unknown"
    output = None
    messages = []
    exit_code = 0
    try:
        while True:
            stats = request_json(f"{args.api}/system_stats")
            ram = used_gib(stats, vram=False)
            vram = used_gib(stats, vram=True)
            peak_ram = max(peak_ram, ram)
            peak_vram = max(peak_vram, vram)
            elapsed = time.monotonic() - started
            if elapsed >= next_report:
                print(
                    f"Progress: {elapsed:.0f}s RAM {ram:.2f}GiB VRAM {vram:.2f}GiB "
                    f"peaks {peak_ram:.2f}/{peak_vram:.2f}GiB",
                    flush=True,
                )
                next_report += 15
            if ram >= args.abort_ram_gib:
                request_json(f"{args.api}/interrupt", data={})
                status = "interrupted_ram_threshold"
                messages = [f"RAM usage reached {ram}GiB"]
                exit_code = 2
                break
            history = request_json(f"{args.api}/history/{prompt_id}")
            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {}).get("status_str", "unknown")
                messages = entry.get("status", {}).get("messages", [])
                output = entry.get("outputs", {}).get("6")
                if status != "success":
                    exit_code = 3
                break
            time.sleep(2)
    finally:
        released_ram, released_vram = release(args.api)
        report = {
            "schema_version": 1,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "api": args.api,
            "comfyui_version": system_stats.get("system", {}).get("comfyui_version", "unknown"),
            "prompt_id": prompt_id,
            "input_name": args.input_name,
            "model": args.model,
            "multiplier": args.multiplier,
            "output_fps": args.output_fps,
            "max_input_frames": args.max_input_frames,
            "cyclic": args.cyclic,
            "wrap_ends": args.wrap_ends,
            "expected_input_frames": args.expected_input_frames,
            "abort_ram_gib": args.abort_ram_gib,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "peak_ram_gib": round(peak_ram, 3),
            "peak_vram_gib": round(peak_vram, 3),
            "released_ram_gib": None if released_ram is None else round(released_ram, 3),
            "released_vram_gib": None if released_vram is None else round(released_vram, 3),
            "output": output,
            "messages": messages,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Run report: {report_path}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
