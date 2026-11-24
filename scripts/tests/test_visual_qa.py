"""Visual QA loop: full-page compare, issue lifecycle, report, Codex handoff and fallback, cleanup. No PDF, browser or Codex needed."""
import json
import os
import stat
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmeasure import codex, qa_run, visual  # noqa: E402
from pdfmeasure.issues import IssueError, IssueStore  # noqa: E402

ZOOM = 3
W, H = 120, 160  # points


def page_image(shift=(0, 0), with_picture=True, with_title=True):
    image = np.full((H * ZOOM, W * ZOOM, 3), 255, dtype=int)
    dx, dy = shift
    if with_title:
        image[(10 + dy) * ZOOM : (22 + dy) * ZOOM, (10 + dx) * ZOOM : (90 + dx) * ZOOM] = (30, 30, 30)
    if with_picture:
        image[(60 + dy) * ZOOM : (110 + dy) * ZOOM, (30 + dx) * ZOOM : (80 + dx) * ZOOM] = (200, 60, 60)
    return image


# ---- full-page comparison -----------------------------------------------------------------------------------------------------------------
def test_identical_pages_have_no_regions_and_never_a_pixel_verdict():
    comparison, mask = visual.compare_images(page_image(), page_image(), ZOOM)
    assert comparison.status == "needs_review" and comparison.diff_ratio == 0 and comparison.regions == [] and not mask.any()


def test_a_missing_picture_becomes_one_region_over_the_picture():
    comparison, _ = visual.compare_images(page_image(), page_image(with_picture=False), ZOOM)
    assert comparison.diff_ratio > 0.05 and len(comparison.regions) == 1
    x, top, width, height = comparison.regions[0].box()
    assert 25 <= x <= 32 and 55 <= top <= 62 and 48 <= width <= 56 and 48 <= height <= 56


def test_a_misaligned_page_is_reported_as_a_registration_error():
    comparison, _ = visual.compare_images(page_image(), page_image(shift=(4, 3)), ZOOM)
    assert any("shifted" in warning for warning in comparison.warnings)
    assert comparison.global_shift_pt[0] != 0


def test_different_sizes_are_reported_and_never_resized():
    small = page_image()[:-30, :-30]
    comparison, mask = visual.compare_images(page_image(), small, ZOOM)
    assert comparison.status == "size_mismatch" and mask is None and comparison.regions == []
    assert "not compared and not resized" in comparison.warnings[0]


def test_regression_after_a_repair_is_detected():
    pdf, v0 = page_image(), page_image(with_picture=False)
    c0, _ = visual.compare_images(pdf, v0, ZOOM)
    fixed, m1 = visual.compare_images(pdf, pdf.copy(), ZOOM)
    good = visual.compare_runs(c0, fixed, m1, ZOOM)
    assert good["comparable"] and not good["regression"] and len(good["improved"]) == 1
    worse_img = page_image(with_picture=False, with_title=False)
    c_worse, m_worse = visual.compare_images(pdf, worse_img, ZOOM)
    bad = visual.compare_runs(c0, c_worse, m_worse, ZOOM)
    assert bad["regression"] and bad["new_regions"]


def test_a_size_mismatch_run_is_not_comparable():
    pdf = page_image()
    c_bad, m_bad = visual.compare_images(pdf, pdf[:-30], ZOOM)
    c_ok, _ = visual.compare_images(pdf, pdf, ZOOM)
    assert visual.compare_runs(c_ok, c_bad, m_bad, ZOOM)["comparable"] is False


def test_evidence_files_are_written(tmp_path):
    pdf, react = page_image(), page_image(with_picture=False)
    comparison, mask = visual.compare_images(pdf, react, ZOOM)
    _, crops = visual.write_evidence(tmp_path, pdf, react, comparison, mask, "v0")
    assert crops
    for name in ("pdf.png", "react-v0.png", "pdf-vs-v0.png", "overlay-v0.png", "heatmap-v0.png", "metrics-v0.json"):
        assert (tmp_path / name).exists(), name
    assert list((tmp_path / "crops" / "v0").glob("region-*.png"))
    assert json.loads((tmp_path / "metrics-v0.json").read_text())["regions"]


