import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

def free_comfy_memory(api):
    try:
        req = urllib.request.Request(
            f"{api}/free",
            data=b'{"unload_models":true,"free_memory":true}',
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

def main():
    parser = argparse.ArgumentParser(description="Run MiniMax H3 Live2D profile generation")
    parser.add_argument("--profile", default="draft")
    parser.add_argument("--seed", type=int, default=2026083307)
    parser.add_argument("--lora-strength", type=float, default=0.5)
    parser.add_argument("--loop-lock", action="store_true")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--prompt-file", default=r".\prompts\MINIMAX_H3_LIVE2D_CRYSTAL_LOCK_LOOP_PROMPT_V7_BODY_ONLY.md")
    parser.add_argument("--input-image", default="keqing_gpt_reference_16x9.png")
    parser.add_argument("--report", default="")
    parser.add_argument("--api", default="http://127.0.0.1:8188")
    parser.add_argument("--abort-ram-gib", type=float, default=31.0)
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    workflow_path = os.path.join(project_root, "workflows", "minimax_h3_live2d_figurine_api.json")
    profiles_path = os.path.join(project_root, "presets", "minimax_h3_live2d_profiles.json")

    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = json.load(f)
    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)

    if args.profile not in profiles:
        raise ValueError(f"Profile {args.profile} not found in {profiles_path}")

    settings = profiles[args.profile]

    if args.prompt_file:
        prompt_full = os.path.abspath(os.path.join(project_root, args.prompt_file) if not os.path.isabs(args.prompt_file) else args.prompt_file)
        with open(prompt_full, "r", encoding="utf-8") as f:
            workflow["6"]["inputs"]["prompt"] = f.read()
        print(f"Loaded prompt from: {prompt_full}")

    if args.input_image:
        workflow["1"]["inputs"]["image"] = args.input_image
        print(f"Input image: {args.input_image}")

    if args.silent:
        workflow.pop("5", None)
        workflow.pop("13", None)
        if "14" in workflow and "inputs" in workflow["14"]:
            workflow["14"]["inputs"].pop("audio", None)
        audio_tag = "_silent"
    else:
        audio_tag = "_audio"

    workflow["17"]["inputs"]["width"] = settings["width"]
    workflow["17"]["inputs"]["height"] = settings["height"]
    workflow["17"]["inputs"]["crop"] = "disabled"

    workflow["6"]["inputs"]["width"] = settings["width"]
    workflow["6"]["inputs"]["height"] = settings["height"]
    workflow["6"]["inputs"]["length"] = settings["length"]

    workflow["8"]["inputs"]["steps"] = settings["steps"]
    workflow["8"]["inputs"]["scheduler"] = settings["scheduler"]
    workflow["9"]["inputs"]["sampler_name"] = settings["sampler"]
    workflow["10"]["inputs"]["noise_seed"] = args.seed
    workflow["14"]["inputs"]["fps"] = settings["fps"]
    workflow["16"]["inputs"]["strength_model"] = args.lora_strength

    output_width = settings.get("output_width", settings["width"])
    output_height = settings.get("output_height", settings["height"])

    if "output_width" in settings:
        workflow["19"] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["12", 0],
                "upscale_method": "lanczos",
                "width": output_width,
                "height": output_height,
                "crop": "disabled"
            }
        }
        workflow["14"]["inputs"]["images"] = ["19", 0]

    if args.loop_lock:
        workflow["6"]["inputs"]["last_frame"] = ["18", 0]
        mode = "fl2v_looplock"
    else:
        workflow["6"]["inputs"].pop("last_frame", None)
        mode = "i2v"

    strength_tag = f"{int(round(args.lora_strength * 100)):03d}"
    image_tag = "_keqing_gpt_reference_16x"
    workflow["15"]["inputs"]["filename_prefix"] = f"minimax_h3/live2d_{args.profile}_{mode}_{output_width}x{output_height}_{settings['length']}f_s{strength_tag}_seed{args.seed}{image_tag}{audio_tag}"

    payload = json.dumps({"prompt": workflow, "client_id": f"gemini-runner-{args.seed}"}).encode("utf-8")

    print(f"Submitting prompt to ComfyUI ({args.api}/prompt)...")
    sys.stdout.flush()

    req = urllib.request.Request(f"{args.api}/prompt", data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"Error submitting prompt: {e}")
        sys.exit(1)

    prompt_id = res_data.get("prompt_id")
    print(f"Prompt submitted successfully! prompt_id={prompt_id}")
    print(f"Profile={args.profile}, Seed={args.seed}, LoRA={args.lora_strength}, Mode={mode}")
    sys.stdout.flush()

    start_time = time.time()
    last_report = 0
    peak_vram = 0.0
    peak_ram = 0.0

    while True:
        try:
            with urllib.request.urlopen(f"{args.api}/system_stats", timeout=5) as resp:
                stats = json.loads(resp.read().decode("utf-8"))
                sys_stat = stats.get("system", {})
                ram = (sys_stat.get("ram_total", 0) - sys_stat.get("ram_free", 0)) / (1024**3)
                vram = 0.0
                devices = stats.get("devices", [])
                if devices:
                    vram = (devices[0].get("vram_total", 0) - devices[0].get("vram_free", 0)) / (1024**3)
                peak_ram = max(peak_ram, ram)
                peak_vram = max(peak_vram, vram)

                if ram >= args.abort_ram_gib:
                    print(f"WARNING: RAM usage {ram:.2f} GiB exceeded threshold {args.abort_ram_gib:.2f} GiB! Freeing memory and interrupting...")
                    free_comfy_memory(args.api)
                    urllib.request.urlopen(urllib.request.Request(f"{args.api}/interrupt", data=b"{}", headers={"Content-Type": "application/json"}))
                    sys.exit(2)
        except Exception:
            pass

        elapsed = time.time() - start_time
        if elapsed >= last_report:
            print(f"Progress: elapsed={elapsed:.1f}s | VRAM={peak_vram:.2f}GB | RAM={peak_ram:.2f}GB")
            sys.stdout.flush()
            last_report += 15

        # Check history
        try:
            with urllib.request.urlopen(f"{args.api}/history/{prompt_id}", timeout=5) as resp:
                hist_data = json.loads(resp.read().decode("utf-8"))
                if prompt_id in hist_data:
                    entry = hist_data[prompt_id]
                    status = entry.get("status", {})
                    outputs = entry.get("outputs", {}).get("15", {})
                    print(f"Finished: status={status.get('status_str')} in {elapsed:.1f}s")
                    print(f"Output files: {json.dumps(outputs, indent=2)}")
                    sys.stdout.flush()

                    if args.report:
                        rep_dir = os.path.dirname(os.path.abspath(args.report))
                        os.makedirs(rep_dir, exist_ok=True)
                        report_data = {
                            "schema_version": 1,
                            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time)),
                            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "status": status.get("status_str"),
                            "profile": args.profile,
                            "prompt_id": prompt_id,
                            "seed": args.seed,
                            "mode": mode,
                            "input_image": args.input_image,
                            "frames": settings["length"],
                            "fps": settings["fps"],
                            "output_width": output_width,
                            "output_height": output_height,
                            "elapsed_seconds": round(elapsed, 2),
                            "peak_vram_gib": round(peak_vram, 2),
                            "peak_ram_gib": round(peak_ram, 2),
                            "output": outputs,
                            "messages": status.get("messages", [])
                        }
                        with open(args.report, "w", encoding="utf-8") as rf:
                            json.dump(report_data, rf, indent=2)
                        print(f"Report written to: {args.report}")
                    
                    # Unload and free after successful completion
                    free_comfy_memory(args.api)
                    return
        except Exception:
            pass

        time.sleep(3)

if __name__ == "__main__":
    main()
