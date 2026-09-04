#!/usr/bin/env python3
"""Shared safety, reporting, and MP4 validation helpers for the 4K pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import secrets
import sys
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
import psutil


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_profile(path: Path | None, name: str | None) -> dict[str, Any] | None:
    if path is None and name is None:
        return None
    if path is None or name is None:
        raise ValueError("--profile-file and --profile-name must be supplied together")
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if config.get("schema_version") != 1:
        raise ValueError(f"Unsupported profile schema: {config.get('schema_version')!r}")
    profiles = config.get("profiles")
    if not isinstance(profiles, dict) or name not in profiles:
        raise KeyError(f"Unknown 4K profile: {name}")
    profile = dict(profiles[name])
    profile["name"] = name
    return profile


def validate_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("Output dimensions must be positive even integers")


def validate_source_and_targets(input_path: Path, output_path: Path, report_path: Path) -> None:
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output paths must be different")
    if output_path.resolve() == report_path.resolve():
        raise ValueError("Video and report paths must be different")
    if output_path.exists():
        raise FileExistsError(f"Output already exists: {output_path}")
    if report_path.exists():
        raise FileExistsError(f"Run report already exists: {report_path}")


def make_partial_path(final_path: Path) -> Path:
    token = secrets.token_hex(4)
    return final_path.with_name(f"{final_path.stem}.partial.{os.getpid()}.{token}{final_path.suffix}")


def failure_report_path(run_report: Path) -> Path:
    stem = run_report.stem
    if stem.endswith("_RUN"):
        stem = f"{stem[:-4]}_FAILED"
    else:
        stem = f"{stem}_FAILED"
    return run_report.with_name(f"{stem}{run_report.suffix or '.json'}")


def write_json_partial(final_path: Path, payload: dict[str, Any]) -> Path:
    if final_path.exists():
        raise FileExistsError(f"JSON output already exists: {final_path}")
    final_path.parent.mkdir(parents=True, exist_ok=True)
    partial = make_partial_path(final_path)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    with partial.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return partial


def publish_partial(partial: Path, final_path: Path) -> None:
    if partial.parent.resolve() != final_path.parent.resolve():
        raise ValueError("Partial and final paths must be in the same directory")
    if final_path.exists():
        raise FileExistsError(f"Refusing to replace existing file: {final_path}")
    os.rename(partial, final_path)


def atomic_write_json(final_path: Path, payload: dict[str, Any]) -> None:
    partial = write_json_partial(final_path, payload)
    publish_partial(partial, final_path)


def write_failure_report(run_report: Path, payload: dict[str, Any]) -> Path | None:
    failed_path = failure_report_path(run_report)
    if failed_path.exists():
        return None
    try:
        atomic_write_json(failed_path, payload)
    except Exception:
        return None
    return failed_path


def parse_mp4_boxes(path: Path) -> list[dict[str, Any]]:
    boxes: list[dict[str, Any]] = []
    file_size = path.stat().st_size
    offset = 0
    with path.open("rb") as handle:
        while offset + 8 <= file_size:
            handle.seek(offset)
            header = handle.read(8)
            if len(header) != 8:
                break
            size = int.from_bytes(header[:4], "big")
            box_type = header[4:8].decode("ascii", errors="replace")
            header_size = 8
            if size == 1:
                extended = handle.read(8)
                if len(extended) != 8:
                    raise ValueError(f"Truncated extended MP4 box at offset {offset}")
                size = int.from_bytes(extended, "big")
                header_size = 16
            elif size == 0:
                size = file_size - offset
            if size < header_size or offset + size > file_size:
                raise ValueError(f"Invalid MP4 box {box_type!r} at offset {offset}")
            boxes.append({"type": box_type, "offset": offset, "size": size})
            offset += size
    return boxes


def faststart_info(path: Path) -> dict[str, Any]:
    boxes = parse_mp4_boxes(path)
    moov = next((item for item in boxes if item["type"] == "moov"), None)
    mdat = next((item for item in boxes if item["type"] == "mdat"), None)
    return {
        "faststart": bool(moov and mdat and moov["offset"] < mdat["offset"]),
        "top_level_boxes": boxes,
    }


def _fraction_text(value: Fraction | None) -> str | None:
    return str(value) if value is not None else None


def probe_video(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with av.open(str(path)) as container:
        video_streams = list(container.streams.video)
        if len(video_streams) != 1:
            raise RuntimeError(f"Expected exactly one video stream, found {len(video_streams)}")
        video = video_streams[0]
        rate = Fraction(video.average_rate) if video.average_rate is not None else None
        pts: list[int | None] = []
        decoded = 0
        for frame in container.decode(video=0):
            pts.append(frame.pts)
            decoded += 1
        stream_types = [stream.type for stream in container.streams]
        duration_seconds = None
        if video.duration is not None and video.time_base is not None:
            duration_seconds = float(video.duration * video.time_base)
        info: dict[str, Any] = {
            "path": str(path.resolve()),
            "sha256": sha256_file(path),
            "file_bytes": path.stat().st_size,
            "codec": video.codec_context.name,
            "profile": video.codec_context.profile,
            "pixel_format": video.codec_context.pix_fmt,
            "width": video.codec_context.width,
            "height": video.codec_context.height,
            "fps": float(rate) if rate is not None else None,
            "fps_text": _fraction_text(rate),
            "declared_frames": video.frames,
            "decoded_frames": decoded,
            "duration_seconds": duration_seconds,
            "stream_types": stream_types,
            "silent": stream_types == ["video"],
            "pts": pts,
        }
    non_null_pts = [item for item in pts if item is not None]
    deltas = [second - first for first, second in zip(non_null_pts, non_null_pts[1:])]
    info.update(
        {
            "pts_all_present": len(non_null_pts) == len(pts),
            "pts_strictly_increasing": all(delta > 0 for delta in deltas),
            "pts_delta": deltas[0] if deltas and len(set(deltas)) == 1 else None,
            "pts_delta_stable": len(set(deltas)) <= 1,
            "first_pts": pts[0] if pts else None,
            "last_pts": pts[-1] if pts else None,
        }
    )
    info.update(faststart_info(path))
    return info


def validate_video(
    path: Path,
    *,
    width: int,
    height: int,
    fps: float,
    expected_frames: int,
) -> dict[str, Any]:
    info = probe_video(path)
    profile_text = str(info["profile"] or "").lower()
    errors: list[str] = []
    checks = {
        "codec_h264": info["codec"] == "h264",
        "profile_high": profile_text.startswith("high"),
        "pixel_format_yuv420p": info["pixel_format"] == "yuv420p",
        "dimensions": info["width"] == width and info["height"] == height,
        "fps": info["fps"] is not None and abs(float(info["fps"]) - fps) < 1e-6,
        "frame_count": info["decoded_frames"] == expected_frames,
        "silent_single_stream": info["silent"],
        "pts_all_present": info["pts_all_present"],
        "pts_strictly_increasing": info["pts_strictly_increasing"],
        "pts_delta_stable": info["pts_delta_stable"],
        "faststart": info["faststart"],
    }
    for name, passed in checks.items():
        if not passed:
            errors.append(name)
    info["checks"] = checks
    info["validation_errors"] = errors
    info["passed"] = not errors
    return info


class ResourceTracker:
    def __init__(self) -> None:
        self.process = psutil.Process()
        self.peak_system_used_gib = 0.0
        self.peak_process_rss_gib = 0.0
        self.sample()

    def sample(self) -> None:
        self.peak_system_used_gib = max(self.peak_system_used_gib, psutil.virtual_memory().used / 2**30)
        self.peak_process_rss_gib = max(self.peak_process_rss_gib, self.process.memory_info().rss / 2**30)

    def result(self) -> dict[str, float]:
        self.sample()
        return {
            "peak_system_ram_gib": self.peak_system_used_gib,
            "peak_process_ram_gib": self.peak_process_rss_gib,
        }


def environment_info() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "pyav": av.__version__,
        "psutil": psutil.__version__,
    }


def _probe_cli() -> int:
    parser = argparse.ArgumentParser(description="Probe a video without writing files")
    parser.add_argument("probe", nargs="?")
    parser.add_argument("--video", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(probe_video(args.video), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_probe_cli())
