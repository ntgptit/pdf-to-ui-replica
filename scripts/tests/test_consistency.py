"""Kit consistency: one primitive renders the same on every page; drift in height, text position or part position is an error."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmeasure import consistency  # noqa: E402


def item(kit, page, height=26.0, text_cy=0.0, parts=None, variant=""):
    return {"kit": kit, "variant": variant, "page": page, "width": 60, "height": height, "fontSize": 14, "text": {"cx": 0.0, "cy": text_cy, "height": 14}, "parts": parts or {}}


def arrow(page, lead_cy):
    return item("answer-line", page, height=28, text_cy=lead_cy - 14, variant="arrow", parts={"lead": {"cx": 5, "cy": lead_cy, "width": 10, "height": 16}, "rule": {"cx": 200, "cy": 27.5, "width": 380, "height": 0.5}})


def test_the_same_primitive_everywhere_passes():
    raw = {"width": 1280, "view": "sheet", "items": [item("example-label", p) for p in ("9", "10", "11")] + [arrow(p, 14.0) for p in ("9", "10")]}
    result = consistency.evaluate(raw)
    assert result["verdict"] == "PASS" and {s["kit"] for s in result["summary"]} == {"example-label", "answer-line (arrow)"}


def test_label_text_drift_and_arrow_on_the_rule_are_caught_with_their_pages():
    raw = {"width": 1280, "view": "sheet", "items": [item("example-label", "9"), item("example-label", "10", text_cy=2.5), arrow("9", 14.0), arrow("11", 20.0)]}
    result = consistency.evaluate(raw)
    texts = [p["text"] for p in result["problems"]]
    assert result["verdict"] == "ERROR"
    assert any("example-label: text centre y varies by 2.50 px" in t and "page 10" in t for t in texts)
    assert any("answer-line (arrow): lead centre y varies by 6.00 px" in t and "page 11" in t for t in texts)


def test_a_part_present_on_some_pages_only_is_a_drift_and_variants_are_separate():
    raw = {"width": 1280, "view": "sheet", "items": [arrow("9", 14.0), item("answer-line", "10", variant="arrow", parts={"rule": {"cx": 200, "cy": 27.5, "width": 380, "height": 0.5}}), item("answer-line", "12", height=40, variant="speaker")]}
    texts = [p["text"] for p in consistency.evaluate(raw)["problems"]]
    assert any("lead centre y exists on some instances only (missing on page(s) 10)" in t for t in texts)
    assert not any("speaker" in t for t in texts)  # another variant is not compared with the arrow one


def test_no_primitive_is_an_error_and_tolerance_is_configurable():
    assert consistency.evaluate({"items": []})["verdict"] == "ERROR"
    raw = {"items": [item("example-label", "9"), item("example-label", "10", text_cy=1.5)]}
    assert consistency.evaluate(raw)["verdict"] == "ERROR" and consistency.evaluate(raw, tolerance=2)["verdict"] == "PASS"
