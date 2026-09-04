#!/usr/bin/env python3
"""Perform reproducible 4K wallpaper validation, including repeated decode loops."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import zlib
from pathlib import Path
from typing import Any

import av
import numpy as np

from upscale_4k_common import (
    ResourceTracker,
    atomic_write_json,
    probe_video,
    sha256_file,
    utc_now,
)


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument(
        "--profile-file",
        type=Path,
        default=project_root / "presets" / "wallpaper_4k_profiles.json",
    )
    parser.add_argument("--generation-report", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--stdout-only", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--minutes", type=float, default=5.0)
    return parser.parse_args()


def mad(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.abs(first.astype(np.int16) - second.astype(np.int16)).mean())


def load_generation_report(path: Path | None, candidate_sha256: str) -> dict[str, Any]:
    if path is None:
        return {
            "present": False,
            "path": None,
            "sha256": None,
            "status_success": False,
            "complete_video": False,
            "candidate_hash_matches": False,
            "resource_evidence": False,
            "method": None,
            "scope": None,
        }
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    method = data.get("method")
    performance = data.get("performance") or {}
    resource_evidence = all(
        key in performance and performance[key] is not None
        for key in ("elapsed_seconds", "peak_system_ram_gib", "peak_process_ram_gib")
    )
    if method == "realesrgan_stream":
        resource_evidence = resource_evidence and all(
            key in performance and performance[key] is not None
            for key in ("peak_gpu_allocated_gib", "peak_gpu_reserved_gib", "peak_total_gpu_used_gib_sampled")
        )
    report_output = data.get("output") or {}
    return {
        "present": True,
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "status_success": data.get("status") == "success",
        "complete_video": data.get("complete_video") is True,
        "candidate_hash_matches": report_output.get("sha256") == candidate_sha256,
        "resource_evidence": resource_evidence,
        "method": method,
        "scope": data.get("scope"),
    }


def main() -> int:
    args = parse_args()
    if args.minutes <= 0:
        raise ValueError("--minutes must be positive")
    if args.stdout_only and args.json_output is not None:
        raise ValueError("--stdout-only and --json-output cannot be used together")
    if not args.video.is_file():
        raise FileNotFoundError(args.video)
    if not args.profile_file.is_file():
        raise FileNotFoundError(args.profile_file)
    if args.generation_report is not None and not args.generation_report.is_file():
        raise FileNotFoundError(args.generation_report)
    if args.json_output is not None and args.json_output.exists():
        raise FileExistsError(f"Validation report already exists: {args.json_output}")

    config = json.loads(args.profile_file.read_text(encoding="utf-8-sig"))
    if config.get("schema_version") != 1:
        raise ValueError(f"Unsupported profile schema: {config.get('schema_version')!r}")
    acceptance = config["acceptance"]
    metadata = probe_video(args.video)
    generation = load_generation_report(args.generation_report, metadata["sha256"])

    expected_frames = int(acceptance["frames"])
    fps = float(acceptance["fps"])
    target_frames = math.ceil(args.minutes * 60.0 * fps)
    duration_cycles = math.ceil(target_frames / expected_frames)
    cycles = duration_cycles if args.audit_only else max(duration_cycles, int(acceptance["minimum_cycles"]))

    tracker = ResourceTracker()
    started_at = utc_now()
    started = time.perf_counter()
    decoded_total = 0
    cycles_with_wrong_frame_count = 0
    pts_missing = 0
    pts_non_increasing = 0
    pts_delta_instability = 0
    pts_sequence_mismatch_cycles = 0
    checksum_mismatch_cycles = 0
    black_frames = 0
    flat_frames = 0
    reference_pts: list[int | None] | None = None
    reference_checksums: list[int] | None = None
    first_frame: np.ndarray | None = None
    last_frame: np.ndarray | None = None

    for cycle in range(cycles):
        checksums: list[int] = []
        pts_values: list[int | None] = []
        previous_pts: int | None = None
        cycle_deltas: list[int] = []
        cycle_count = 0
        with av.open(str(args.video)) as container:
            for frame in container.decode(video=0):
                pts_values.append(frame.pts)
                if frame.pts is None:
                    pts_missing += 1
                elif previous_pts is not None:
                    delta = frame.pts - previous_pts
                    cycle_deltas.append(delta)
                    if delta <= 0:
                        pts_non_increasing += 1
                if frame.pts is not None:
                    previous_pts = frame.pts
                array = frame.to_ndarray(format="rgb24")
                mean = float(array.mean())
                std = float(array.std())
                if mean < 1.0:
                    black_frames += 1
                if std < 1.0:
                    flat_frames += 1
                checksums.append(zlib.crc32(array))
                if first_frame is None:
                    first_frame = array.copy()
                last_frame = array
                cycle_count += 1
                tracker.sample()
        if len(set(cycle_deltas)) > 1:
            pts_delta_instability += 1
        if cycle_count != expected_frames:
            cycles_with_wrong_frame_count += 1
        if reference_checksums is None:
            reference_checksums = checksums
            reference_pts = pts_values
        else:
            if checksums != reference_checksums:
                checksum_mismatch_cycles += 1
            if pts_values != reference_pts:
                pts_sequence_mismatch_cycles += 1
        decoded_total += cycle_count
        if (cycle + 1) % 25 == 0 or cycle + 1 == cycles:
            print(f"Validated {cycle + 1}/{cycles} cycles ({decoded_total} decoded frames)", flush=True)

    elapsed = time.perf_counter() - started
    if first_frame is None or last_frame is None:
        boundary_mad = None
    else:
        boundary_mad = mad(last_frame, first_frame)

    profile_text = str(metadata.get("profile") or "").lower()
    media_checks = {
        "codec_h264": metadata["codec"] == "h264",
        "profile_high": profile_text.startswith("high"),
        "pixel_format_yuv420p": metadata["pixel_format"] == "yuv420p",
        "dimensions_3840x2160": metadata["width"] == int(acceptance["width"])
        and metadata["height"] == int(acceptance["height"]),
        "fps_24": metadata["fps"] is not None and abs(float(metadata["fps"]) - fps) < 1e-6,
        "declared_frames_61": metadata["declared_frames"] == expected_frames,
        "decoded_frames_61": metadata["decoded_frames"] == expected_frames,
        "single_silent_video_stream": metadata["silent"],
        "faststart": metadata["faststart"],
        "not_partial": ".partial." not in args.video.name,
    }
    repeated_decode_checks = {
        "all_cycles_have_61_frames": cycles_with_wrong_frame_count == 0,
        "pts_all_present": pts_missing == 0,
        "pts_strictly_increasing": pts_non_increasing == 0,
        "pts_delta_stable": pts_delta_instability == 0,
        "pts_sequence_identical_across_cycles": pts_sequence_mismatch_cycles == 0,
        "checksums_identical_across_cycles": checksum_mismatch_cycles == 0,
        "black_frames_zero": black_frames <= int(acceptance["black_frames_max"]),
        "flat_frames_zero": flat_frames <= int(acceptance["flat_frames_max"]),
        "loop_boundary_within_gate": boundary_mad is not None
        and boundary_mad <= float(acceptance["endpoint_boundary_mad_max"]),
    }
    duration_checks = {
        "requested_duration_decoded": decoded_total >= target_frames,
        "minimum_cycles_119": cycles >= int(acceptance["minimum_cycles"]),
        "minimum_decoded_frames_7259": decoded_total >= int(acceptance["minimum_decoded_frames"]),
        "minimum_virtual_seconds_300": decoded_total / fps >= float(acceptance["minimum_minutes"]) * 60.0,
    }
    generation_checks = {
        "generation_report_present": generation["present"],
        "generation_succeeded": generation["status_success"],
        "generation_complete_video": generation["complete_video"],
        "candidate_hash_matches_generation_report": generation["candidate_hash_matches"],
        "generation_resource_evidence": generation["resource_evidence"],
        "generation_scope_full": generation["scope"] == "full",
    }

    audit_pass = all(media_checks.values()) and all(repeated_decode_checks.values())
    formal_pass = audit_pass and all(duration_checks.values()) and all(generation_checks.values())
    result = {
        "schema_version": 1,
        "validation_mode": "audit" if args.audit_only else "formal",
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "command": [sys.executable, *sys.argv],
        "video": metadata,
        "generation_report": generation,
        "requested_minutes": args.minutes,
        "target_frames": target_frames,
        "validated_cycles": cycles,
        "decoded_frames": decoded_total,
        "virtual_playback_seconds": decoded_total / fps,
        "decode_wall_seconds": elapsed,
        "average_decode_fps": decoded_total / max(elapsed, 1e-9),
        "resource_usage": tracker.result(),
        "counters": {
            "cycles_with_wrong_frame_count": cycles_with_wrong_frame_count,
            "pts_missing": pts_missing,
            "pts_non_increasing": pts_non_increasing,
            "pts_delta_instability_cycles": pts_delta_instability,
            "pts_sequence_mismatch_cycles": pts_sequence_mismatch_cycles,
            "checksum_mismatch_cycles": checksum_mismatch_cycles,
            "black_frames": black_frames,
            "flat_frames": flat_frames,
        },
        "reference_pts": reference_pts,
        "reference_crc32": reference_checksums,
        "loop_boundary_mad": boundary_mad,
        "checks": {
            "media": media_checks,
            "repeated_decode": repeated_decode_checks,
            "duration": duration_checks,
            "generation": generation_checks,
        },
        "audit_pass": audit_pass,
        "overall_pass": formal_pass,
        "passed": audit_pass if args.audit_only else formal_pass,
    }

    if args.json_output is not None:
        atomic_write_json(args.json_output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
