"""Knowhow register: the shipped entries are valid, detectors catch their pattern and nothing else, entries are added once and recorded when seen,
defects link to entries, the QA report lists candidates, and the harness refuses ERROR findings."""
import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from module_fixture import make_module  # noqa: E402
from pdfmeasure import knowhow, qa_cli, qa_run  # noqa: E402
from pdfmeasure.issues import IssueStore  # noqa: E402


def test_the_shipped_register_is_valid_and_rendered():
    data = knowhow.load()
    ids = [entry["id"] for entry in data["entries"]]
    assert ids == [f"KH-{n:03d}" for n in range(1, len(ids) + 1)] and len(ids) >= 10
    assert all(knowhow.validate(entry) == [] for entry in data["entries"])
    assert knowhow.render(data) == knowhow.RENDERED.read_text(encoding="utf-8")  # the md is regenerated with every change


@pytest.mark.parametrize("line, hit", [
    ("[data-book=a][data-view=sheet] .wb-rule { border-bottom: calc(var(--wb-pt) * 0.3) solid var(--wb-ink); }", True),
    ("[data-book=a][data-view=sheet] .wb-box { border: 0.5px solid red; }", True),
    ("[data-book=a][data-view=sheet] .wb-box { outline-width: .4px; }", True),
    ("[data-book=a][data-view=sheet] .wb-box { border: 1px solid red; }", False),
    ("[data-book=a][data-view=sheet] .wb-rule::before { height: max(calc(var(--wb-pt) * 0.3), 0.5px); }", True),  # a thin box is painted 1 px too (measured)
    ("[data-book=a][data-view=sheet] .wb-gap { height: 12.5px; }", False),
    ("[data-book=a][data-view=sheet] .wb-box { border: 10.5px solid red; }", False),
])
def test_the_hairline_detector(tmp_path, line, hit):
    (tmp_path / "rule.css").write_text(line + "\n")
    found = [f for f in knowhow.scan(tmp_path) if f["id"] == "KH-001"]
    assert bool(found) == hit
    if hit:
        assert found[0]["severity"] in ("ERROR", "WARNING") and found[0]["line"] == 1


def test_a_default_1px_line_in_a_book_is_flagged(tmp_path):
    book = tmp_path / "books" / "a" / "parts" / "rule"
    book.mkdir(parents=True)
    (book / "rule.css").write_text("[data-book=a][data-view=sheet] .wb-rule { border-bottom: 1px solid var(--wb-ink); }\n")
    (book / "rule.tsx").write_text('<hr className="border-b border-ink" />\n<div className="h-px scale-y-50 origin-top bg-current" />\n')
    found = {(f["file"].split("/")[-1], f["line"], f["severity"]) for f in knowhow.scan(tmp_path) if f["id"] == "KH-001"}
    assert ("rule.css", 1, "WARNING") in found and ("rule.tsx", 1, "WARNING") in found and not any(line == 2 for _, line, _ in found)
    core = tmp_path / "core" / "reading" / "card"
    core.mkdir(parents=True)
    (core / "card.tsx").write_text('<div className="border rounded-lg" />\n')  # the reading view's 1px borders are app design, not printed lines
    assert not any(f["file"].startswith("core/") for f in knowhow.scan(tmp_path))


def test_tsx_detectors(tmp_path):
    (tmp_path / "a.tsx").write_text('<div className="border-b-[0.5px]" />\n<svg><line strokeWidth={0.3} /></svg>\n<Input className="text-sm" />\n')
    found = {(f["id"], f["line"]) for f in knowhow.scan(tmp_path)}
    assert ("KH-001", 1) in found and not any(line == 2 for _, line in found) and ("KH-006", 3) in found
    (tmp_path / "app.css").write_text("@custom-variant print (&:where([data-view=sheet] *));\n")
    assert any(f["id"] == "KH-005" for f in knowhow.scan(tmp_path))


