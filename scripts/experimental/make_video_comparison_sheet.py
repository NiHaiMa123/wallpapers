#!/usr/bin/env python3
"""Build a row-per-video contact sheet for visual seed comparison."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import av
from PIL import Image, ImageDraw, ImageFont


def label_for(path: Path) -> str:
    match = re.search(r"_s(\d{3})_seed(\d+)_", path.name)
    if match:
        return f"seed {match.group(2)}  LoRA {int(match.group(1)) / 100:.2f}"
    return path.stem


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("videos", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--indexes", nargs="+", required=True, type=int)
    parser.add_argument("--box", nargs=4, type=float, default=(0, 0, 1, 1))
    parser.add_argument("--cell-width", type=int, default=280)
    args = parser.parse_args()

    decoded: list[tuple[Path, list[Image.Image]]] = []
    for path in args.videos:
        with av.open(str(path)) as container:
            frames = [frame.to_image().convert("RGB") for frame in container.decode(video=0)]
        invalid = [index for index in args.indexes if index < 0 or index >= len(frames)]
        if invalid:
            raise ValueError(f"{path}: indexes outside 0..{len(frames) - 1}: {invalid}")
        decoded.append((path, frames))

    source_width, source_height = decoded[0][1][0].size
    left, top, right, bottom = args.box
    crop = (
        round(left * source_width), round(top * source_height),
        round(right * source_width), round(bottom * source_height),
    )
    crop_width, crop_height = crop[2] - crop[0], crop[3] - crop[1]
    cell_height = round(args.cell_width * crop_height / crop_width)
    row_label_width = 230
    column_label_height = 30
    sheet = Image.new(
        "RGB",
        (row_label_width + args.cell_width * len(args.indexes),
         column_label_height + cell_height * len(decoded)),
        "#151515",
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for column, frame_index in enumerate(args.indexes):
        draw.text((row_label_width + column * args.cell_width + 8, 9), f"frame {frame_index}", fill="white", font=font)
    for row, (path, frames) in enumerate(decoded):
        y = column_label_height + row * cell_height
        draw.text((8, y + 10), label_for(path), fill="white", font=font)
        for column, frame_index in enumerate(args.indexes):
            tile = frames[frame_index].crop(crop).resize((args.cell_width, cell_height), Image.Resampling.LANCZOS)
            sheet.paste(tile, (row_label_width + column * args.cell_width, y))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output, quality=96)
    print(f"output={args.output.resolve()}")
    print(f"videos={len(decoded)} indexes={args.indexes} crop={crop}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
