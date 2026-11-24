"""High-zoom tiles: the whole page cut into pieces that are rendered from the source at >= 6 px/pt and small enough to be looked at without being scaled down.

Why: a whole page at 1.4-3 px/pt shrinks further when it is shown to the viewer (a two-page picture ends up near 1.7 px/pt), and an enlarged 3 px/pt crop
is still 3 px/pt of information. Small parts (numbered stroke-order circles, arrowheads, dotted guides, hairlines, taper of a brush stroke) are lost in both.
Tiles are re-rendered, never enlarged, and every tile carries its box in points so that findings can be written down in pt.

Two modes: `pdf` (the PDF alone: object inventory, phase 2A) and `pair` (PDF | rebuilt page: visual QA, phase 10).
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
from PIL import Image

from . import visual

MIN_DETAIL_ZOOM = 6  # px per point: below this the harness rejects the tiles
MAX_VIEW_PX = 1500  # longest edge of one tile picture, so the viewer does not scale it down
OVERLAP_PT = 6.0  # neighbouring tiles share a strip so that nothing is cut in half unseen
BLANK_INK_SHARE = 0.0005  # share of non-white pixels under which a tile is blank
MODES = ("pdf", "pair")
MANIFEST = "tiles.json"


def tile_size_pt(zoom: int, mode: str) -> float:
    """A pair tile is two pictures side by side, so it covers half the area of a single-picture tile at the same zoom."""
    return math.floor(MAX_VIEW_PX / (zoom * (2 if mode == "pair" else 1)))


def grid(page_w: float, page_h: float, tile_pt: float, overlap: float = OVERLAP_PT) -> list[tuple[str, list[float]]]:
    """Boxes [x, top, w, h] in points that cover the page, in reading order, ids r<row>c<col>."""
    step = tile_pt - overlap
    cols, rows = max(1, math.ceil((page_w - overlap) / step)), max(1, math.ceil((page_h - overlap) / step))
    boxes = []
    for row in range(rows):
        for col in range(cols):
            x, top = col * step, row * step
            boxes.append((f"r{row}c{col}", [round(x, 2), round(top, 2), round(min(tile_pt, page_w - x), 2), round(min(tile_pt, page_h - top), 2)]))
    return boxes


def ink_share(tile: Image.Image) -> float:
    return float((np.array(tile.convert("L")) < 235).mean())


def tiles_dir(output: str | Path, page: int, mode: str) -> Path:
    return Path(output) / "pages" / f"page-{page:03d}" / f"tiles-{mode}"


def cut(image: Image.Image, box: list[float], zoom: int) -> Image.Image:
    x, top, width, height = (round(v * zoom) for v in box)
    return image.crop((x, top, x + width, top + height))


def write_tiles(output: str | Path, page: int, mode: str, pdf_image: Image.Image, react_image: Image.Image | None, zoom: int, page_pt: tuple[float, float]) -> dict:
    """Cut both images the same way and write one picture per non-blank tile plus tiles.json. Returns the manifest."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if mode == "pair" and react_image is None:
        raise ValueError("pair tiles need the rebuilt page image")
    folder = tiles_dir(output, page, mode)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.png"):
        old.unlink()
    entries = []
    for tile_id, box in grid(page_pt[0], page_pt[1], tile_size_pt(zoom, mode)):
        pdf_tile = cut(pdf_image, box, zoom)
        react_tile = cut(react_image, box, zoom) if react_image is not None else None
        blank = ink_share(pdf_tile) < BLANK_INK_SHARE and (react_tile is None or ink_share(react_tile) < BLANK_INK_SHARE)
        entry = {"id": tile_id, "box_pt": box, "blank": blank, "file": None}
        if not blank:
            name = f"{tile_id}.png"
            title = f"x={box[0]:g} top={box[1]:g} pt  {zoom} px/pt"
            parts = [(f"PDF  {title}", np.array(pdf_tile).astype(int))] + ([(f"REBUILT  {title}", np.array(react_tile).astype(int))] if react_tile is not None else [])
            visual.side_by_side(parts, folder / name)
            entry["file"] = name
        entries.append(entry)
    manifest = {
        "mode": mode, "page": page, "zoom": zoom, "page_pt": [round(page_pt[0], 3), round(page_pt[1], 3)], "tile_pt": tile_size_pt(zoom, mode), "overlap_pt": OVERLAP_PT,
        "created": time.time(), "blank_count": sum(1 for e in entries if e["blank"]), "tiles": entries,
    }
    (folder / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def read_manifest(output: str | Path, page: int, mode: str) -> dict | None:
    path = tiles_dir(output, page, mode) / MANIFEST
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def manifest_problems(manifest: dict | None, mode: str, where: str) -> list[str]:
    """Why these tiles cannot count as a detail pass (empty = they can)."""
    if manifest is None:
        return [f"no {mode} tiles for {where}: run `tiles --mode {mode}` (zoom >= {MIN_DETAIL_ZOOM} px/pt)"]
    if manifest["zoom"] < MIN_DETAIL_ZOOM:
        return [f"{mode} tiles of {where} were made at {manifest['zoom']} px/pt, under the minimum {MIN_DETAIL_ZOOM}"]
    return []


# ---- command ----------------------------------------------------------------------------------------------------------------------------
def command_tiles(args) -> int:
    from .cli import page_width

    zoom = args.zoom
    if zoom < MIN_DETAIL_ZOOM:
        print(f"tiles: zoom {zoom} is under the minimum {MIN_DETAIL_ZOOM} px/pt (small parts need it)")
        return 2
    folder = tiles_dir(args.output, args.page, args.mode)
    work = Path(args.run_dir) / "working-images" if args.run_dir else folder.parent / "_work"
    work.mkdir(parents=True, exist_ok=True)
    pdf_path = visual.render_pdf_page(args.pdf, args.page, work / f"pdf-{args.page}-z{zoom}.png", zoom)
    Image.MAX_IMAGE_PIXELS = None
    pdf_image = Image.open(pdf_path).convert("RGB")
    react_image = None
    if args.mode == "pair":
        if not args.url:
            print("tiles: pair mode needs --url (the page is captured at the same zoom)")
            return 2
        react_path = visual.capture_react(args.url, work / f"react-z{zoom}", page_width(args.pdf, args.page), args.sheet, zoom, args.attr, args.sheet_selector, args.css_per_pt)
        react_image = Image.open(react_path).convert("RGB")
        if abs(react_image.width - pdf_image.width) > visual.SIZE_TOLERANCE_PX or abs(react_image.height - pdf_image.height) > visual.SIZE_TOLERANCE_PX:
            print(f"tiles: size differs (PDF {pdf_image.size}, rebuilt {react_image.size}); fix the page box first, nothing was cut")
            return 2
    page_pt = (pdf_image.width / zoom, pdf_image.height / zoom)
    manifest = write_tiles(args.output, args.page, args.mode, pdf_image, react_image, zoom, page_pt)
    shown = len(manifest["tiles"]) - manifest["blank_count"]
    print(f"tiles: {shown} picture(s) in {folder} ({manifest['blank_count']} blank tile(s) skipped); {manifest['tile_pt']:g} pt per tile at {zoom} px/pt. Look at every picture, then `state view --view-kind {'inventory' if args.mode == 'pdf' else 'qa'}`.")
    return 0


def register(add) -> None:
    cmd = add("tiles", command_tiles, "cut a page into high-zoom tiles (re-rendered, never enlarged): --mode pdf for the inventory, --mode pair for PDF | rebuilt page")
    cmd.add_argument("--pdf", required=True)
    cmd.add_argument("--page", type=int, required=True)
    cmd.add_argument("--output", required=True)
    cmd.add_argument("--mode", choices=MODES, default="pdf")
    cmd.add_argument("--zoom", type=int, default=MIN_DETAIL_ZOOM, help=f"px per point, at least {MIN_DETAIL_ZOOM}")
    cmd.add_argument("--url", help="pair: the lab URL of the rebuilt page")
    cmd.add_argument("--sheet", type=int, default=0)
    cmd.add_argument("--attr", default="data-wb")
    cmd.add_argument("--sheet-selector")
    cmd.add_argument("--css-per-pt", type=float, default=8)
    cmd.add_argument("--run-dir")