def test_a_size_mismatch_writes_the_side_by_side_but_no_diff_images(tmp_path):
    pdf = page_image()
    comparison, mask = visual.compare_images(pdf, pdf[:-30], ZOOM)
    visual.write_evidence(tmp_path, pdf, pdf[:-30], comparison, mask, "v0")
    assert (tmp_path / "pdf-vs-v0.png").exists() and not (tmp_path / "heatmap-v0.png").exists()


# ---- issue lifecycle ----------------------------------------------------------------------------------------------------------------------
def add(store, **kw):
    base = dict(run="run-0", page=1, description="picture missing", region=[30.0, 60.0, 50.0, 50.0], type="missing", severity="P1", object_id="OBJ-003", evidence=["pages/page-001/crops/v0/region-01.png"], cause="asset not drawn")
    base.update(kw)
    return store.add(**base)


def test_the_same_unresolved_defect_keeps_its_id_across_runs(tmp_path):
    store = IssueStore(tmp_path / "issues.json")
    first = add(store)
    again = add(store, run="run-1", region=[31.0, 61.0, 49.0, 49.0])
    assert first["id"] == again["id"] == "ISS-001" and len(store.issues) == 1 and len(first["history"]) == 2
    other = add(store, object_id="OBJ-009")
    assert other["id"] == "ISS-002"
    store.save()
    reloaded = IssueStore(tmp_path / "issues.json")
    assert reloaded.get("ISS-001")["history"][1]["run"] == "run-1"
    assert add(reloaded, run="run-2")["id"] == "ISS-001"  # status was not reset by a reload


def test_verified_needs_evidence_and_the_path_through_needs_verify(tmp_path):
    store = IssueStore(tmp_path / "i.json")
    issue = add(store, evidence=[])
    with pytest.raises(IssueError):
        store.set_status(issue["id"], "VERIFIED", run="run-1", note="looks right")  # OPEN -> VERIFIED
    store.set_status(issue["id"], "FIXING", run="run-1", note="drawing it")
    store.set_status(issue["id"], "NEEDS_VERIFY", run="run-1", note="drawn")
    with pytest.raises(IssueError):
        store.set_status(issue["id"], "VERIFIED", run="run-1", note="looks right")  # no evidence
    store.set_status(issue["id"], "VERIFIED", run="run-1", note="compared with the PDF crop", evidence=["pages/page-001/crops/v1/region-01.png"])
    assert store.get(issue["id"])["status"] == "VERIFIED"


def test_a_regression_reopens_the_same_issue_and_a_limitation_needs_a_reason(tmp_path):
    store = IssueStore(tmp_path / "i.json")
    issue = add(store)
    store.set_status(issue["id"], "FIXING", run="run-1", note="x")
    store.set_status(issue["id"], "NEEDS_VERIFY", run="run-1", note="x")
    store.set_status(issue["id"], "VERIFIED", run="run-1", note="ok")
    store.set_status(issue["id"], "OPEN", run="run-2", note="regressed")
    assert len(store.issues) == 1 and store.get(issue["id"])["status"] == "OPEN"
    with pytest.raises(IssueError):
        store.set_status(issue["id"], "ACCEPTED_LIMITATION", run="run-2", note=" ")


def test_rejects_unknown_severity_type_and_bad_region(tmp_path):
    store = IssueStore(tmp_path / "i.json")
    for bad in ({"severity": "P9"}, {"type": "weird"}, {"region": [1, 2, 3]}):
        with pytest.raises(IssueError):
            add(store, **bad)


