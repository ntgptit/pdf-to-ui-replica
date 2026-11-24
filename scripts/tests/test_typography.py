"""Typography scores on real text (DejaVu fonts): same font passes even with other text; size, weight, family, indent and spacing errors are caught
at the agreed levels (PASS >= 95 %, WARNING < 95 %, ERROR < 92 %)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmeasure import typography  # noqa: E402

FONTS = Path("/usr/share/fonts/truetype/dejavu")
pytestmark = pytest.mark.skipif(not (FONTS / "DejaVuSans.ttf").exists(), reason="DejaVu fonts not installed")
ZOOM = 8
TEXT_A = ["The quick brown fox jumps over", "a lazy dog while reading books", "Single vowels and how to write"]
TEXT_B = ["Read the vowels and write them", "Hangul letters are drawn in order", "Practice every stroke slowly now"]


def page(font="DejaVuSans.ttf", size=10.0, lines=TEXT_A, x=20.0, pitch=16.0):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (300 * ZOOM, 120 * ZOOM), "white")
    draw = ImageDraw.Draw(image)
    face = ImageFont.truetype(str(FONTS / font), int(round(size * ZOOM)))
    for index, text in enumerate(lines):
        draw.text((x * ZOOM, (20 + index * pitch) * ZOOM), text, font=face, fill=(20, 20, 20))
    return np.array(image)


BASE = None


def scores(other, **cfg):
    global BASE
    if BASE is None:
        BASE = page()
    result = typography.compare(BASE, other, ZOOM, cfg)
    worst = {attr: min(style["scores"].get(attr, 1.0) for style in result["styles"]) for attr in typography.ATTRIBUTES}
    return result, worst


def test_identical_and_same_font_with_other_text_pass():
    result, worst = scores(page())
    assert result["verdict"] == "PASS" and min(worst.values()) == 1.0 and result["matched"] == 3
    result, worst = scores(page(lines=TEXT_B), same_text=False)
    assert result["verdict"] == "PASS", worst
    assert not result["indent_scored"] and all("indent" not in style["scores"] for style in result["styles"])


def test_size_error_is_graded():
    assert scores(page(size=10.3))[0]["verdict"] == "PASS"
    result, worst = scores(page(size=11.0))
    assert result["verdict"] == "ERROR" and worst["size"] < 0.92


def test_bold_is_a_weight_error_and_serif_or_mono_a_family_error():
    result, worst = scores(page("DejaVuSans-Bold.ttf"))
    assert result["verdict"] == "ERROR" and worst["weight"] < 0.92 and worst["size"] >= 0.95  # weight is normalised: not a size error
    assert scores(page("DejaVuSerif.ttf"))[1]["family"] < 0.92
    assert scores(page("DejaVuSansMono.ttf"))[1]["family"] < 0.95


def test_indent_and_spacing_are_graded():
    assert scores(page(x=20.3))[1]["indent"] >= 0.95
    assert scores(page(x=21.0))[1]["indent"] < 0.92
    assert scores(page(pitch=16.5))[1]["spacing"] >= 0.95
    assert 0.92 <= scores(page(pitch=17.2))[1]["spacing"] < 0.95  # WARNING


def test_spec_reads_line_pitch_and_indents_of_the_pdf():
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (300 * ZOOM, 120 * ZOOM), "white")
    draw = ImageDraw.Draw(image)
    face = ImageFont.truetype(str(FONTS / "DejaVuSans.ttf"), 10 * ZOOM)
    for index, text in enumerate(TEXT_A):
        draw.text(((20 if index != 1 else 32) * ZOOM, (20 + index * 16) * ZOOM), text, font=face, fill=(20, 20, 20))
    result = typography.spec(np.array(image), ZOOM)
    style = result["styles"][0]
    assert style["lines"] == 3 and abs(style["line_pitch_median"] - 16) < 0.1
    assert len(style["left_edges"]) == 3 and max(style["left_edges"]) - min(style["left_edges"]) == pytest.approx(12, abs=1.5)


def test_levels():
    assert (typography.level(0.95), typography.level(0.949), typography.level(0.92), typography.level(0.919)) == ("PASS", "WARNING", "WARNING", "ERROR")
