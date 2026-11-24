"""Page-wide text layout check: left edges / indents, tops, bottoms, line pitch, missing and extra lines."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmeasure import textlayout as tl  # noqa: E402

Z = 4
BASE = [(20, 20, 120, 9), (20, 40, 150, 9), (30, 60, 130, 9), (20, 80, 100, 9)]  # x, top, width, height in points: a paragraph with an indented line


def page(lines, extra=()):
    image = np.full((200 * Z, 300 * Z, 3), 255, dtype=int)
    for x, top, w, h in [*lines, *extra]:
        image[int(round(top * Z)) : int(round((top + h) * Z)), int(round(x * Z)) : int(round((x + w) * Z))] = (30, 30, 30)
    return image


def run(react_lines, **cfg):
    return tl.compare(tl.segments(page(BASE), Z), tl.segments(page(react_lines), Z), cfg)


def test_identical_pages_pass_with_every_line_matched():
    result = run(BASE)
    assert result["ok"] and result["matched"] == 4 and result["worst"]["left"] == 0 and not result["problems"]


def test_a_left_indent_off_by_one_point_fails():
    moved = [BASE[0], BASE[1], (31.0, 60, 130, 9), BASE[3]]
    result = run(moved)
    assert not result["ok"] and any("left edge off by +1.00" in problem for problem in result["problems"])


def test_a_hanging_indent_that_is_lost_on_one_line_fails_even_when_the_first_line_is_right():
    moved = [BASE[0], BASE[1], (20, 60, 140, 9), BASE[3]]  # the indented third line starts at the margin
    assert any("left edge" in problem for problem in run(moved)["problems"])


def test_line_spacing_that_drifts_is_caught_by_the_pitch_and_by_the_position():
    drift = [BASE[0], (20, 40.75, 150, 9), (30, 60.75, 130, 9), (20, 80.75, 100, 9)]  # the second line is 0.75 pt low, the rest follow it
    problems = run(drift)["problems"]
    assert any("pitch to the line above" in problem for problem in problems) and any("top off by +0.75" in problem for problem in problems)
    only_pitch = [BASE[0], BASE[1], (30, 60.5, 130, 9), (20, 80.5, 100, 9)]  # +0.5 pt from the third line on: inside the 0.6 position tolerance, but the pitch (20.5 vs 20) is not
    result = run(only_pitch, tolerance_vertical=0.6, tolerance_pitch=0.3)
    assert any("pitch" in problem for problem in result["problems"])


def test_a_missing_and_an_extra_line_are_listed():
    missing = run([BASE[0], BASE[1], BASE[3]])
    assert any("only in the PDF at (30.0, 60.0)" in problem for problem in missing["problems"]) and not missing["ok"]
    extra = tl.compare(tl.segments(page(BASE), Z), tl.segments(page(BASE, [(20, 120, 80, 9)]), Z))
    assert any("only in the rebuilt page" in problem for problem in extra["problems"])


def test_tolerances_are_configurable_and_regions_limit_the_check():
    moved = [BASE[0], BASE[1], (30.4, 60, 130, 9), BASE[3]]
    assert run(moved)["ok"]  # 0.4 pt is inside the default 0.5
    assert not run(moved, tolerance_left=0.2)["ok"]
    bad = [BASE[0], (25, 40, 150, 9), BASE[2], BASE[3]]
    assert not run(bad)["ok"]
    assert run(bad, regions=[[0, 55, 300, 40]])["ok"]  # the wrong line is outside the region


def test_a_page_without_text_is_not_a_pass():
    empty = np.full((200 * Z, 300 * Z, 3), 255, dtype=int)
    result = tl.compare(tl.segments(empty, Z), tl.segments(empty, Z))
    assert result["empty"] and not result["ok"] and "nothing was verified" in tl.to_markdown("x", result)


def test_frames_and_thin_rules_are_not_text_lines():
    image = page(BASE)
    image[100 * Z : 101 * Z, 10 * Z : 280 * Z] = (30, 30, 30)  # a 1 pt rule
    image[10 * Z : 190 * Z, 5 * Z : 6 * Z] = (30, 30, 30)  # a tall frame edge
    assert len(tl.segments(image, Z)) == 4


def test_two_columns_stay_separate_lines():
    image = page([(20, 20, 60, 9), (150, 20, 60, 9), (20, 40, 60, 9), (150, 40, 60, 9)])
    assert len(tl.segments(image, Z)) == 4
