"""High-zoom tiles: they cover the page, skip blank areas, are re-rendered (small parts keep their pixels) and small enough to be viewed unscaled."""
import sys
from argparse import Namespace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmeasure import tiles  # noqa: E402

ZOOM = 6
PAGE_PT = (300.0, 300.0)


def page_image(with_marker=True) -> Image.Image:
    image = Image.new("RGB", (int(PAGE_PT[0] * ZOOM), int(PAGE_PT[1] * ZOOM)), (255, 255, 255))
    if with_marker:  # a 7 pt numbered-marker-sized red circle at (50, 60) pt
        ImageDraw.Draw(image).ellipse([50 * ZOOM, 60 * ZOOM, 57 * ZOOM, 67 * ZOOM], fill=(220, 50, 50))
    return image


def test_tile_size_keeps_every_picture_under_the_view_limit():
    assert tiles.tile_size_pt(6, "pdf") == 250 and tiles.tile_size_pt(6, "pair") == 125
    assert tiles.tile_size_pt(8, "pair") * 8 * 2 <= tiles.MAX_VIEW_PX


def test_grid_covers_the_whole_page_with_overlap():
    boxes = tiles.grid(595, 842, 125)
    covered = np.zeros((842, 595), dtype=bool)
    for _, (x, top, width, height) in boxes:
        covered[int(top) : int(top + height) + 1, int(x) : int(x + width) + 1] = True
    assert covered.all()
    assert boxes[0][0] == "r0c0" and len({box_id for box_id, _ in boxes}) == len(boxes)
    (_, first), (_, second) = boxes[0], boxes[1]
    assert first[0] + first[2] - second[0] == tiles.OVERLAP_PT  # neighbours share a strip


def test_blank_tiles_are_skipped_and_the_marker_keeps_its_pixels(tmp_path):
    manifest = tiles.write_tiles(tmp_path, 9, "pdf", page_image(), None, ZOOM, PAGE_PT)
    drawn = [t for t in manifest["tiles"] if not t["blank"]]
    assert manifest["blank_count"] == len(manifest["tiles"]) - len(drawn) > 0 and len(drawn) >= 1
    folder = tiles.tiles_dir(tmp_path, 9, "pdf")
    picture = np.array(Image.open(folder / drawn[0]["file"]).convert("RGB")).astype(int)
    red = (picture[..., 0] > 180) & (picture[..., 1] < 100)
    assert red.sum() > 1000  # a 7 pt circle at 6 px/pt is about 1400 px: re-rendered, not shrunk
    assert max(picture.shape[:2]) <= tiles.MAX_VIEW_PX + 40  # label bar included


def test_pair_tiles_show_both_pages_side_by_side_within_the_limit(tmp_path):
    manifest = tiles.write_tiles(tmp_path, 9, "pair", page_image(), page_image(with_marker=False), ZOOM, PAGE_PT)
    drawn = [t for t in manifest["tiles"] if not t["blank"]]
    assert drawn  # the marker exists only in the PDF half: the tile is not blank
    picture = Image.open(tiles.tiles_dir(tmp_path, 9, "pair") / drawn[0]["file"])
    assert picture.width <= tiles.MAX_VIEW_PX + 40
    with pytest.raises(ValueError, match="rebuilt page image"):
        tiles.write_tiles(tmp_path, 9, "pair", page_image(), None, ZOOM, PAGE_PT)


def test_manifest_problems_reject_missing_and_low_zoom_tiles(tmp_path):
    assert "no pdf tiles" in tiles.manifest_problems(None, "pdf", "page 9")[0]
    manifest = tiles.write_tiles(tmp_path, 9, "pdf", page_image(), None, ZOOM, PAGE_PT)
    assert tiles.manifest_problems(manifest, "pdf", "page 9") == []
    assert "under the minimum" in tiles.manifest_problems({**manifest, "zoom": 3}, "pdf", "page 9")[0]


def test_the_command_refuses_a_zoom_that_is_too_low(tmp_path, capsys):
    args = Namespace(zoom=3, output=str(tmp_path), page=9, mode="pdf", run_dir=None, pdf="x.pdf", url=None)
    assert tiles.command_tiles(args) == 2
    assert "under the minimum" in capsys.readouterr().out
