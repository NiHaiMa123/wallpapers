"""Run a two-window MiniMax H3 continuation probe through the local ComfyUI API.

The probe intentionally keeps each generation at 22 frames.  Window 2 receives
the final five frames of window 1 through MiniMaxH3AddGuide, then only its new
17 frames are appended.  This validates the minimum H3-native sliding-window
scheme without committing to the full loop workflow.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import time
import urllib.error
import urllib.request

import av
import numpy as np
from PIL import Image, ImageDraw


# This file lives in scripts/experimental/, so the repo root is two levels up
# from __file__ (experimental -> scripts -> repo root).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMFY_OUTPUT = Path(r"D:\Comfy-Desktop\ComfyUI-Shared\output")
WINDOW_LENGTH = 22
CONTEXT_LENGTH = 5
WIDTH = 1024
HEIGHT = 576
FPS = 24

FIRST_PROMPT = """hmmotion. One continuous locked-off 16:9 shot of the exact same clearly adult anime game character from the first frame. Preserve the exact face, violet-red eyes, hairstyle, costume, sword, anatomy, pose, framing, background, lighting, and materials. Use only coherent low-amplitude living-character motion: subtle breathing, minute coordinated head and shoulder settling, gentle hair-tip and cloth follow-through, and restrained purple electrical arcs attached to the blade. Keep the camera and background fixed. Keep all petals already present in the image spatially fixed and do not create new particles.

Perform only the closing half of one natural quick blink near the end of this short clip. Both eyelids should begin open, close together smoothly, and reach a clean just-closed state at the final frame. Do not reopen before the clip ends. No large pose change, no camera movement, no identity drift, no face warping, no extra limbs, no detached lightning, no full-screen flash, no morphing, no text, no watermark."""

SECOND_PROMPT = """hmmotion. Continue forward in time from the supplied five-frame motion clip of the exact same clearly adult anime game character. Preserve the exact identity, face, violet-red eyes, hairstyle, costume, sword, anatomy, pose, framing, background, lighting, materials, and the incoming motion direction. The supplied clip ends at the just-closed phase of one blink. Reopen both eyes naturally within the next few frames, then keep both eyes open for the rest of the clip. Do not perform a second blink. Continue subtle breathing, minute coordinated head and shoulder settling, gentle hair-tip and cloth follow-through, and restrained purple electrical arcs attached to the blade. Keep all existing petals spatially fixed and create no new particles.

