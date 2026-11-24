"""Tests that need no PDF and no browser: colour conversion, shapes, text lines, roles, invariants, compare, zoom and text metrics."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmeasure import textmetrics, zoom  # noqa: E402
from pdfmeasure.colors import cmyk_to_rgb, to_hex, to_rgb  # noqa: E402
from pdfmeasure.compare import Dom, Metric, run_checks  # noqa: E402
from pdfmeasure.report import invariants  # noqa: E402
from pdfmeasure.roles import Rule, extract_roles, load_rules, page_side  # noqa: E402
from pdfmeasure.shapes import PageInfo, Shape  # noqa: E402
from pdfmeasure.signatures import page_ranges  # noqa: E402
from pdfmeasure.textlines import text_lines  # noqa: E402

GREEN, GREY, INK = (69, 166, 101), (167, 165, 166), (35, 31, 32)


def shape(kind="curve", x0=0.0, top=0.0, x1=10.0, bottom=10.0, fill=None, stroke=None, linewidth=0.0, path=()):
    return Shape(kind=kind, page=1, x0=x0, top=top, x1=x1, bottom=bottom, fill=fill, stroke=stroke, linewidth=linewidth, path=path)


# ---- colours, shapes, lines ------------------------------------------------------------------------------------------------------------------
def test_cmyk_is_converted_the_way_a_pdf_reader_shows_it():
    assert to_hex(cmyk_to_rgb(0.75, 0.15, 0.75, 0.0)) == "#45a665"
    assert to_hex(cmyk_to_rgb(0, 0, 0, 1)) == "#231f20"
    assert cmyk_to_rgb(0, 0, 0, 0) == (255, 255, 255)
    assert to_rgb(0.5) == (128, 128, 128) and to_rgb(None) is None


def test_corner_radius_comes_from_the_first_arc_of_a_rounded_rectangle():
    rounded = shape(path=(("m", (13.5, 0.0)), ("l", (60.0, 0.0)), ("c", (66.0, 0.0), (70.0, 4.0), (73.5, 13.5))))
    assert rounded.corner_radius == 13.5
    assert shape(path=(("m", (0.0, 0.0)), ("l", (5.0, 0.0)))).corner_radius is None


def test_page_ranges_compress_runs():
    assert page_ranges({9, 10, 11, 13, 20, 21}) == "9-11,13,20-21"


def test_outlines_of_one_syllable_with_a_long_final_consonant_form_one_line():
    glyphs = [shape(x0=10, top=100, x1=14, bottom=108, fill=INK), shape(x0=15, top=100, x1=19, bottom=108, fill=INK), shape(x0=20, top=108.5, x1=24, bottom=112, fill=INK), shape(x0=10, top=140, x1=14, bottom=148, fill=INK), shape(x0=15, top=140, x1=19, bottom=148, fill=INK)]
    assert [round(line.top) for line in text_lines(PageInfo(1, 532.9, 720.0, glyphs))] == [100, 140]


# ---- roles, invariants, compare ---------------------------------------------------------------------------------------------------------------
RULES = [
    Rule("tab", kind="curve", fill="#45a665", ranges={"top": (None, 30), "height": (30, None)}),
    Rule("card", kind="curve", stroke="#a7a5a6", ranges={"linewidth": (1.15, 1.25), "height": (400, None)}),
    Rule("rule", kind="line", stroke="#231f20", ranges={"linewidth": (0.28, 0.32)}),
    Rule("left-only", kind="rect", sides=("left",)),
]


def page(number=9, card_top=128.27):
    return PageInfo(
        number,
        532.913,
        720.0,
        [
            shape(x0=-19.8, top=22.7, x1=164.4, bottom=62.4, fill=GREEN),
            shape(x0=48.5, top=card_top, x1=475.6, bottom=card_top + 527.1, stroke=GREY, linewidth=1.2),
            shape(kind="line", x0=100, top=222, x1=190, bottom=222, stroke=INK, linewidth=0.3),
            shape(kind="rect", x0=0, top=0, x1=10, bottom=10, fill=INK),
        ],
    )


def test_roles_are_recognised_by_look_and_sides_follow_the_page_parity():
    found = extract_roles(page(9), RULES)
    assert set(found) == {"tab", "card", "rule", "left-only"}
    assert "left-only" not in extract_roles(page(10), RULES)
    assert page_side(9) == "left" and page_side(10) == "right" and page_side(9, "right") == "right"


def test_a_colour_outside_the_tolerance_does_not_match():
    other = PageInfo(9, 532.913, 720.0, [shape(x0=48.5, top=128.3, x1=475.6, bottom=655.4, stroke=(200, 0, 0), linewidth=1.2)])
    assert "card" not in extract_roles(other, RULES)


def test_rules_load_from_json_and_ranges_may_be_open(tmp_path):
    path = tmp_path / "roles.json"
    path.write_text(json.dumps([{"role": "tall", "kind": "curve", "height": [400, None], "stroke": "any"}]))
    assert load_rules(str(path))[0].ranges["height"] == (400, None)


def test_invariants_report_spread_per_side():
    pages = [page(9, 128.27), page(11, 128.27), page(13, 128.9)]
    rows = invariants(pages, RULES, [{"name": "card top", "role": "card", "field": "top"}, {"name": "card x0 right", "role": "card", "field": "x0", "sides": "right"}])
    assert rows[0]["count"] == 3 and rows[0]["spread"] == 0.63 and len(rows) == 1


def dom_from(elements, scale=1.5):
    dom = Dom.__new__(Dom)
    dom.elements, dom.dpr, dom.scale = elements, 4.0, scale
    return dom


def test_compare_runs_pdf_and_dom_checks_in_points():
    dom = dom_from([{"role": "card", "x": 48.5 * 1.5, "y": 128.27 * 1.5, "w": 427.1 * 1.5, "h": 527.1 * 1.5, "style": {"background": "rgb(69, 166, 101)"}, "frame": {"strokeWidth": 0.46 * 1.5}}])
    checks = [
        {"name": "card top", "pdf": {"role": "card", "field": "top"}, "dom": {"id": "card", "field": "y"}},
        {"name": "card width", "pdf": {"role": "card", "field": "width"}, "dom": {"id": "card", "field": "w"}, "tolerance": 0.1},
        {"name": "colour", "expect": "#45a665", "dom": {"id": "card", "path": "style.background", "unit": "colour"}, "tolerance": 0},
        {"name": "stroke", "expect": 0.46, "dom": {"id": "card", "path": "frame.strokeWidth", "unit": "px"}, "tolerance": 0.03},
    ]
    assert all(metric.ok for metric in run_checks(checks, page(9), RULES, dom))
    off = run_checks([{"name": "card top", "pdf": {"role": "card", "field": "top"}, "dom": {"id": "card", "field": "bottom"}}], page(9), RULES, dom)
    assert not off[0].ok


def test_metric_tolerance_for_numbers_and_colours():
    assert Metric("x", 10.0, 10.4, 0.5).ok and not Metric("x", 10.0, 11.0, 0.5).ok
    assert Metric("c", "#45a665", "#45a665", 0).ok and not Metric("c", "#45a665", "#000000", 0).ok


# ---- zoom -----------------------------------------------------------------------------------------------------------------------------------
def canvas(height=240, width=360):
    return np.full((height, width, 3), 255, dtype=int)


def draw(image, x0, y0, x1, y1, colour):
    image[y0:y1, x0:x1] = colour
    return image


def test_register_finds_the_shift_that_puts_the_rebuilt_mask_on_the_pdf_mask():
    pdf = np.zeros((120, 180), dtype=bool)
    pdf[40:60, 50:130] = True
    lab = np.zeros_like(pdf)
    lab[46:66, 44:124] = True
    assert zoom.register(pdf, lab) == (6, -6)
    assert zoom.overlap(pdf, zoom.shifted(lab, 6, -6)) == 1.0


def test_an_identical_part_matches_and_a_shifted_part_is_reported():
    part = zoom.Part("frame", (0, 0, 30, 20), "align", "#45a665", 0.3)
    pdf = draw(canvas(), 60, 60, 300, 72, GREEN)
    assert zoom.compare_part(part, pdf, pdf.copy()).problems == []
    off = zoom.compare_part(part, pdf, draw(canvas(), 60, 66, 300, 78, GREEN))
    assert off.values["shift y (pt)"] == -0.5 and any("shifted" in problem for problem in off.problems)


def test_extent_ink_and_line_methods():
    pdf = draw(canvas(), 24, 48, 200, 120, INK)
    lab = draw(canvas(), 24, 72, 200, 150, INK)
    assert any("ink top off" in problem for problem in zoom.compare_part(zoom.Part("t", (0, 0, 30, 20), "ink", "ink"), pdf, lab).problems)
    assert any("top edge off" in problem for problem in zoom.compare_part(zoom.Part("e", (0, 0, 30, 20), "extent", "ink", 0.4), pdf, lab).problems)
    thin = draw(canvas(), 12, 120, 340, 124, INK)
    thick = draw(canvas(), 12, 130, 340, 140, INK)
    problems = zoom.compare_part(zoom.Part("r", (0, 0, 30, 20), "line", "ink", 0.3, 0.2), thin, thick).problems
    assert "thickness differs" in problems and "centre height differs" in problems


def test_a_part_with_none_of_its_colour_is_reported_not_crashed():
    assert zoom.compare_part(zoom.Part("f", (0, 0, 30, 20), "align", "#45a665"), canvas(), canvas()).problems == ["a side has none of the part's colour in the region"]


def test_parts_load_from_json_and_a_bad_box_is_refused(tmp_path):
    path = tmp_path / "parts.json"
    path.write_text(json.dumps([{"name": "a", "box": [10, 20, 30, 40], "method": "align", "colour": "#45a665"}]))
    assert zoom.load_parts(str(path))[0].box == (10, 20, 30, 40)
    path.write_text(json.dumps([{"name": "a", "box": [10, 20, 0, 40], "method": "align"}]))
    with pytest.raises(SystemExit):
        zoom.load_parts(str(path))


def test_crop_lab_cuts_by_array_index_at_the_zoom():
    sheet = np.arange(1200 * 1200 * 3).reshape(1200, 1200, 3)
    crop = zoom.crop_lab(sheet, zoom.Part("x", (10, 20, 4, 2), "align", "any"))
    assert crop.shape == (24, 48, 3) and (crop[0, 0] == sheet[240, 120]).all()


# ---- text metrics ---------------------------------------------------------------------------------------------------------------------------
def test_bands_words_and_pitch():
    mask = np.zeros((600, 300), dtype=bool)
    mask[60:180, 20:200] = True
    mask[360:480, 20:200] = True
    assert textmetrics.bands(mask) == [(5.0, 15.0), (30.0, 40.0)]
    row = np.zeros((120, 600), dtype=bool)
    row[:, 12:100] = True
    row[:, 124:200] = True
    row[:, 300:400] = True
    assert [(round(a, 2), round(b, 2)) for a, b in textmetrics.words(row, 3.0)] == [(1.0, 16.67), (25.0, 33.33)]
    pitch = 10.08
    columns = 70 * textmetrics.ZOOM
    profile = np.zeros(columns, dtype=bool)
    for index in range(6):
        start = int(round(index * pitch * textmetrics.ZOOM))
        profile[start : start + int(7.5 * textmetrics.ZOOM)] = True
    block = np.zeros((4 * 120, columns), dtype=bool)
    for line in range(4):
        block[line * 120 + 10 : line * 120 + 110, :] = profile
    estimate = textmetrics.pitch(block)
    assert estimate is not None and abs(estimate["pitch"] - pitch) < 0.05


# ---- the verifier must fail closed -----------------------------------------------------------------------------------------------------------
def test_a_different_shape_in_the_same_place_fails_the_overlap_gate():
    part = zoom.Part("bar", (0, 0, 30, 20), "align", "#45a665", 0.5)
    pdf = draw(canvas(), 60, 60, 300, 72, GREEN)
    lab = draw(canvas(), 60, 60, 300, 62, GREEN)  # same top-left, a sixth of the height
    assert any("shapes differ" in problem for problem in zoom.compare_part(part, pdf, lab).problems)


def test_unknown_method_and_empty_lists_are_refused(tmp_path):
    path = tmp_path / "parts.json"
    path.write_text(json.dumps([{"name": "a", "box": [1, 1, 10, 10], "method": "alingn"}]))
    with pytest.raises(SystemExit):
        zoom.load_parts(str(path))
    path.write_text("[]")
    with pytest.raises(SystemExit):
        zoom.load_parts(str(path))
    with pytest.raises(SystemExit):
        run_checks([], page(9), RULES, dom_from([]))


@pytest.mark.parametrize("zoom_px", [8, 12, 16])
def test_zoom_is_a_parameter(zoom_px):
    zoom.set_zoom(zoom_px)
    try:
        sheet = np.arange(40 * zoom_px * 40 * zoom_px * 3).reshape(40 * zoom_px, 40 * zoom_px, 3)
        crop = zoom.crop_lab(sheet, zoom.Part("x", (2, 3, 4, 2), "align", "any"))
        assert crop.shape == (2 * zoom_px, 4 * zoom_px, 3) and (crop[0, 0] == sheet[3 * zoom_px, 2 * zoom_px]).all()
        pdf = np.zeros((10 * zoom_px, 10 * zoom_px), dtype=bool)
        pdf[3 * zoom_px : 5 * zoom_px, 2 * zoom_px : 8 * zoom_px] = True
        lab = np.zeros_like(pdf)
        lab[4 * zoom_px : 6 * zoom_px, 2 * zoom_px : 8 * zoom_px] = True
        assert zoom.register(pdf, lab) == (0, -zoom_px)
    finally:
        zoom.set_zoom(12)


def test_a_colour_that_passes_the_mask_but_is_visibly_other_fails_the_colour_gate():
    part = zoom.Part("bar", (0, 0, 30, 20), "align", "#45a665", 0.5)
    pdf = draw(canvas(), 60, 60, 300, 72, GREEN)
    near = draw(canvas(), 60, 60, 300, 72, (69 + 24, 166, 101 + 12))  # inside the mask tolerance, 24 off in one channel
    assert zoom.compare_part(part, pdf, pdf.copy()).problems == []
    assert any("colour differs" in problem for problem in zoom.compare_part(part, pdf, near).problems)


def test_a_metric_delta_is_not_rounded_before_the_tolerance_is_applied():
    assert not Metric("x", 10.0, 10.034, 0.03).ok and Metric("x", 10.0, 10.03, 0.03).ok


def test_run_checks_compares_unrounded_values():
    dom = dom_from([{"role": "card", "x": 0.0, "y": 128.27 * 1.5 + 0.034 * 1.5, "w": 1.0, "h": 1.0}])
    check = [{"name": "top", "pdf": {"role": "card", "field": "top"}, "dom": {"id": "card", "field": "y"}, "tolerance": 0.03}]
    assert not run_checks(check, page(9), RULES, dom)[0].ok


def test_skip_rules_of_verify():
    from pdfmeasure.cli import validate_layers

    full = {"pdf_page": 9, "checks": "c.json", "parts": "p.json"}
    assert validate_layers({**full, "skip": {"text_layout": "fixture text differs from the printed text"}}) == {"text_layout": "fixture text differs from the printed text"}
    assert validate_layers({**full, "text_layout": {}}) == {}
    for bad in (
        {"pdf_page": 9, "skip": {"checks": "x", "parts": "y", "text_layout": "z"}},  # nothing left to verify
        {**full, "text_layout": {}, "skip": {"parts": " "}},  # empty reason
        {**full, "text_layout": {}, "skip": {"extras": "y"}},  # unknown layer
        full,  # text layout silently omitted
        {"pdf_page": 9, "checks": "c.json", "text_layout": {}},  # parts silently omitted
        {**full, "text_layout": {}, "skip": {"parts": "x"}},  # has and skips
    ):
        with pytest.raises(SystemExit):
            validate_layers(bad)
