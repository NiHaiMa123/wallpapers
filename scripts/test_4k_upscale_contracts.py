#!/usr/bin/env python3
"""Contract tests for the Step 10 4K safety and naming rules."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from upscale_4k_common import (
    atomic_write_json,
    failure_report_path,
    faststart_info,
    make_partial_path,
    publish_partial,
    validate_source_and_targets,
    write_json_partial,
)


class Step10ContractsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project_root = Path(__file__).resolve().parents[1]
        cls.config = json.loads(
            (cls.project_root / "presets" / "wallpaper_4k_profiles.json").read_text(encoding="utf-8")
        )

    def test_profile_schema_and_default(self) -> None:
        self.assertEqual(self.config["schema_version"], 1)
        self.assertIn(self.config["default_profile"], self.config["profiles"])
        self.assertEqual(self.config["default_profile"], "temporal_safe")
        self.assertEqual(
            set(self.config["profiles"]),
            {"temporal_safe", "ai_detail_2k", "ai_detail_2k_60", "ai_detail_default"},
        )
        ai = self.config["profiles"]["ai_detail_default"]
        self.assertGreater(ai["tile"], ai["overlap"])
        self.assertFalse(ai["interpolation"])
        for profile in self.config["profiles"].values():
            if "abort_ram_gib" in profile:
                self.assertEqual(profile["abort_ram_gib"], 31.0)

    def test_canonical_output_names(self) -> None:
        identity = "MiniMaxH3_Live2D_Seed2026082904"
        template = self.config["naming"]["output_template"]
        names = {
            key: template.format(
                identity=identity,
                width=value["width"],
                height=value["height"],
                fps=value["fps"],
                method_tag=value["method_tag"],
            )
            for key, value in self.config["profiles"].items()
        }
        self.assertEqual(
            names["temporal_safe"],
            "MiniMaxH3_Live2D_Seed2026082904_3840x2160_24fps_LANCZOS_LOOP_SILENT.mp4",
        )
        self.assertEqual(
            names["ai_detail_default"],
            "MiniMaxH3_Live2D_Seed2026082904_3840x2160_24fps_RealESRGANx4plus_LOOP_SILENT.mp4",
        )
        self.assertEqual(
            names["ai_detail_2k"],
            "MiniMaxH3_Live2D_Seed2026082904_2560x1440_24fps_RealESRGANx4plus_LOOP_SILENT.mp4",
        )
        self.assertEqual(
            names["ai_detail_2k_60"],
            "MiniMaxH3_Live2D_Seed2026082904_2560x1440_60fps_RealESRGANx4plus_LOOP_SILENT.mp4",
        )

    def test_partial_path_stays_in_target_directory(self) -> None:
        target = Path("D:/example/output/video.mp4")
        partial = make_partial_path(target)
        self.assertEqual(partial.parent, target.parent)
        self.assertEqual(partial.suffix, ".mp4")
        self.assertIn(".partial.", partial.name)

    def test_atomic_json_publish_and_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.json"
            atomic_write_json(target, {"status": "success"})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["status"], "success")
            with self.assertRaises(FileExistsError):
                atomic_write_json(target, {"status": "replacement"})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["status"], "success")

    def test_publish_refuses_to_damage_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "candidate.mp4"
            target.write_bytes(b"original")
            partial = root / "candidate.partial.1.test.mp4"
            partial.write_bytes(b"replacement")
            with self.assertRaises(FileExistsError):
                publish_partial(partial, target)
            self.assertEqual(target.read_bytes(), b"original")
            self.assertEqual(partial.read_bytes(), b"replacement")

    def test_video_target_collision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            output = root / "output.mp4"
            report = root / "output_RUN.json"
            source.write_bytes(b"source")
            output.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                validate_source_and_targets(source, output, report)
            self.assertEqual(output.read_bytes(), b"existing")

    def test_input_output_identity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.mp4"
            report = Path(directory) / "report.json"
            source.write_bytes(b"source")
            with self.assertRaises(ValueError):
                validate_source_and_targets(source, source, report)

    def test_top_level_mp4_faststart_parser(self) -> None:
        def box(name: bytes, payload: bytes = b"") -> bytes:
            return (8 + len(payload)).to_bytes(4, "big") + name + payload

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fast = root / "fast.mp4"
            slow = root / "slow.mp4"
            fast.write_bytes(box(b"ftyp") + box(b"moov") + box(b"mdat", b"frame"))
            slow.write_bytes(box(b"ftyp") + box(b"mdat", b"frame") + box(b"moov"))
            self.assertTrue(faststart_info(fast)["faststart"])
            self.assertFalse(faststart_info(slow)["faststart"])

    def test_report_partial_can_be_published(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "run_RUN.json"
            partial = write_json_partial(target, {"status": "success"})
            self.assertFalse(target.exists())
            publish_partial(partial, target)
            self.assertTrue(target.exists())

    def test_failure_report_name(self) -> None:
        self.assertEqual(failure_report_path(Path("video_RUN.json")).name, "video_FAILED.json")
        self.assertEqual(failure_report_path(Path("video.json")).name, "video_FAILED.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
