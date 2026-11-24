"""The scan's text-layout check must not report a one-pixel difference as a defect at low zoom, and must still catch a real one."""
import sys
from argparse import Namespace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmeasure import qa_cli, textlayout  # noqa: E402

ZOOM = 3


def page(shift_px=0):
    image = np.full((100 * ZOOM, 120 * ZOOM, 3), 255, dtype=int)
    for index, top in enumerate((10, 30, 50)):
        y = top * ZOOM + (shift_px if index == 1 else 0)
        image[y : y + 8 * ZOOM, 10 * ZOOM : 70 * ZOOM] = 30
    return image


def args(**overrides):
    return Namespace(url=None, zoom=ZOOM, pdf="x.pdf", page=1, label="v0", sheet=0, attr="data-wb", sheet_selector=None, css_per_pt=8, **overrides)


def test_a_one_pixel_difference_is_below_the_default_tolerance_but_not_a_defect_at_3_px_per_pt():
    exact = textlayout.compare(textlayout.segments(page(), ZOOM), textlayout.segments(page(1), ZOOM))
    assert exact["problems"], "premise: 1 px = 0.33 pt is over the 0.3 pt pitch tolerance"
    result, note = qa_cli._text_layout(args(), page(), page(1), Path("."))
    assert result["problems"] == [] and "widened" in note


def test_a_real_shift_is_still_reported_at_3_px_per_pt():
    result, _ = qa_cli._text_layout(args(), page(), page(6), Path("."))  # 2 pt
    assert result["problems"]
