"""Build a conservative 1080p loop-keyframe set for RIFE validation.

This is deliberately not a generative animation step.  It applies very small,
cyclic layer motion and glow changes to a trusted reference while restoring a
feathered face patch from the source on every keyframe.  That makes the test
useful for separating interpolation defects from H3 identity hallucination.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


TARGET_SIZE = (1920, 1080)
KEYFRAME_COUNT = 7  # 0..6, with frame 6 exactly equal to frame 0


def feathered_ellipse(size: tuple[int, int], box: tuple[int, int, int, int], blur: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse(box, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur))


def transform_about(
    image: Image.Image,
    scale: float,
    dx: float,
    dy: float,
    center: tuple[float, float],
) -> Image.Image:
    """Return an affine-transformed copy, keeping the requested center stable."""
    cx, cy = center
    inv = 1.0 / scale
    # PIL affine maps output coordinates back to source coordinates.
    matrix = (
        inv,
        0.0,
        cx - (cx + dx) * inv,
        0.0,
        inv,
        cy - (cy + dy) * inv,
    )
    return image.transform(
        image.size,
        Image.Transform.AFFINE,
        matrix,
        resample=Image.Resampling.BICUBIC,
    )


def purple_glow_mask(image: Image.Image) -> Image.Image:
    r, g, b = image.split()
    rg = ImageChops.subtract(r, g)
    bg = ImageChops.subtract(b, g)
    violet = ImageChops.lighter(rg, bg)
    # Retain only clearly violet details, then soften the emitted glow.
    violet = violet.point(lambda x: 0 if x < 18 else min(255, (x - 18) * 4))
    return violet.filter(ImageFilter.GaussianBlur(8))


def build_frames(source: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = Image.open(source).convert("RGB").resize(TARGET_SIZE, Image.Resampling.LANCZOS)
    w, h = base.size

    # Broad central layer: hair, sleeves, skirt, legs and sword.  The motion is
    # tiny enough that imperfect automatic separation is not distracting.
    subject_mask = feathered_ellipse(
        base.size,
        (int(w * 0.285), int(h * 0.005), int(w * 0.735), int(h * 0.985)),
        blur=34,
    )
    # Lock face/irises to the trusted source on every keyframe.
    face_mask = feathered_ellipse(
        base.size,
        (int(w * 0.495), int(h * 0.070), int(w * 0.625), int(h * 0.315)),
        blur=18,
    )
    glow_mask = purple_glow_mask(base)
    violet_layer = Image.new("RGB", base.size, (150, 88, 255))

    paths: list[Path] = []
    first_frame: Image.Image | None = None
    for index in range(KEYFRAME_COUNT):
        if index == KEYFRAME_COUNT - 1 and first_frame is not None:
            frame = first_frame.copy()
        else:
            phase = 2.0 * math.pi * index / (KEYFRAME_COUNT - 1)
            sway = math.sin(phase)
            breathe = math.sin(phase - math.pi / 2.0)
            moved = transform_about(
                base,
                scale=1.0 + 0.0016 * breathe,
                dx=2.2 * sway,
                dy=1.2 * breathe,
                center=(w * 0.555, h * 0.90),
            )
            frame = Image.composite(moved, base, subject_mask)

            # A restrained cyclic pulse on existing purple effects only.
            glow_strength = int(8 + 8 * (0.5 + 0.5 * math.sin(phase + 0.6)))
            local_glow = glow_mask.point(lambda x, s=glow_strength: x * s // 255)
            frame = Image.composite(violet_layer, frame, local_glow)

            # Restore the face after every other operation so iris pixels cannot
            # change hue between authored keyframes.
            frame = Image.composite(base, frame, face_mask)
            if index == 0:
                first_frame = frame.copy()

        path = output_dir / f"{index:03d}.png"
        frame.save(path, format="PNG", compress_level=4)
        paths.append(path)

    # Face contact sheet is a quick visual invariant check before interpolation.
    face_box = (int(w * 0.49), int(h * 0.06), int(w * 0.635), int(h * 0.33))
    crops = [Image.open(path).convert("RGB").crop(face_box) for path in paths]
    cw, ch = crops[0].size
    sheet = Image.new("RGB", (cw * len(crops), ch), (24, 24, 24))
    for index, crop in enumerate(crops):
        sheet.paste(crop, (index * cw, 0))
    sheet.save(output_dir.parent / "keyframe_face_lock_sheet.jpg", quality=95)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    paths = build_frames(args.source, args.output_dir)
    print(f"created={len(paths)} size={TARGET_SIZE[0]}x{TARGET_SIZE[1]}")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
