"""Ebook harness: page statuses move only through checks, gates are evaluated from files, failed fixes leave the agent's loop, the Stop hook blocks."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmeasure import reflow, tiles, typography  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from module_fixture import make_module  # noqa: E402
from pdfmeasure.ebook_state import EbookState, StateError, inventory_rows  # noqa: E402
from pdfmeasure.issues import IssueError, IssueStore  # noqa: E402

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "ebook-gate-stop.py"

INVENTORY = """# inventory
INVENTORY_COMPLETE

| ID | Page | Object | Region (pt) | Approach | Status |
|---|---|---|---|---|---|
| OBJ-001 | 9 | frame | 0,0,10,10 | SVG | VERIFIED |
| OBJ-002 | 10 | bubble | 0,0,10,10 | SVG | VERIFIED |
| OBJ-003 | 11 | sticker | 0,0,10,10 | SVG | TODO |
"""


def make_tiles(output: Path, page: int, mode: str, zoom: int = 6, ids: tuple[str, ...] = ()) -> None:
    """A tiles manifest as `tiles` writes it (the picture files themselves are not needed by the checks)."""
    folder = tiles.tiles_dir(output, page, mode)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"mode": mode, "page": page, "zoom": zoom, "page_pt": [595, 842], "tile_pt": 250, "overlap_pt": 6, "created": time.time(), "blank_count": 0, "tiles": [{"id": tile_id, "box_pt": [0, 0, 10, 10], "blank": False, "file": f"{tile_id}.png"} for tile_id in ids]}
    (folder / tiles.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")


def make_stack(root: Path, tailwind: str = "^4.3.4") -> Path:
    """A minimal app of the supported stack: components.json next to a package.json with react and tailwindcss."""
    app = root / "apps" / "web"
    app.mkdir(parents=True, exist_ok=True)
    (app / "package.json").write_text(json.dumps({"dependencies": {"react": "^19.0.0"}, "devDependencies": {"tailwindcss": tailwind}}), encoding="utf-8")
    (app / "components.json").write_text(json.dumps({"style": "new-york", "tailwind": {"css": "src/index.css"}}), encoding="utf-8")
    return root


def make_spec(output: Path, page: int) -> None:
    folder = output / "pages" / f"page-{page:03d}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / typography.SPEC_FILE).write_text(json.dumps({"zoom": 8, "styles": [], "fonts": []}), encoding="utf-8")


def make_typography(output: Path, page: int, verdict: str = "PASS", score: float = 0.99, zoom: int = 8) -> None:
    folder = output / "pages" / f"page-{page:03d}"
    folder.mkdir(parents=True, exist_ok=True)
    result = {"zoom": zoom, "created": time.time(), "verdict": verdict, "worst": {"score": score, "style": "core 7 pt", "attribute": "weight"}, "empty": False}
    (folder / typography.RESULT_FILE).write_text(json.dumps(result), encoding="utf-8")


def make_reflow(output: Path, page: int, verdict: str = "PASS", auto: bool = True) -> None:
    folder = output / "pages" / f"page-{page:03d}"
    folder.mkdir(parents=True, exist_ok=True)
    problems = [{"level": "ERROR", "width": 360, "text": "horizontal scroll"}] if verdict == "ERROR" else []
    (folder / reflow.RESULT_FILE).write_text(json.dumps({"created": time.time(), "verdict": verdict, "problems": problems, "auto_checked": auto}), encoding="utf-8")


def make_consistency(output: Path, verdict: str = "PASS") -> None:
    problems = [{"level": "ERROR", "kit": "example-label", "text": "example-label: text centre y varies by 2.50 px"}] if verdict == "ERROR" else []
    (output / "consistency.json").write_text(json.dumps({"created": time.time(), "verdict": verdict, "problems": problems}), encoding="utf-8")


def inventory_pass(state: EbookState) -> list[str]:
    """What an agent does for gate inventory: PDF tiles for every page, a look at them, then the gate."""
    for page in state.scope["pages"]:
        make_spec(state.output, page)
        make_tiles(state.output, page, "pdf")
        time.sleep(0.01)
        state.record_view(page, "looked at every tile; found the numbered markers and dotted guides", "inventory")
    return state.run_gate("inventory", inventory=state.inventory)


def scan(output: Path, page: int, failing: list[str] | None = None, verified: bool = True) -> Path:
    folder = output / "pages" / f"page-{page:03d}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "overlay-v0.png").write_bytes(b"x")
    note = "- verify ran (exit 0); every entry within tolerance" if verified and not failing else "- none"
    lines = [f"# Scan: page {page}, v0", "", "- status: **needs_review**; different pixels: 0.01", "", "## Failing geometry / zoom / text-layout entries (same run)", ""]
    lines += [f"- {item}" for item in failing] if failing else [note]
    lines += ["", "Text and artwork regions usually differ by design."]
    path = folder / "scan-v0.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def state(tmp_path):
    out = tmp_path / "out"
    (out).mkdir()
    inventory = tmp_path / "object-inventory.md"
    inventory.write_text(INVENTORY, encoding="utf-8")
    s = EbookState(out)
    s.init(kind="web-fixed", pages=[9, 10, 11], pilot=[9])
    assert s.run_gate("scope", root=make_stack(tmp_path)) == []
    s.set_module(str(make_module(tmp_path)), "vitamin-1")
    s.inventory = inventory
    return s


def ready(state: EbookState, page: int, **scan_kwargs):
    scan(state.output, page, **scan_kwargs)
    time.sleep(0.01)
    make_tiles(state.output, page, "pair")
    make_typography(state.output, page)
    make_reflow(state.output, page)
    make_consistency(state.output)
    time.sleep(0.01)
    state.record_view(page, "looked at the overlay, every pair tile and the crops")


def test_init_demands_a_valid_scope(tmp_path):
    with pytest.raises(StateError, match="pilot"):
        EbookState(tmp_path / "a").init(kind="web-fixed", pages=[1, 2], pilot=[])
    with pytest.raises(StateError, match="not in scope"):
        EbookState(tmp_path / "b").init(kind="web-fixed", pages=[1, 2], pilot=[7])
    with pytest.raises(StateError, match="output kind"):
        EbookState(tmp_path / "c").init(kind="pdf", pages=[1], pilot=[1])
    EbookState(tmp_path / "d").init(kind="analysis", pages=[1, 2], pilot=[])  # analysis needs no pilot


def test_no_page_starts_before_the_inventory_and_only_pilot_pages_before_the_pilot_gate(state):
    with pytest.raises(StateError, match="inventory"):
        state.set_page(9, "IN_PROGRESS", note="start")
    # page 11 has a row (TODO), so the inventory gate passes: a TODO row only blocks that page's VERIFIED, not the inventory
    assert inventory_pass(state) == []
    state.set_page(9, "IN_PROGRESS", note="pilot start")
    with pytest.raises(StateError, match="pilot"):
        state.set_page(10, "IN_PROGRESS", note="too early")


def test_verified_needs_scan_clean_verify_and_a_view_after_the_scan(state):
    inventory_pass(state)
    state.set_page(9, "IN_PROGRESS", note="start")
    with pytest.raises(StateError, match="no scan"):
        state.set_page(9, "VERIFIED", note="done")
    scan(state.output, 9, failing=["geometry: | frame | x | **off** |"])
    with pytest.raises(StateError, match="failing"):
        state.set_page(9, "VERIFIED", note="done")
    scan(state.output, 9, verified=False)
    with pytest.raises(StateError, match="no passing verify run"):
        state.set_page(9, "VERIFIED", note="done")
    scan(state.output, 9)
    with pytest.raises(StateError, match="no pair tiles"):
        state.set_page(9, "VERIFIED", note="done")
    time.sleep(0.01)
    make_tiles(state.output, 9, "pair", zoom=3)
    with pytest.raises(StateError, match="under the minimum 6"):
        state.set_page(9, "VERIFIED", note="done")
    time.sleep(0.01)
    make_tiles(state.output, 9, "pair")
    with pytest.raises(StateError, match="state view"):
        state.set_page(9, "VERIFIED", note="done")
    time.sleep(0.01)
    state.record_view(9, "looked at the page, every pair tile and the crops")
    with pytest.raises(StateError, match="no typography result"):
        state.set_page(9, "VERIFIED", note="done")
    make_typography(state.output, 9)
    make_reflow(state.output, 9)
    assert state.set_page(9, "VERIFIED", note="clean scan and look", inventory=state.inventory)["status"] == "VERIFIED"
    time.sleep(0.01)
    scan(state.output, 9)  # a newer scan makes the earlier pair tiles and look stale
    assert any("older than the latest scan" in item for item in state.page_problems(9))
    assert any("state view" in item for item in state.page_problems(9))


def test_an_open_p1_blocks_verified_and_a_limitation_cannot_cover_it(state):
    inventory_pass(state)
    state.set_page(9, "IN_PROGRESS", note="start")
    ready(state, 9)
    store = state.issue_store()
    store.add(run="r0", page=9, description="bubble tail wrong", region=[0, 0, 10, 10], type="shape", severity="P1")
    store.save()
    with pytest.raises(StateError, match="P0/P1"):
        state.set_page(9, "VERIFIED", note="done")
    with pytest.raises(StateError, match="limitation cannot cover"):
        state.set_page(9, "ACCEPTED_LIMITATION", note="meh", reason="artwork differs")


def test_inventory_rows_of_the_page_must_be_closed(state):
    inventory_pass(state)
    state.set_page(9, "IN_PROGRESS", note="start")
    ready(state, 9)
    assert state.page_problems(9, state.inventory) == []
    assert [row["id"] for row in inventory_rows(state.inventory)] == ["OBJ-001", "OBJ-002", "OBJ-003"]
    state.set_page(9, "VERIFIED", note="ok", inventory=state.inventory)
    state.run_gate("pilot", inventory=state.inventory)
    state.set_page(11, "IN_PROGRESS", note="start")
    ready(state, 11)
    with pytest.raises(StateError, match=r"OBJ-003 \(TODO\)"):
        state.set_page(11, "VERIFIED", note="done", inventory=state.inventory)


def test_pilot_gate_then_book_gate(state, tmp_path):
    inventory_pass(state)
    assert state.run_gate("pilot")  # pilot not verified yet
    state.set_page(9, "IN_PROGRESS", note="start")
    ready(state, 9)
    state.set_page(9, "VERIFIED", note="ok")
    assert state.run_gate("pilot") == []
    for page in (10, 11):
        state.set_page(page, "IN_PROGRESS", note="start")
    problems = state.run_gate("book")
    assert any("page 10 is IN_PROGRESS" in item for item in problems)
    ready(state, 10)
    state.set_page(10, "VERIFIED", note="ok")
    with pytest.raises(StateError, match="reason"):
        state.set_page(11, "ACCEPTED_LIMITATION", note="x")
    state.set_page(11, "ACCEPTED_LIMITATION", note="artwork redrawn, differs", reason="original artwork cannot be copied")
    assert state.run_gate("book") == []
    # a later change breaks a VERIFIED page: the book gate re-reads the evidence and fails
    time.sleep(0.01)
    scan(state.output, 9, failing=["zoom: | part | **off** |"])
    assert any("page 9" in item for item in state.run_gate("book"))


def test_delivery_needs_build_report_cleanup_and_no_tracked_book(state, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "book.pdf").write_bytes(b"%PDF")
    subprocess.run(["git", "add", "book.pdf"], cwd=root, check=True)
    state.data["scope"]["output_kind"] = "replica-lab"
    state.data["scope"]["pages"] = [9]
    state.data["pages"] = {"9": state.data["pages"]["9"]}
    state.data["gates"]["inventory"] = {"passed": True}
    state.data["gates"]["scope"] = {"passed": True}
    make_spec(state.output, 9)
    state.set_page(9, "IN_PROGRESS", note="start")
    ready(state, 9)
    state.set_page(9, "VERIFIED", note="ok")
    problems = state.run_gate("delivery", root=root)
    text = " | ".join(problems)
    assert "no report.md" in text and "tracked PDF: book.pdf" in text and "build not verified" in text
    (state.output / "report.md").write_text("# report\nNo unresolved P0/P1\n", encoding="utf-8")
    subprocess.run(["git", "rm", "-q", "--cached", "book.pdf"], cwd=root, check=True)
    assert state.run_gate("delivery", root=root, build_cmd="exit 3")[0].startswith("build `exit 3` failed")
    assert state.run_gate("delivery", root=root, build_cmd="true") == []


def test_failed_fixes_leave_the_agents_loop_at_the_cap(tmp_path):
    store = IssueStore(tmp_path / "issues.json", max_failed_rounds=2)
    issue = store.add(run="r0", page=9, description="tail", region=[0, 0, 10, 10], type="shape", severity="P1", cause="control points are off")
    iid = issue["id"]
    for round_number in (1, 2):
        store.set_status(iid, "FIXING", run=f"r{round_number}", note="trying")
        store.set_status(iid, "NEEDS_VERIFY", run=f"r{round_number}", note="fixed?")
        result = store.set_status(iid, "OPEN", run=f"r{round_number}", note="still wrong")
    assert result["failed_rounds"] == 2 and result["status"] == "CODEX_READY"  # cause known: hand over
    with pytest.raises(IssueError, match="did not hold"):
        store.set_status(iid, "FIXING", run="r3", note="one more try")
    assert store.set_status(iid, "FIXING", run="r3", note="new idea", reset_rounds="measured the tail base: the earlier guess was wrong")["status"] == "FIXING"
    no_cause = store.add(run="r0", page=10, description="x", region=[50, 50, 10, 10], type="layout", severity="P2")
    for _ in range(2):
        store.set_status(no_cause["id"], "FIXING", run="r", note="t")
        store.set_status(no_cause["id"], "NEEDS_VERIFY", run="r", note="f")
        store.set_status(no_cause["id"], "OPEN", run="r", note="w")
    assert store.get(no_cause["id"])["status"] == "BLOCKED"  # no cause to hand over


def run_hook(root: Path, output: Path) -> str:
    env = {**os.environ, "PDF_TO_UI_OUTPUT": str(output)}
    result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"cwd": str(root), "session_id": f"t{time.time_ns()}"}), capture_output=True, text=True, env=env, cwd=root, check=False)
    return result.stdout


def test_stop_hook_blocks_until_pages_are_settled(state, tmp_path):
    repo = Path(__file__).resolve().parents[2]
    assert run_hook(repo, tmp_path / "no-state") == ""  # no state file: the hook is silent
    inventory_pass(state)
    state.set_page(9, "IN_PROGRESS", note="start")
    state.save()
    blocked = json.loads(run_hook(repo, state.output))
    assert blocked["decision"] == "block" and "page 9 is IN_PROGRESS" in blocked["reason"]
    state.block("waiting for the owner to pick fixed or reflowable")
    state.save()
    assert run_hook(repo, state.output) == ""  # blocked on purpose: it may stop


def test_a_view_needs_one_observation_per_tile(state):
    make_tiles(state.output, 9, "pdf", ids=("r0c0", "r0c1", "r1c0"))
    with pytest.raises(StateError, match="missing or empty for 3 of 3"):
        state.record_view(9, "looked", "inventory")
    with pytest.raises(StateError, match="missing or empty for 1 of 3.*r1c0"):
        state.record_view(9, "looked", "inventory", {"r0c0": "numbered markers 1 and 2", "r0c1": "nothing small"})
    with pytest.raises(StateError, match="not in the pdf manifest"):
        state.record_view(9, "looked", "inventory", {"r0c0": "ok ok", "r0c1": "ok ok", "r1c0": "ok ok", "r9c9": "invented"})
    state.record_view(9, "looked", "inventory", {"r0c0": "numbered markers 1 and 2", "r0c1": "nothing small", "r1c0": "dotted guide, arrowhead"})
    assert state.entry(9)["inventory_tile_notes"]["r1c0"] == "dotted guide, arrowhead"
    with pytest.raises(StateError, match="no pair tiles"):
        state.record_view(9, "looked", "qa")


def test_typography_error_blocks_verified_a_warning_does_not_and_a_stale_result_is_rejected(state):
    inventory_pass(state)
    state.set_page(9, "IN_PROGRESS", note="start")
    ready(state, 9)
    make_typography(state.output, 9, "ERROR", 0.86)
    with pytest.raises(StateError, match=r"typography ERROR: weight of style core 7 pt at 86.0%"):
        state.set_page(9, "VERIFIED", note="done")
    make_typography(state.output, 9, "WARNING", 0.93)
    assert state.set_page(9, "VERIFIED", note="weight 93 % listed as P2")["status"] == "VERIFIED"
    assert any("WARNING (weight 93.0%)" in row for row in state.coverage_lines())
    time.sleep(0.01)
    scan(state.output, 9)
    assert any("older than the latest scan" in item for item in state.page_problems(9) if "typography" in item)
    make_typography(state.output, 9, zoom=6)
    assert any("under the minimum 8" in item for item in state.page_problems(9))


def test_no_page_starts_without_a_typography_spec(state):
    inventory_pass(state)
    (state.output / "pages" / "page-009" / typography.SPEC_FILE).unlink()
    with pytest.raises(StateError, match="no typography spec"):
        state.set_page(9, "IN_PROGRESS", note="start")


def test_a_page_with_undelivered_artwork_cannot_be_verified(state):
    from pdfmeasure import artwork

    inventory_pass(state)
    state.set_page(9, "IN_PROGRESS", note="start")
    ready(state, 9)
    briefs = {"set": "book", "objects": [{"id": "OBJ-001", "page": 9, "name": "frame", "box_pt": [0, 0, 10, 10], "themes": ["light"], "states": [{"name": "default", "description": "x"}]}]}
    artwork.folder(state.output).mkdir(parents=True, exist_ok=True)
    (artwork.folder(state.output) / artwork.BRIEFS).write_text(json.dumps(briefs), encoding="utf-8")
    with pytest.raises(StateError, match="artwork OBJ-001 .* not delivered"):
        state.set_page(9, "VERIFIED", note="done")
    (artwork.folder(state.output) / artwork.MAP).write_text(json.dumps({"objects": {"OBJ-001": {"files": {"default/light": "a.webp"}}}}), encoding="utf-8")
    assert state.set_page(9, "VERIFIED", note="art fitted")["status"] == "VERIFIED"


def test_a_web_page_needs_a_reading_view_that_passes(state):
    inventory_pass(state)
    state.set_page(9, "IN_PROGRESS", note="start")
    ready(state, 9)
    (state.output / "pages" / "page-009" / reflow.RESULT_FILE).unlink()
    with pytest.raises(StateError, match="no reading-view result"):
        state.set_page(9, "VERIFIED", note="done")
    make_reflow(state.output, 9, "ERROR")
    with pytest.raises(StateError, match="reading view ERROR at 360 px: horizontal scroll"):
        state.set_page(9, "VERIFIED", note="done")
    make_reflow(state.output, 9, "WARNING")
    assert state.set_page(9, "VERIFIED", note="ok")["status"] == "VERIFIED"


def test_a_replica_lab_does_not_need_a_reading_view(tmp_path):
    out = tmp_path / "lab"
    out.mkdir()
    lab = EbookState(out)
    lab.init(kind="replica-lab", pages=[9], pilot=[9])
    lab.run_gate("scope", root=make_stack(tmp_path / "repo"))
    lab.set_module(str(make_module(tmp_path / "repo")), "vitamin-1")
    lab.inventory = tmp_path / "inv.md"
    lab.inventory.write_text(INVENTORY.replace("| OBJ-002 | 10 |", "| OBJ-002 | 9 |").replace("| OBJ-003 | 11 | sticker | 0,0,10,10 | SVG | TODO |", ""), encoding="utf-8")
    assert inventory_pass(lab) == []
    lab.set_page(9, "IN_PROGRESS", note="start")
    ready(lab, 9)
    (out / "pages" / "page-009" / reflow.RESULT_FILE).unlink()
    assert lab.set_page(9, "VERIFIED", note="ok")["status"] == "VERIFIED"


def test_a_build_needs_the_supported_stack(tmp_path):
    from pdfmeasure import stack

    out = tmp_path / "o"
    out.mkdir()
    build = EbookState(out)
    build.init(kind="web-fixed", pages=[9], pilot=[9])
    empty = tmp_path / "empty"
    empty.mkdir()
    assert any("not supported yet" in p and "no components.json" in p for p in build.run_gate("scope", root=empty))
    old = make_stack(tmp_path / "old", tailwind="^3.4.1")
    assert any("tailwindcss ^3.4.1" in p for p in build.run_gate("scope", root=old))
    build.data["gates"]["inventory"] = {"passed": True}
    make_spec(out, 9)
    with pytest.raises(StateError, match="gate scope has not passed"):
        build.set_page(9, "IN_PROGRESS", note="start")
    assert build.run_gate("scope", root=make_stack(tmp_path / "ok")) == []
    assert build.scope["stack"]["app"] == "apps/web" and build.set_page(9, "IN_PROGRESS", note="start")["status"] == "IN_PROGRESS"
    analysis = EbookState(tmp_path / "a")
    analysis.init(kind="analysis", pages=[9], pilot=[])
    assert analysis.run_gate("scope", root=empty) == []  # an analysis builds nothing: no stack needed


def test_pilot_and_book_gates_check_the_module_layout(state, tmp_path):
    inventory_pass(state)
    state.set_page(9, "IN_PROGRESS", note="start")
    ready(state, 9)
    state.set_page(9, "VERIFIED", note="ok")
    assert state.run_gate("pilot") == []
    broken = Path(state.scope["module"]["path"]) / "books/vitamin-1/kit/example-label/example-label.tsx"
    broken.write_text(broken.read_text().replace("style={{ '--label-h'", "style={{ height"))
    assert any(p.startswith("structure: L4") for p in state.run_gate("pilot"))
    broken.write_text(broken.read_text().replace("style={{ height", "style={{ '--label-h'"))
    state.data["scope"]["module"]["book"] = "unknown-book"
    assert any("book 'unknown-book' has no folder" in p for p in state.run_gate("pilot"))
    del state.data["scope"]["module"]
    assert any("no module declared" in p for p in state.run_gate("pilot"))


def test_a_web_fixed_page_needs_the_desktop_and_mobile_check(state):
    inventory_pass(state)
    state.set_page(9, "IN_PROGRESS", note="start")
    ready(state, 9)
    make_reflow(state.output, 9, auto=False)
    with pytest.raises(StateError, match="desktop and mobile are both required"):
        state.set_page(9, "VERIFIED", note="done")
    make_reflow(state.output, 9)
    assert state.set_page(9, "VERIFIED", note="ok")["status"] == "VERIFIED"


def test_gates_need_a_fresh_passing_kit_consistency(state):
    inventory_pass(state)
    state.set_page(9, "IN_PROGRESS", note="start")
    ready(state, 9)
    state.set_page(9, "VERIFIED", note="ok")
    assert state.run_gate("pilot") == []
    make_consistency(state.output, "ERROR")
    assert any("kit consistency ERROR: example-label" in p for p in state.run_gate("pilot"))
    (state.output / "consistency.json").unlink()
    assert any("no kit consistency result" in p for p in state.run_gate("pilot"))
    make_consistency(state.output)
    time.sleep(0.01)
    scan(state.output, 9)
    assert any("older than the latest scan" in p for p in state.run_gate("pilot") if "consistency" in p)