Static camera. No abrupt pose change, no motion reset, no camera movement, no identity drift, no face warping, no crossed eyes, no extra limbs, no detached lightning, no full-screen flash, no morphing, no text, no watermark."""


def api_json(base: str, method: str, endpoint: str, body: dict | None = None, timeout: float = 15.0):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        base.rstrip("/") + endpoint,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8")) if payload else {}


def free_comfy(base: str) -> None:
    api_json(base, "POST", "/free", {"unload_models": True, "free_memory": True})
    time.sleep(2.0)


def system_usage(base: str) -> tuple[float, float, str]:
    stats = api_json(base, "GET", "/system_stats")
    ram = (stats["system"]["ram_total"] - stats["system"]["ram_free"]) / 2**30
    device = stats["devices"][0]
    vram = (device["vram_total"] - device["vram_free"]) / 2**30
    return ram, vram, str(stats["system"]["comfyui_version"])


def base_workflow(prompt: str, seed: int, prefix: str, first_frame: list) -> dict:
    return {
        "2": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors", "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "6": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {
            "clip": ["3", 0], "vae": ["4", 0], "prompt": prompt,
            "width": WIDTH, "height": HEIGHT, "length": WINDOW_LENGTH, "first_frame": first_frame}},
        "7": {"class_type": "BasicGuider", "inputs": {"model": ["16", 0], "conditioning": ["6", 0]}},
        "8": {"class_type": "BasicScheduler", "inputs": {
            "model": ["16", 0], "scheduler": "simple", "steps": 20, "denoise": 1.0}},
        "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "10": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "11": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["10", 0], "guider": ["7", 0], "sampler": ["9", 0],
            "sigmas": ["8", 0], "latent_image": ["6", 1]}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["4", 0]}},
        "16": {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["2", 0], "lora_name": "HMNSFW-AIO-V2.5.safetensors", "strength_model": 0.5}},
        "20": {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": prefix}},
    }


def first_workflow(seed: int, prefix: str, input_image: str) -> dict:
    workflow = base_workflow(FIRST_PROMPT, seed, prefix, ["18", 0])
    workflow.update({
        "1": {"class_type": "LoadImage", "inputs": {"image": input_image}},
        "17": {"class_type": "ImageScale", "inputs": {
            "image": ["1", 0], "upscale_method": "lanczos", "width": WIDTH,
            "height": HEIGHT, "crop": "disabled"}},
        "18": {"class_type": "ImageSharpen", "inputs": {
            "image": ["17", 0], "sharpen_radius": 1, "sigma": 0.7, "alpha": 0.15}},
    })
    return workflow


def second_workflow(seed: int, prefix: str, context_paths: list[str]) -> dict:
    workflow = base_workflow(SECOND_PROMPT, seed, prefix, ["30", 0])
    for offset, path in enumerate(context_paths):
        workflow[str(30 + offset)] = {"class_type": "LoadImage", "inputs": {"image": path}}
    workflow.update({
        "40": {"class_type": "ImageBatch", "inputs": {"image1": ["30", 0], "image2": ["31", 0]}},
        "41": {"class_type": "ImageBatch", "inputs": {"image1": ["40", 0], "image2": ["32", 0]}},
        "42": {"class_type": "ImageBatch", "inputs": {"image1": ["41", 0], "image2": ["33", 0]}},
        "43": {"class_type": "ImageBatch", "inputs": {"image1": ["42", 0], "image2": ["34", 0]}},
        "44": {"class_type": "MiniMaxH3AddGuide", "inputs": {
            "positive": ["6", 0], "latent": ["6", 1], "vae": ["4", 0],
            "image": ["43", 0], "frame_idx": 0}},
    })
    workflow["7"]["inputs"]["conditioning"] = ["44", 0]
    return workflow


def wait_prompt(base: str, prompt_id: str, abort_ram_gib: float) -> dict:
    started = time.monotonic()
    peak_ram = peak_vram = 0.0
    last_notice = -1
    while True:
        ram, vram, _ = system_usage(base)
        peak_ram, peak_vram = max(peak_ram, ram), max(peak_vram, vram)
        elapsed = time.monotonic() - started
        notice = int(elapsed // 30)
        if notice != last_notice:
            print(f"progress prompt={prompt_id[:8]} elapsed={elapsed:.0f}s RAM={ram:.2f}/{peak_ram:.2f}GiB VRAM={vram:.2f}/{peak_vram:.2f}GiB", flush=True)
            last_notice = notice
        if ram >= abort_ram_gib:
            api_json(base, "POST", "/interrupt", {})
            raise RuntimeError(f"RAM fuse triggered at {ram:.3f} GiB")
        history = api_json(base, "GET", f"/history/{prompt_id}")
        item = history.get(prompt_id)
        if item:
            status = item.get("status", {})
            if status.get("completed"):
                if status.get("status_str") != "success":
                    raise RuntimeError(f"ComfyUI prompt failed: {json.dumps(status, ensure_ascii=False)}")
                return {
                    "elapsed_seconds": round(elapsed, 3),
                    "peak_ram_gib": round(peak_ram, 3),
                    "peak_vram_gib": round(peak_vram, 3),
                    "history": item,
                }
        time.sleep(2.0)


def submit(base: str, workflow: dict, client_id: str, abort_ram_gib: float) -> dict:
    response = api_json(base, "POST", "/prompt", {"prompt": workflow, "client_id": client_id}, timeout=30.0)
    if response.get("node_errors"):
        raise RuntimeError(f"Prompt validation failed: {json.dumps(response['node_errors'], ensure_ascii=False)}")
    prompt_id = response["prompt_id"]
    result = wait_prompt(base, prompt_id, abort_ram_gib)
    result["prompt_id"] = prompt_id
    return result


def wait_for_frames(directory: Path, count: int) -> list[Path]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        frames = sorted(directory.glob("frame_*.png"))
        if len(frames) == count:
            return frames
        time.sleep(0.5)
    raise RuntimeError(f"Expected {count} frames in {directory}, found {len(list(directory.glob('frame_*.png')))}")


def read_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def mad(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean())


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.square(a.astype(np.float32) - b.astype(np.float32)).mean())
    return math.inf if mse == 0 else 20.0 * math.log10(255.0 / math.sqrt(mse))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encode_video(frames: list[np.ndarray], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("libx264", rate=Fraction(FPS, 1), options={"crf": "18", "preset": "slow", "tune": "animation"})
        stream.width = WIDTH
        stream.height = HEIGHT
        stream.pix_fmt = "yuv420p"
        for array in frames:
            for packet in stream.encode(av.VideoFrame.from_ndarray(array, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def contact_sheet(frames: list[np.ndarray], path: Path) -> None:
    indexes = sorted(set([0, 5, 10, 15, 17, 18, 19, 20, 21, 22, 23, 24, 25, 30, 34, 38]))
    thumb_w, thumb_h = 320, 180
    canvas = Image.new("RGB", (thumb_w * 4, (thumb_h + 24) * 4), "black")
    draw = ImageDraw.Draw(canvas)
    for slot, index in enumerate(indexes):
        image = Image.fromarray(frames[index]).resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        x = slot % 4 * thumb_w
        y = slot // 4 * (thumb_h + 24)
        canvas.paste(image, (x, y))
        draw.text((x + 6, y + thumb_h + 3), f"assembled frame {index + 1}", fill="white")
    canvas.save(path, quality=92)


def analyze(first_paths: list[Path], second_paths: list[Path], artifact_dir: Path) -> dict:
    first = [read_rgb(path) for path in first_paths]
    second = [read_rgb(path) for path in second_paths]
    overlap = []
    for i in range(CONTEXT_LENGTH):
        overlap.append({
            "context_index": i,
            "window1_frame_index": WINDOW_LENGTH - CONTEXT_LENGTH + i,
            "window2_frame_index": i,
            "mad": round(mad(first[-CONTEXT_LENGTH + i], second[i]), 6),
            "psnr_db": round(psnr(first[-CONTEXT_LENGTH + i], second[i]), 6),
        })
    assembled = first + second[CONTEXT_LENGTH:]
    adjacent = [mad(assembled[i], assembled[i + 1]) for i in range(len(assembled) - 1)]
    seam_index = WINDOW_LENGTH - 1
    seam_mad = adjacent[seam_index]
    p95 = float(np.percentile(adjacent, 95))
    median = float(np.median(adjacent))
    internal_next = mad(second[CONTEXT_LENGTH - 1], second[CONTEXT_LENGTH])
    video_path = artifact_dir / "window_probe_39f.mp4"
    sheet_path = artifact_dir / "window_probe_contact_sheet.jpg"
    encode_video(assembled, video_path)
    contact_sheet(assembled, sheet_path)
    return {
        "assembled_frames": len(assembled),
        "duration_seconds": len(assembled) / FPS,
        "overlap_fidelity": overlap,
        "overlap_mean_mad": round(float(np.mean([row["mad"] for row in overlap])), 6),
        "overlap_mean_psnr_db": round(float(np.mean([row["psnr_db"] for row in overlap])), 6),
        "stitch": {
            "assembled_pair": [WINDOW_LENGTH - 1, WINDOW_LENGTH],
            "mad": round(seam_mad, 6),
            "window2_internal_context_to_new_mad": round(internal_next, 6),
            "internal_adjacent_mad_median": round(median, 6),
            "internal_adjacent_mad_p95": round(p95, 6),
            "spike_ratio_vs_p95": round(seam_mad / p95, 6) if p95 else None,
        },
        "video": str(video_path),
        "video_sha256": sha256(video_path),
        "contact_sheet": str(sheet_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8188")
    parser.add_argument("--input-image", default="keqing_gpt_reference_16x9.png")
    parser.add_argument("--seed-first", type=int, default=2026083101)
    parser.add_argument("--seed-second", type=int, default=2026083102)
    parser.add_argument("--abort-ram-gib", type=float, default=31.0)
    args = parser.parse_args()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-window5"
    artifact_dir = PROJECT_ROOT / "artifacts" / "loop_vfi_probe" / run_id
    artifact_dir.mkdir(parents=True, exist_ok=False)
    output_root_rel = Path("minimax_h3_window_probe") / run_id
    output_root = COMFY_OUTPUT / output_root_rel
    first_dir = output_root / "window_1"
    second_dir = output_root / "window_2"

    ram, vram, version = system_usage(args.api)
    if not version.startswith("0.34"):
        raise RuntimeError(f"Expected ComfyUI 0.34, got {version}")
    print(f"run_id={run_id} ComfyUI={version} baseline_RAM={ram:.2f}GiB baseline_VRAM={vram:.2f}GiB", flush=True)

    first_prefix = (output_root_rel / "window_1" / "frame").as_posix()
    first = first_workflow(args.seed_first, first_prefix, args.input_image)
    (artifact_dir / "window_1_workflow.json").write_text(json.dumps(first, indent=2, ensure_ascii=False), encoding="utf-8")
    free_comfy(args.api)
    print("submitting window 1", flush=True)
    first_run = submit(args.api, first, f"codex-h3-window-probe-{run_id}-1", args.abort_ram_gib)
    first_paths = wait_for_frames(first_dir, WINDOW_LENGTH)

    context_paths = []
    for path in first_paths[-CONTEXT_LENGTH:]:
        rel = path.relative_to(COMFY_OUTPUT).as_posix()
        context_paths.append(f"{rel} [output]")
    second_prefix = (output_root_rel / "window_2" / "frame").as_posix()
    second = second_workflow(args.seed_second, second_prefix, context_paths)
    (artifact_dir / "window_2_workflow.json").write_text(json.dumps(second, indent=2, ensure_ascii=False), encoding="utf-8")
    free_comfy(args.api)
    print("submitting window 2 with five-frame guide", flush=True)
    second_run = submit(args.api, second, f"codex-h3-window-probe-{run_id}-2", args.abort_ram_gib)
    second_paths = wait_for_frames(second_dir, WINDOW_LENGTH)

    analysis = analyze(first_paths, second_paths, artifact_dir)
    report = {
        "run_id": run_id,
        "result": "MECHANICAL_PASS",
        "scope": "Two 22-frame 1024x576 H3 windows with a five-frame AddGuide overlap",
        "api": args.api,
        "comfyui_version": version,
        "input_image": args.input_image,
        "window_length": WINDOW_LENGTH,
        "context_length": CONTEXT_LENGTH,
        "new_frames_per_continuation": WINDOW_LENGTH - CONTEXT_LENGTH,
        "seeds": {"window_1": args.seed_first, "window_2": args.seed_second},
        "generation": {"window_1": {k: v for k, v in first_run.items() if k != "history"},
                       "window_2": {k: v for k, v in second_run.items() if k != "history"}},
        "output_frame_directories": {"window_1": str(first_dir), "window_2": str(second_dir)},
        "analysis": analysis,
    }
    report_path = artifact_dir / "window_probe_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md = f"""# H3 five-frame sliding-window probe\n\n- Result: `{report['result']}`\n- Run: `{run_id}`\n- Windows: `22F + (22F - 5F) = {analysis['assembled_frames']}F` at {WIDTH}x{HEIGHT}\n- Window 1 peak RAM/VRAM: {first_run['peak_ram_gib']}/{first_run['peak_vram_gib']} GiB\n- Window 2 peak RAM/VRAM: {second_run['peak_ram_gib']}/{second_run['peak_vram_gib']} GiB\n- Overlap mean MAD/PSNR: {analysis['overlap_mean_mad']} / {analysis['overlap_mean_psnr_db']} dB\n- Stitch MAD: {analysis['stitch']['mad']}\n- Internal P95 adjacent MAD: {analysis['stitch']['internal_adjacent_mad_p95']}\n- Stitch spike ratio: {analysis['stitch']['spike_ratio_vs_p95']}\n- Video: `{analysis['video']}`\n- Contact sheet: `{analysis['contact_sheet']}`\n\n`MECHANICAL_PASS` means both jobs completed, the five-frame guide was accepted, 39 frames were assembled without duplicate overlap, and metrics were produced. Visual blink/motion continuity still requires review.\n"""
    (artifact_dir / "window_probe_report.md").write_text(md, encoding="utf-8")
    print(json.dumps({"report": str(report_path), "analysis": analysis}, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
