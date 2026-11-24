"""Tile screenshots into one contact sheet, each under its page name."""

import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

GUTTER = 16
LABEL_HEIGHT = 22
BACKGROUND = (245, 245, 245)
INK = (30, 30, 30)
#: Tall pages are cut off at this many pixels once scaled, so that one long
#: page cannot swamp the sheet: the tile shows the top of the page.
MAX_TILE_HEIGHT = 720


def _font() -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for candidate in ("Helvetica.ttc", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, 14)
        except OSError:
            continue
    return ImageFont.load_default()


def label_for(path: Path) -> str:
    """``season-edit-1440.png`` is labelled ``season-edit``."""
    return re.sub(r"-\d+$", "", path.stem)


def sheet(
    files: list[Path],
    out: Path,
    columns: int = 4,
    tile_width: int = 360,
    max_tile_height: int = MAX_TILE_HEIGHT,
):
    """
    Write one PNG with every image scaled to ``tile_width`` in a grid of
    ``columns``, the page name drawn above each, and a gutter all round. An
    image taller than ``max_tile_height`` once scaled shows only its top.
    """
    columns = max(1, columns)
    tiles = []
    for path in files:
        with Image.open(path) as source:
            image = source.convert("RGB")
        height = max(1, round(image.height * tile_width / image.width))
        scaled = image.resize((tile_width, height), Image.LANCZOS)
        scaled = scaled.crop((0, 0, tile_width, min(height, max_tile_height)))
        tiles.append((label_for(Path(path)), scaled))

    rows = [tiles[i : i + columns] for i in range(0, len(tiles), columns)]
    row_heights = [max(t.height for _, t in row) + LABEL_HEIGHT for row in rows]
    width = columns * tile_width + (columns + 1) * GUTTER
    height = sum(row_heights) + (len(rows) + 1) * GUTTER
    canvas = Image.new("RGB", (width, max(height, 1)), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    font = _font()

    y = GUTTER
    for row, row_height in zip(rows, row_heights):
        x = GUTTER
        for label, tile in row:
            draw.text((x, y + 2), label, fill=INK, font=font)
            canvas.paste(tile, (x, y + LABEL_HEIGHT))
            x += tile_width + GUTTER
        y += row_height + GUTTER

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="contact")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--tile-width", type=int, default=360)
    parser.add_argument("--max-tile-height", type=int, default=MAX_TILE_HEIGHT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    files = sorted(
        p
        for p in args.run_dir.glob(f"*-{args.width}.png")
        if not p.name.startswith("contact-")
    )
    if not files:
        print(f"contact: no *-{args.width}.png in {args.run_dir}", file=sys.stderr)
        return 1
    out = args.out or args.run_dir / f"contact-{args.width}.png"
    sheet(files, out, args.columns, args.tile_width, args.max_tile_height)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