def test_page_is_not_complete_while_a_p0_or_p1_is_unresolved(tmp_path):
    store = IssueStore(tmp_path / "i.json")
    add(store, severity="P2", type="spacing", object_id="OBJ-004")
    assert store.page_complete()[0]
    p1 = add(store)
    done, blockers = store.page_complete()
    assert not done and p1["id"] in blockers[0]
    store.set_status(p1["id"], "ACCEPTED_LIMITATION", run="run-1", note="artwork differs by design")
    assert store.page_complete()[0]


# ---- report -----------------------------------------------------------------------------------------------------------------------------
def test_report_says_not_complete_and_lists_counts_prompts_and_codex_state(tmp_path):
    store = IssueStore(tmp_path / "issues.json")
    p1 = add(store)
    store.update(p1["id"], codex_prompt="codex-prompts/p001-obj003-issue001.md")
    info = codex.CodexInfo(False, "the `codex` executable is not on PATH")
    path = qa_run.write_report(tmp_path, store, run="run-1", baseline_run="run-0", pages=[1], codex={"info": info, "prompts": ["codex-prompts/p001-obj003-issue001.md"], "executed": False}, unverified=["illustration colours"])
    text = path.read_text()
    assert "NOT complete" in text and "ISS-001" in text and "NOT available" in text and "NO (prompts kept" in text and "illustration colours" in text


# ---- Codex handoff ----------------------------------------------------------------------------------------------------------------------
CONTEXT = {
    "goal": "Draw the cat picture", "object_description": "A cat on a pillow", "evidence": ["pages/page-001/pdf.png", "pages/page-001/crops/v0/region-01.png"],
    "measures": "box 30,60,50,50 pt", "cause": "asset missing", "source_files": ["src/page.tsx"], "approach": "SVG",
    "constraints": "keep tokens", "acceptance": ["region 1 shows the cat"], "commands": ["pnpm build"], "allowed_files": ["src/page.tsx"],
}


def test_prompt_has_the_eleven_sections_and_every_issue_id(tmp_path):
    store = IssueStore(tmp_path / "i.json")
    a, b = add(store), add(store, object_id="OBJ-004", region=[0, 0, 10, 10])
    text = codex.build_prompt([a, b], CONTEXT)
    for _, title in codex.SECTIONS:
        assert title in text
    assert "ISS-001" in text and "ISS-002" in text
    path = codex.write_prompt(tmp_path / "codex-prompts", [a], CONTEXT)
    assert path.name == "p001-obj003-issue001.md"


def test_handoff_is_refused_without_a_cause_or_with_a_thin_context(tmp_path):
    store = IssueStore(tmp_path / "i.json")
    with pytest.raises(codex.HandoffError):
        codex.build_prompt([add(store, cause="")], CONTEXT)
    with pytest.raises(codex.HandoffError):
        codex.build_prompt([add(store, object_id="OBJ-7")], {**CONTEXT, "acceptance": ""})


def fake_codex(directory: Path, resume=True, prompt_arg=True) -> Path:
    script = directory / "codex"
    exec_help = "Usage: codex exec [OPTIONS] [PROMPT] [COMMAND]\\nCommands:\\n  resume  Resume a session\\n" if prompt_arg else "Usage: codex exec [OPTIONS]\\n"
    resume_help = "Usage: codex exec resume [OPTIONS] [SESSION_ID] [PROMPT]\\n  --last"
    script.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "exec" ] && [ "$2" = "--help" ]; then printf \'' + exec_help + "'; exit 0; fi\n"
        'if [ "$1" = "exec" ] && [ "$2" = "resume" ] && [ "$3" = "--help" ]; then ' + ("printf '" + resume_help + "'; exit 0; " if resume else "exit 2; ") + "fi\n"
        "echo \"session id: 0192abcd-1111\"; exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_detect_without_the_cli_says_so(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    info = codex.detect()
    assert not info.available and "not on PATH" in info.reason


