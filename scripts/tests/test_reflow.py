"""Reading view on phones: the judgement of the browser measurements (check-reflow.cjs), without a browser."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmeasure import reflow  # noqa: E402


def width(**overrides):
    data = {"innerWidth": 360, "scrollWidth": 360, "viewport": "width=device-width, initial-scale=1", "blocks": ["title", "ex-1", "art"],
            "texts": [{"block": "title", "role": "heading", "px": 24, "width": 300, "text": "Title"}, {"block": "ex-1", "role": "body", "px": 16, "width": 320, "text": "Read"},
                      {"block": "art", "role": "caption", "px": 14, "width": 100, "text": "child"}],
            "targets": [{"tag": "button", "label": "Play", "width": 44, "height": 44}], "media": [{"tag": "img", "block": "art", "left": 16, "right": 200, "width": 184}]}
    data.update(overrides)
    return data


def run(fixed_blocks=("title", "ex-1", "art"), fixed_px=5.4, **overrides):
    raw = {"widths": {"360": width(**overrides)}, "fixed": {"width": 360, "blocks": list(fixed_blocks), "texts": [{"role": "body", "px": fixed_px, "width": 100, "text": "x"}]}}
    return reflow.evaluate(raw)


def texts_of(result, level):
    return [p["text"] for p in result["problems"] if p["level"] == level]


def test_a_good_reading_view_passes_and_the_unreadable_print_view_sends_phones_to_it():
    result = run()
    assert result["verdict"] == "PASS" and result["phone_default"] == "reading" and result["fixed_body_px_at_phone"] == 5.4
    assert run(fixed_px=13)["phone_default"] == "either"


def test_overflow_zoom_lock_and_offscreen_pictures_are_errors():
    assert any("horizontal scroll" in t for t in texts_of(run(scrollWidth=500), "ERROR"))
    assert any("zoom is disabled" in t for t in texts_of(run(viewport="width=device-width, user-scalable=no"), "ERROR"))
    assert any("zoom is disabled" in t for t in texts_of(run(viewport="width=device-width, maximum-scale=1"), "ERROR"))
    assert any("runs off the screen" in t for t in texts_of(run(media=[{"tag": "img", "block": "art", "left": 0, "right": 420, "width": 420}]), "ERROR"))


def test_text_sizes_follow_their_role():
    small_body = run(texts=[{"block": "ex-1", "role": "body", "px": 14, "width": 200, "text": "Read"}])
    assert any("body text 14 px (min 16)" in t for t in texts_of(small_body, "ERROR"))
    caption_ok = run(texts=[{"block": "art", "role": "caption", "px": 14, "width": 100, "text": "child"}])
    assert caption_ok["verdict"] == "PASS"
    assert any("caption text 12 px (min 14)" in t for t in texts_of(run(texts=[{"block": "art", "role": "caption", "px": 12, "width": 100, "text": "c"}]), "ERROR"))
    assert run(texts=[{"block": "art", "role": "decorative", "px": 8, "width": 30, "text": "★"}])["verdict"] == "PASS"
    long_line = run(texts=[{"block": "ex-1", "role": "body", "px": 16, "width": 720, "text": "Read"}])
    assert texts_of(long_line, "ERROR") == [] and any("45 em" in t for t in texts_of(long_line, "WARNING"))


def test_targets_have_a_hard_floor_and_a_comfortable_size():
    assert any("min 24" in t for t in texts_of(run(targets=[{"tag": "button", "label": "▶", "width": 27, "height": 18}]), "ERROR"))
    medium = run(targets=[{"tag": "button", "label": "▶", "width": 32, "height": 32}])
    assert texts_of(medium, "ERROR") == [] and any("comfortable 44" in t for t in texts_of(medium, "WARNING"))
    assert reflow.evaluate({"widths": {"360": width(targets=[{"tag": "a", "label": "x", "width": 32, "height": 32}])}}, {"target_warn_px": 32})["verdict"] == "PASS"  # a project's own rule


def test_every_print_block_is_present_in_reading_order():
    missing = run(blocks=["title", "ex-1"])
    assert any("missing in the reading view: art" in t for t in texts_of(missing, "ERROR"))
    swapped = run(blocks=["ex-1", "title", "art"])
    assert any("reading order differs" in t and "'ex-1'" in t for t in texts_of(swapped, "ERROR"))
    extra = run(blocks=["title", "ex-1", "art", "glossary"])
    assert texts_of(extra, "ERROR") == [] and any("only in the reading view: glossary" in t for t in texts_of(extra, "WARNING"))


def test_the_report_groups_one_problem_seen_at_several_widths():
    raw = {"widths": {str(w): width(innerWidth=w, scrollWidth=500) for w in (320, 360, 390)}}
    text = reflow.to_markdown(18, reflow.evaluate(raw))
    assert "## ERROR (3)" in text and "- 320, 360, 390 px: horizontal scroll" not in text  # widths differ in the text (screen width named)
    raw = {"widths": {str(w): width(innerWidth=w, viewport="user-scalable=no") for w in (320, 360)}}
    assert "- 320, 360 px: zoom is disabled" in reflow.to_markdown(18, reflow.evaluate(raw))


def test_the_page_opens_reading_on_phones_and_the_sheet_on_desktops():
    good = {"widths": {"360": width()}, "auto": {"360": {"view": "reading", "innerWidth": 360, "scrollWidth": 360}, "1280": {"view": "sheet", "innerWidth": 1280, "scrollWidth": 1280}, "1920": {"view": "sheet", "innerWidth": 1920, "scrollWidth": 1920}}}
    result = reflow.evaluate(good)
    assert result["verdict"] == "PASS" and result["auto_checked"]
    bad = {"widths": {"360": width()}, "auto": {"360": {"view": "sheet", "innerWidth": 360, "scrollWidth": 360}, "1920": {"view": "reading", "innerWidth": 1920, "scrollWidth": 2100}}}
    errors = texts_of(reflow.evaluate(bad), "ERROR")
    assert any("opens the sheet view at 360 px, expected reading" in t for t in errors)
    assert any("opens the reading view at 1920 px, expected sheet" in t for t in errors)
    assert any("horizontal scroll at 1920 px" in t for t in errors)
    assert not reflow.evaluate({"widths": {"360": width()}})["auto_checked"]
