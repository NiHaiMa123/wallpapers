#!/usr/bin/env python3
"""Create an enlarged crop sheet from evenly spaced video frames."""

from __future__ import annotations

import argparse
from pathlib import Path

import av
from PIL import Image, ImageDraw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--box", nargs=4, type=float, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"), required=True)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--indexes", nargs="+", type=int, help="Exact zero-based frame indexes; overrides --count")
    parser.add_argument("--columns", type=int, help="Wrap the sheet after this many columns")
    parser.add_argument("--cell-width", type=int, default=420)
    args = parser.parse_args()

    with av.open(str(args.video)) as container:
        frames = [frame.to_image().convert("RGB") for frame in container.decode(video=0)]
    if not frames:
        raise RuntimeError("Video contains no frames")

    if args.indexes:
        indexes = args.indexes
        invalid = [index for index in indexes if index < 0 or index >= len(frames)]
        if invalid:
            raise ValueError(f"Frame indexes outside 0..{len(frames) - 1}: {invalid}")
    else:
        if args.count < 2:
            raise ValueError("--count must be at least 2")
        indexes = [round((len(frames) - 1) * index / (args.count - 1)) for index in range(args.count)]
    width, height = frames[0].size
    left, top, right, bottom = args.box
    crop_box = (round(left * width), round(top * height), round(right * width), round(bottom * height))
    crop_width = crop_box[2] - crop_box[0]
    crop_height = crop_box[3] - crop_box[1]
    cell_height = round(args.cell_width * crop_height / crop_width)
    label_height = 28
    columns = args.columns or len(indexes)
    if columns < 1:
        raise ValueError("--columns must be at least 1")
    rows = (len(indexes) + columns - 1) // columns
    sheet = Image.new("RGB", (args.cell_width * columns, (cell_height + label_height) * rows), "#171717")
    draw = ImageDraw.Draw(sheet)
    for slot, frame_index in enumerate(indexes):
        crop = frames[frame_index].crop(crop_box).resize((args.cell_width, cell_height), Image.Resampling.LANCZOS)
        column = slot % columns
        row = slot // columns
        x = column * args.cell_width
        y = row * (cell_height + label_height)
        sheet.paste(crop, (x, y + label_height))
        draw.text((x + 8, y + 7), f"frame {frame_index}", fill="white")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output, quality=96)
    print(f"output={args.output.resolve()}")
    print(f"source={width}x{height} crop={crop_box} indexes={indexes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
