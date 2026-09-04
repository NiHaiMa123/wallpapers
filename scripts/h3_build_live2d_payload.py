#!/usr/bin/env python3
"""Build a ComfyUI /prompt payload for the Live2D H3 runner.

PowerShell ConvertTo-Json on mutated PSCustomObject graphs can recurse through
PSObject metadata and exhaust RAM. This helper loads the workflow JSON with
Python and applies a flat patch file of primitives.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--patches", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    workflow = json.loads(Path(args.workflow).read_text(encoding="utf-8-sig"))
    patches = json.loads(Path(args.patches).read_text(encoding="utf-8-sig"))

    if patches.get("prompt") is not None:
        workflow["6"]["inputs"]["prompt"] = patches["prompt"]
    if patches.get("image"):
        workflow["1"]["inputs"]["image"] = patches["image"]

    if patches.get("silent"):
        workflow.pop("5", None)
        workflow.pop("13", None)
        workflow.get("14", {}).get("inputs", {}).pop("audio", None)

    width = int(patches["width"])
    height = int(patches["height"])
    length = int(patches["length"])
    workflow["17"]["inputs"]["width"] = width
    workflow["17"]["inputs"]["height"] = height
    workflow["17"]["inputs"]["crop"] = "disabled"
    workflow["6"]["inputs"]["width"] = width
    workflow["6"]["inputs"]["height"] = height
    workflow["6"]["inputs"]["length"] = length
    workflow["8"]["inputs"]["steps"] = int(patches["steps"])
    workflow["8"]["inputs"]["scheduler"] = patches["scheduler"]
    workflow["9"]["inputs"]["sampler_name"] = patches["sampler"]
    workflow["10"]["inputs"]["noise_seed"] = int(patches["seed"])
    workflow["14"]["inputs"]["fps"] = float(patches["fps"])
    workflow["16"]["inputs"]["strength_model"] = float(patches["lora_strength"])

    if patches.get("scale_output"):
        workflow["19"] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["12", 0],
                "upscale_method": "lanczos",
                "width": int(patches["output_width"]),
                "height": int(patches["output_height"]),
                "crop": "disabled",
            },
        }
        workflow["14"]["inputs"]["images"] = ["19", 0]

    if patches.get("loop_lock"):
        workflow["6"]["inputs"]["last_frame"] = ["18", 0]
    else:
        workflow["6"]["inputs"].pop("last_frame", None)

    workflow["15"]["inputs"]["filename_prefix"] = patches["filename_prefix"]

    payload = {"prompt": workflow, "client_id": patches["client_id"]}
    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Payload bytes: {Path(args.output).stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