def test_detect_reads_the_syntax_from_help(tmp_path, monkeypatch):
    fake_codex(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    info = codex.detect()
    assert info.available and info.supports_resume and info.resume_selector == "--last"
    fake_codex(tmp_path, resume=False)
    assert not codex.detect().supports_resume
    fake_codex(tmp_path, prompt_arg=False)
    unknown = codex.detect()
    assert not unknown.available and "PROMPT" in unknown.reason


def test_prompts_run_resumed_in_one_session_or_merged(tmp_path):
    prompts = []
    for n in (1, 2):
        path = tmp_path / f"p001-obj00{n}-issue00{n}.md"
        path.write_text(f"task {n}")
        prompts.append(path)
    calls = []

    class Done:
        returncode, stdout, stderr = 0, "session id: abcdef12-3456", ""

    def execute(command, timeout, cwd):
        calls.append(command)
        return Done()

    resumed = codex.CodexInfo(True, "", "/bin/codex", "", True, "--last", True)
    results, mode = codex.run_prompts(prompts, resumed, tmp_path, execute=execute)
    assert mode == "separate resumed runs" and len(results) == 2 and calls[1][:4] == ["/bin/codex", "exec", "resume", "--last"] and results[0].session == "abcdef12-3456"
    calls.clear()
    merged_info = codex.CodexInfo(True, "", "/bin/codex", "", False, None, True)
    results, mode = codex.run_prompts(prompts, merged_info, tmp_path, execute=execute)
    assert mode == "one merged run" and len(calls) == 1 and "task 1" in calls[0][2] and "task 2" in calls[0][2]


def test_a_failed_codex_run_stops_and_reports_the_exit_code(tmp_path):
    path = tmp_path / "p001-obj001-issue001.md"
    path.write_text("x")
    second = tmp_path / "p001-obj002-issue002.md"
    second.write_text("y")

    class Failed:
        returncode, stdout, stderr = 7, "", "boom"

    info = codex.CodexInfo(True, "", "/bin/codex", "", True, "--last", True)
    results, _ = codex.run_prompts([path, second], info, tmp_path, execute=lambda c, t, w: Failed())
    assert len(results) == 1 and results[0].exit_code == 7
    codex.write_execution(tmp_path / "execution.md", info, [path, second], results, "x")
    assert "exit code: 7" in (tmp_path / "execution.md").read_text()


def test_without_codex_the_prompts_stay_and_the_file_says_not_run(tmp_path):
    info = codex.CodexInfo(False, "the `codex` executable is not on PATH")
    prompt = tmp_path / "codex-prompts" / "p001-obj003-issue001.md"
    prompt.parent.mkdir()
    prompt.write_text("keep me")
    codex.write_execution(tmp_path / "codex-results" / "execution.md", info, [prompt], [], None)
    text = (tmp_path / "codex-results" / "execution.md").read_text()
    assert "was NOT run" in text and "p001-obj003-issue001.md" in text and prompt.read_text() == "keep me"


def test_cli_codex_run_without_codex_leaves_issues_ready(tmp_path, monkeypatch):
    from pdfmeasure import cli

    monkeypatch.setenv("PATH", "/nonexistent")
    store = IssueStore(tmp_path / "issues.json")
    issue = add(store)
    store.save()
    context = tmp_path / "ctx.json"
    context.write_text(json.dumps(CONTEXT))
    assert cli.main(["codex-prompt", "--output", str(tmp_path), "--issues", issue["id"], "--context", str(context)]) == 0
    assert IssueStore(tmp_path / "issues.json").get(issue["id"])["status"] == "CODEX_READY"
    assert cli.main(["codex-run", "--output", str(tmp_path)]) == 3
    assert IssueStore(tmp_path / "issues.json").get(issue["id"])["status"] == "CODEX_READY"
    assert "was NOT run" in (tmp_path / "codex-results" / "execution.md").read_text()
    assert list((tmp_path / "codex-prompts").glob("*.md"))


def test_cli_codex_run_with_a_fake_cli_ends_at_needs_verify_not_verified(tmp_path, monkeypatch):
    from pdfmeasure import cli

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_codex(bin_dir)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    out = tmp_path / "out"
    store = IssueStore(out / "issues.json")
    issue = add(store)
    store.save()
    context = tmp_path / "ctx.json"
    context.write_text(json.dumps(CONTEXT))
    cli.main(["codex-prompt", "--output", str(out), "--issues", issue["id"], "--context", str(context)])
    assert cli.main(["codex-run", "--output", str(out), "--cwd", str(tmp_path)]) == 0
    assert IssueStore(out / "issues.json").get(issue["id"])["status"] == "NEEDS_VERIFY"
    assert "exit code: 0" in (out / "codex-results" / "execution.md").read_text()


# ---- cleanup ----------------------------------------------------------------------------------------------------------------------------
def test_cleanup_removes_only_the_run_folder_and_keeps_the_evidence(tmp_path):
    output = tmp_path / "out"
    run = qa_run.start_run(output, tmp_path)
    (output / "report.md").write_text("keep")
    (output / "codex-prompts" / "p.md").write_text("keep")
    (Path(run["run_dir"]) / "working-images" / "big.png").write_bytes(b"x" * 10)
    removed = qa_run.finish_run(output, run, True, tmp_path)
    assert removed >= 2 and not Path(run["run_dir"]).exists()
    assert (output / "report.md").read_text() == "keep" and (output / "codex-prompts" / "p.md").exists()
    assert (tmp_path / ".tmp" / "pdf-to-ui").is_dir()


def test_cleanup_refuses_anything_that_is_not_a_marked_run_folder(tmp_path):
    base = tmp_path / ".tmp" / "pdf-to-ui"
    base.mkdir(parents=True)
    victim = tmp_path / "src"
    victim.mkdir()
    (victim / "a.txt").write_text("source")
    for target in (victim, base, tmp_path, base / "not-a-run-id"):
        (target).mkdir(exist_ok=True)
        with pytest.raises(qa_run.CleanupRefused):
            qa_run.cleanup_run(target, tmp_path)
    unmarked = base / "20260101-000000-abcd"
    unmarked.mkdir()
    with pytest.raises(qa_run.CleanupRefused):
        qa_run.cleanup_run(unmarked, tmp_path)
    link = base / "20260101-000000-beef"
    link.symlink_to(victim)
    with pytest.raises(qa_run.CleanupRefused):
        qa_run.cleanup_run(link, tmp_path)
    assert (victim / "a.txt").read_text() == "source"


def test_cleanup_does_not_follow_a_symlink_inside_the_run(tmp_path):
    output = tmp_path / "out"
    run = qa_run.start_run(output, tmp_path)
    outside = tmp_path / "precious"
    outside.mkdir()
    (outside / "file.txt").write_text("keep")
    (Path(run["run_dir"]) / "cache" / "link").symlink_to(outside)
    qa_run.cleanup_run(run["run_dir"], tmp_path, output)
    assert (outside / "file.txt").read_text() == "keep"


def test_cleanup_refuses_when_the_output_folder_is_inside_the_run(tmp_path):
    run = qa_run.start_run(tmp_path / "out", tmp_path)
    inside = Path(run["run_dir"]) / "cache" / "out"
    inside.mkdir()
    with pytest.raises(qa_run.CleanupRefused):
        qa_run.cleanup_run(run["run_dir"], tmp_path, inside)


def test_a_failed_run_keeps_a_log_and_the_report_then_cleans_up(tmp_path):
    output = tmp_path / "out"
    run = qa_run.start_run(output, tmp_path)
    (output / "report.md").write_text("partial report")
    qa_run.finish_run(output, run, False, tmp_path, log="capture failed: timeout")
    assert (output / "logs" / f"{run['run_id']}-failed.log").read_text() == "capture failed: timeout"
    assert (output / "report.md").read_text() == "partial report" and not Path(run["run_dir"]).exists()


def test_cli_visual_compare_end_to_end_on_screenshots(tmp_path, monkeypatch):
    from PIL import Image

    from pdfmeasure import cli, visual as visual_module

    pdf_png, react_png = tmp_path / "pdf.png", tmp_path / "react.png"
    Image.fromarray(page_image().astype(np.uint8)).save(pdf_png)
    Image.fromarray(page_image(with_picture=False).astype(np.uint8)).save(react_png)
    monkeypatch.setattr(visual_module, "render_pdf_page", lambda pdf, page, out, zoom: pdf_png)
    out = tmp_path / "out"
    args = ["visual-compare", "--pdf", "x.pdf", "--page", "1", "--output", str(out), "--zoom", str(ZOOM), "--react-image", str(react_png)]
    assert cli.main(args + ["--label", "v0"]) == 0
    fixed = tmp_path / "fixed.png"
    Image.fromarray(page_image().astype(np.uint8)).save(fixed)
    args[-1] = str(fixed)
    assert cli.main(args + ["--label", "v1"]) == 0
    folder = out / "pages" / "page-001"
    assert (folder / "triptych.png").exists() and json.loads((folder / "progress.json").read_text())["improved"]
    wrong = tmp_path / "wrong.png"
    Image.fromarray(page_image()[:-30].astype(np.uint8)).save(wrong)
    args[-1] = str(wrong)
    assert cli.main(args + ["--label", "v2"]) == 2  # size mismatch is a failure exit


def test_report_does_not_call_a_page_complete_when_only_minor_issues_remain(tmp_path):
    store = IssueStore(tmp_path / "issues.json")
    add(store, severity="P2", type="spacing", object_id="OBJ-004")
    text = qa_run.write_report(tmp_path, store, run="run-1", baseline_run="run-0", pages=[1]).read_text()
    assert "No unresolved P0/P1" in text and "1 P2/P3 issue(s) remain" in text and "NOT complete" not in text


def test_scan_report_lists_every_region_warnings_and_failing_entries(tmp_path):
    pdf, react = page_image(), page_image(with_picture=False)
    comparison, mask = visual.compare_images(pdf, react, ZOOM)
    _, crops = visual.write_evidence(tmp_path, pdf, react, comparison, mask, "v0")
    text = visual.scan_markdown(1, "v0", comparison, crops, None, ["geometry: | bubble right | 246.8 | 262.8 | +16 |"])
    assert "| 1 |" in text and "crops/v0/region-01.png" in text and "bubble right" in text and "needs_review" in text
    mismatch, _ = visual.compare_images(pdf, pdf[:-30], ZOOM)
    assert "WARNING" in visual.scan_markdown(1, "v0", mismatch, [], None, None)


def test_a_tiny_new_region_is_noted_but_is_not_a_regression():
    pdf = page_image()
    c0, _ = visual.compare_images(pdf, page_image(with_picture=False), ZOOM)
    nearly = pdf.copy()
    nearly[2 * ZOOM : 8 * ZOOM, 100 * ZOOM : 106 * ZOOM] = (0, 0, 0)  # a 6 x 6 pt speck elsewhere
    c1, m1 = visual.compare_images(pdf, nearly, ZOOM)
    result = visual.compare_runs(c0, c1, m1, ZOOM)
    assert result["new_regions"] and not result["regression"]


def test_issue_add_batch_records_triaged_candidates(tmp_path):
    from pdfmeasure import cli

    out = tmp_path / "out"
    batch = tmp_path / "triage.json"
    batch.write_text(json.dumps([{"page": 1, "description": "bubble too wide", "region": [10, 10, 50, 20], "type": "layout", "severity": "P2", "object": "OBJ-002"}, {"page": 1, "description": "same bubble again", "region": [11, 10, 50, 20], "type": "layout", "severity": "P2", "object": "OBJ-002"}]))
    assert cli.main(["issue", "add-batch", "--output", str(out), "--file", str(batch)]) == 0
    assert len(IssueStore(out / "issues.json").issues) == 1  # the second entry is the same defect