def test_add_seen_search(tmp_path):
    path = tmp_path / "knowhow.json"
    data = {"entries": []}
    entry = {"title": "Thing breaks", "tags": ["css"], "symptom": "s", "cause": "c", "fix": "f", "check": "k"}
    assert knowhow.add(data, entry)["id"] == "KH-001"
    with pytest.raises(knowhow.KnowhowError, match="already covers"):
        knowhow.add(data, {**entry, "title": "thing  BREAKS"})
    with pytest.raises(knowhow.KnowhowError, match="unknown tags"):
        knowhow.add(data, {**entry, "title": "x", "tags": ["nope"]})
    with pytest.raises(knowhow.KnowhowError, match="does not compile"):
        knowhow.add(data, {**entry, "title": "y", "detect": [{"glob": "*.css", "pattern": "(", "severity": "ERROR", "message": "m"}]})
    knowhow.seen(data, "KH-001", "vitamin-1", "answer rules")
    knowhow.save(data, path)
    assert json.loads(path.read_text())["entries"][0]["seen"][0]["build"] == "vitamin-1" and path.with_suffix(".md").exists()
    assert [e["id"] for e in knowhow.search(knowhow.load(), "hairline 1 px")] == ["KH-001"]
    assert knowhow.search(knowhow.load(), "zoom", ["reading"])[0]["id"] == "KH-006"


def test_a_defect_links_to_an_existing_entry_and_the_report_lists_candidates(tmp_path):
    out = tmp_path / "out"
    args = argparse.Namespace(output=str(out), action="add", run="run-0", page=9, description="answer rule too thick", region="10,10,100,2", type="stroke", severity="P1",
                              object=None, evidence=None, cause="border under 1px", fix=None, knowhow="KH-999")
    assert qa_cli.command_issue(args) == 2  # unknown knowhow id refused
    args.knowhow = "KH-001"
    assert qa_cli.command_issue(args) == 0
    store = IssueStore(out / "issues.json")
    assert store.issues[0]["knowhow"] == "KH-001"
    other = store.add(run="run-0", page=9, description="tab label too low", region=[0, 0, 10, 10], type="layout", severity="P2", cause="baseline offset")
    store.set_status(other["id"], "FIXING", run="r1", note="fix")
    store.set_status(other["id"], "NEEDS_VERIFY", run="r1", note="fixed")
    store.set_status(other["id"], "VERIFIED", run="r1", note="ok", evidence=["after.png"])
    store.save()
    report = qa_run.write_report(out, store, run="r1", baseline_run="run-0", pages=[9]).read_text()
    assert "ISS-001 matched KH-001" in report and "ISS-002 (layout): tab label too low" in report


def test_the_harness_refuses_error_findings(tmp_path):
    from pdfmeasure.ebook_state import EbookState

    module = make_module(tmp_path)
    state = EbookState(tmp_path / "o")
    state.init(kind="web-fixed", pages=[9], pilot=[9])
    state.set_module(str(module), "vitamin-1")
    assert not any(p.startswith("knowhow") for p in state._structure_problems(tmp_path))
    css = module / "books/vitamin-1/kit/answer-line/answer-line.css"
    css.write_text(css.read_text().replace("display: flex;", "display: flex; border-bottom: calc(var(--wb-pt) * 0.3) solid;"))
    assert any(p.startswith("knowhow KH-001") for p in state._structure_problems(tmp_path))


def test_an_entry_is_corrected_with_evidence(tmp_path):
    data = {"entries": []}
    knowhow.add(data, {"title": "T", "tags": ["css"], "symptom": "s", "cause": "c", "fix": "old fix", "check": "k"})
    with pytest.raises(knowhow.KnowhowError, match="--reason"):
        knowhow.update(data, "KH-001", {"fix": "new"}, "")
    entry = knowhow.update(data, "KH-001", {"fix": "new fix"}, "measured in Chromium")
    assert entry["fix"] == "new fix" and entry["history"][0]["fields"] == ["fix"]
    assert "Corrected" in knowhow.render(data)
    shipped = knowhow.get(knowhow.load(), "KH-001")
    assert "SVG stroke" in shipped["fix"] and "scale: 1 0.5" in shipped["fix"] and "never round" in shipped["fix"] and len(shipped["history"]) >= 2  # measured corrections kept
