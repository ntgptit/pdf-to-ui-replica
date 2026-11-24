"""Commands of the visual QA loop: qa-start, visual-compare, issue, codex-prompt, codex-run, qa-report, qa-finish."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import codex as codex_module
from . import qa_run, visual
from .ebook_state import EbookState
from .issues import DEFAULT_MAX_FAILED_ROUNDS, IssueError, IssueStore


def page_dir(output: str, page: int) -> Path:
    return Path(output) / "pages" / f"page-{page:03d}"


def command_qa_start(args: argparse.Namespace) -> int:
    print(json.dumps(qa_run.start_run(args.output, args.root), indent=2))
    return 0


def command_visual_compare(args: argparse.Namespace) -> int:
    """PDF vs the rebuilt page. --label v0 is the baseline; v1 (or later) also writes progress against v0 and the three-part picture."""
    from .cli import page_width

    folder = page_dir(args.output, args.page)
    folder.mkdir(parents=True, exist_ok=True)
    work = Path(args.run_dir) / "working-images" if args.run_dir else folder / "_work"
    work.mkdir(parents=True, exist_ok=True)
    if not args.react_image and not args.url:
        print("visual-compare: give --url (capture the page) or --react-image (an existing screenshot)")
        return 2
    pdf_path = visual.render_pdf_page(args.pdf, args.page, work / f"pdf-{args.page}.png", args.zoom)
    if args.react_image:
        react_path = Path(args.react_image)
    else:
        react_path = visual.capture_react(args.url, work / f"react-{args.label}", page_width(args.pdf, args.page), args.sheet, args.zoom, args.attr, args.sheet_selector, args.css_per_pt)
    pdf_img, react_img = visual.load_rgb(pdf_path), visual.load_rgb(react_path)
    comparison, mask = visual.compare_images(pdf_img, react_img, args.zoom)
    metrics, crops = visual.write_evidence(folder, pdf_img, react_img, comparison, mask, args.label, args.crop_limit)
    before = folder / "metrics-v0.json"
    if args.label != "v0" and before.exists() and (folder / "react-v0.png").exists():
        v0_img = visual.load_rgb(folder / "react-v0.png")
        v0_cmp, _ = visual.compare_images(pdf_img, v0_img, args.zoom)
        visual.side_by_side([("PDF", pdf_img), ("React V0", v0_img), (f"React {args.label.upper()}", react_img)], folder / "triptych.png")
        progress = visual.compare_runs(v0_cmp, comparison, mask, args.zoom)
        (folder / "progress.json").write_text(json.dumps(progress, indent=2), encoding="utf-8")
        metrics["progress"] = progress
    failing, note = [], ""
    if args.verify_config:
        failing, note = _verify_page(args, folder)
    if mask is not None:
        layout, layout_note = _text_layout(args, pdf_img, react_img, work)
        failing += [f"text layout: {problem}" for problem in layout["problems"]]
        if layout["more"]:
            failing.append(f"text layout: ... and {layout['more']} more")
        if layout["empty"]:
            failing.append("text layout: no text lines found in the PDF page, nothing was verified")
        note = note or "- none"
        if layout_note:
            comparison.warnings.append(layout_note)
        metrics["text_layout"] = {key: layout[key] for key in ("pdf_lines", "react_lines", "matched", "worst")}
    scan = visual.scan_markdown(args.page, args.label, comparison, crops, metrics.get("progress"), failing, note)
    (folder / f"scan-{args.label}.md").write_text(scan, encoding="utf-8")
    print(scan)
    print(f"visual-compare: wrote {folder / f'scan-{args.label}.md'} (regions, crops, failing verify entries in one report)")
    if comparison.status == "size_mismatch":
        print("visual-compare: " + comparison.warnings[0], flush=True)
        return 2
    return 0


TEXT_LAYOUT_ZOOM = 6  # px/pt: the 0.3 pt line-pitch tolerance is under one pixel at 3 px/pt (1 px = 0.33 pt), so it needs at least this
MIN_TOLERANCE_PX = 1.5


def _text_layout(args: argparse.Namespace, pdf_img, react_img, work: Path) -> tuple[dict, str]:
    """Text-layout check of the scan. With --url it is re-rendered at 6 px/pt (the same check `verify` runs). With only --react-image the given pictures are used and
    the tolerances are never finer than 1.5 px (a one-pixel difference is not a defect); the scan says so, and `verify` stays the exact check."""
    from . import textlayout

    from .cli import page_width

    zoom, cfg, note = args.zoom, {}, ""
    if args.url and zoom < TEXT_LAYOUT_ZOOM:
        zoom = TEXT_LAYOUT_ZOOM
        pdf_img = visual.load_rgb(visual.render_pdf_page(args.pdf, args.page, work / f"pdf-{args.page}-z{zoom}.png", zoom))
        react_img = visual.load_rgb(visual.capture_react(args.url, work / f"react-{args.label}-z{zoom}", page_width(args.pdf, args.page), args.sheet, zoom, args.attr, args.sheet_selector, args.css_per_pt))
    elif zoom < TEXT_LAYOUT_ZOOM:
        floor = round(MIN_TOLERANCE_PX / zoom, 2)
        cfg = {"tolerance_left": max(0.5, floor), "tolerance_vertical": max(0.5, floor), "tolerance_pitch": max(0.3, floor)}
        note = f"text layout checked on the given {zoom} px/pt image: tolerances widened to {floor} pt (1.5 px); run `verify` (6 px/pt) for the exact 0.3/0.5 pt check"
    result = textlayout.compare(textlayout.segments(pdf_img, zoom, cfg), textlayout.segments(react_img, zoom, cfg), cfg)
    return result, note


def _verify_page(args: argparse.Namespace, folder: Path) -> tuple[list[str], str]:
    """Run geometry + zoom verify for this PDF page only, in the same pass, and return what failed (so one run gives the whole error report)."""
    from .cli import command_verify

    config_path = Path(args.verify_config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["pages"] = [entry for entry in config["pages"] if entry["pdf_page"] == args.page]
    if not config["pages"]:
        return [], f"- verify config has no entry for PDF page {args.page}"
    filtered = config_path.parent / f".verify-page-{args.page}.json"  # next to the config so relative paths keep working
    filtered.write_text(json.dumps(config), encoding="utf-8")
    try:
        out = folder / f"verify-{args.label}"
        code = command_verify(argparse.Namespace(config=str(filtered), pdf=args.pdf, url=args.url, out=str(out)))
    finally:
        filtered.unlink(missing_ok=True)
    failing: list[str] = []
    for name in ("geometry.md", "zoom.md"):
        for line in (out / name).read_text(encoding="utf-8").splitlines():
            if "**off" in line:
                failing.append(f"{name.split('.')[0]}: {line.strip('| ')}")
    return failing, f"- verify ran (exit {code}); every entry within tolerance" if not failing else ""


def _store(args: argparse.Namespace) -> IssueStore:
    """The failed-round cap comes from the ebook state when there is one (`state init --max-failed-rounds`)."""
    state = EbookState(args.output)
    cap = state.scope["max_failed_rounds"] if state.exists else DEFAULT_MAX_FAILED_ROUNDS
    return IssueStore(Path(args.output) / "issues.json", cap)


def _knowhow_id(value: str | None) -> str:
    """A knowhow id given with a defect must exist in the register (references/knowhow.json)."""
    if not value:
        return ""
    from . import knowhow

    knowhow.get(knowhow.load(), value)  # raises KnowhowError for an unknown id
    return value


def command_issue(args: argparse.Namespace) -> int:
    store = _store(args)
    try:
        if args.action == "add":
            issue = store.add(
                run=args.run, page=args.page, description=args.description, region=[float(v) for v in args.region.split(",")], type=args.type, severity=args.severity,
                object_id=args.object, evidence=args.evidence or [], cause=args.cause or "", fix_plan=args.fix or "", knowhow=_knowhow_id(args.knowhow),
            )
        elif args.action == "status":
            issue = store.set_status(args.id, args.status, run=args.run, note=args.note, evidence=args.evidence or [], reset_rounds=args.reset_rounds or "")
            if issue["status"] != args.status:
                print(f"issue: {args.id} is now {issue['status']} (not {args.status}): {issue['failed_rounds']} fixes did not hold; see its history")
        elif args.action == "add-batch":
            issue = None
            for entry in json.loads(Path(args.file).read_text(encoding="utf-8")):
                store.add(run=args.run, page=entry["page"], description=entry["description"], region=entry["region"], type=entry["type"], severity=entry["severity"], object_id=entry.get("object"), evidence=entry.get("evidence", []), cause=entry.get("cause", ""), fix_plan=entry.get("fix", ""), knowhow=_knowhow_id(entry.get("knowhow")))
        elif args.action == "note-run":
            store.note_run(args.run, args.note or "checked")
            issue = None
        else:
            issue = None
    except (IssueError, ValueError) as error:
        print(f"issue: {error}")
        return 2
    store.save()
    if args.action == "list":
        print(store.to_markdown())
        return 0
    print(json.dumps(issue, indent=2, ensure_ascii=False) if issue else "ok")
    return 0


def command_codex_prompt(args: argparse.Namespace) -> int:
    store = _store(args)
    issues = [store.get(item) for item in args.issues.split(",")]
    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    try:
        path = codex_module.write_prompt(Path(args.output) / "codex-prompts", issues, context)
    except codex_module.HandoffError as error:
        print(f"codex-prompt: {error}")
        return 2
    for issue in issues:
        store.update(issue["id"], codex_prompt=str(path.relative_to(args.output)))
        if issue["status"] in ("OPEN", "FIXING"):
            store.set_status(issue["id"], "CODEX_READY", run=args.run, note=f"hard defect handed over in {path.name}")
    store.save()
    print(path)
    return 0


def command_codex_run(args: argparse.Namespace) -> int:
    store = _store(args)
    output = Path(args.output)
    files = sorted((output / "codex-prompts").glob("*.md"))
    if args.only:
        files = [f for f in files if f.name in args.only]
    info = codex_module.detect()
    wanted = {str(f.relative_to(output)) for f in files}
    issues = [i for i in store.issues if i["codex_prompt"] in wanted and i["status"] == "CODEX_READY"]
    if not info.available or not files:
        codex_module.write_execution(output / "codex-results" / "execution.md", info, files, [], None)
        print(f"codex-run: Codex NOT run ({info.reason or 'no prompts'}); prompts kept, issues stay CODEX_READY")
        return 3
    for issue in issues:
        store.set_status(issue["id"], "CODEX_RUNNING", run=args.run, note="sent to Codex")
    store.save()
    results, mode = codex_module.run_prompts(files, info, Path(args.cwd))
    codex_module.write_execution(output / "codex-results" / "execution.md", info, files, results, mode)
    ok = all(r.exit_code == 0 for r in results) and len(results) >= 1
    for issue in issues:
        store.set_status(issue["id"], "NEEDS_VERIFY" if ok else "CODEX_READY", run=args.run, note="Codex finished (exit 0); re-capture and verify" if ok else "Codex failed; prompt kept")
    store.save()
    print(f"codex-run: {'finished' if ok else 'failed'}; see codex-results/execution.md. Issues are NEEDS_VERIFY, not fixed, until re-captured.")
    return 0 if ok else 1


def command_qa_report(args: argparse.Namespace) -> int:
    store = _store(args)
    codex = None
    if args.codex_info:
        info = codex_module.detect()
        prompts = sorted(str(p.relative_to(args.output)) for p in (Path(args.output) / "codex-prompts").glob("*.md"))
        executed = (Path(args.output) / "codex-results" / "execution.md").exists() and "was NOT run" not in (Path(args.output) / "codex-results" / "execution.md").read_text(encoding="utf-8")
        codex = {"info": info, "prompts": prompts, "executed": executed}
    progress = {}
    for page in args.pages:
        file = page_dir(args.output, page) / "progress.json"
        if file.exists():
            progress[page] = json.loads(file.read_text(encoding="utf-8"))
    verify = json.loads(Path(args.verify).read_text(encoding="utf-8")) if args.verify else None
    state = EbookState(args.output)
    coverage = state.coverage_lines() if state.exists else None
    path = qa_run.write_report(args.output, store, run=args.run, baseline_run=args.baseline_run, pages=args.pages, progress=progress, verify=verify, codex=codex, unverified=args.unverified, coverage=coverage)
    print(path)
    return 0


def command_qa_finish(args: argparse.Namespace) -> int:
    try:
        removed = qa_run.finish_run(args.output, {"run_id": args.run_id, "run_dir": args.run_dir}, not args.failed, args.root, args.log or "")
    except qa_run.CleanupRefused as error:
        print(f"qa-finish: refused: {error}")
        return 2
    print(f"removed {removed} temporary file(s); evidence, report and prompts kept")
    return 0


def register(add) -> None:
    start = add("qa-start", command_qa_start, "create the output folders and the run's private temp folder")
    start.add_argument("--output", required=True)
    start.add_argument("--root", default=".")

    vc = add("visual-compare", command_visual_compare, "whole page: PDF vs rebuilt page, side by side, overlay, heatmap, regions, metrics (no pixel verdict)")
    vc.add_argument("--pdf", required=True)
    vc.add_argument("--page", type=int, required=True)
    vc.add_argument("--output", required=True)
    vc.add_argument("--label", default="v0", help="v0 = baseline, v1... = after a repair (also writes progress against v0 and triptych.png)")
    vc.add_argument("--url")
    vc.add_argument("--react-image", help="an existing screenshot instead of capturing the url")
    vc.add_argument("--sheet", type=int, default=0)
    vc.add_argument("--zoom", type=int, default=3)
    vc.add_argument("--css-per-pt", type=float, default=8)
    vc.add_argument("--attr", default="data-wb")
    vc.add_argument("--sheet-selector")
    vc.add_argument("--run-dir")
    vc.add_argument("--crop-limit", type=int, default=40)
    vc.add_argument("--verify-config", help="also run geometry + zoom verify for this page in the same pass and list what fails in the scan report")

    issue = add("issue", command_issue, "visual defect inventory: add | add-batch | status | note-run | list")
    issue.add_argument("action", choices=["add", "add-batch", "status", "note-run", "list"])
    issue.add_argument("--output", required=True)
    issue.add_argument("--run", default="run-0")
    issue.add_argument("--id")
    issue.add_argument("--page", type=int)
    issue.add_argument("--object")
    issue.add_argument("--description")
    issue.add_argument("--region", help="x,top,width,height in points")
    issue.add_argument("--type")
    issue.add_argument("--severity")
    issue.add_argument("--status")
    issue.add_argument("--note")
    issue.add_argument("--reset-rounds", help="status: restart the failed-round count; needs a written reason (why one more try is likely to work)")
    issue.add_argument("--cause")
    issue.add_argument("--fix")
    issue.add_argument("--knowhow", help="KH-nnn of the knowhow entry this defect matches (`knowhow search` first); add-batch: a `knowhow` field per entry")
    issue.add_argument("--evidence", action="append")
    issue.add_argument("--file", help="add-batch: JSON list of {page, description, region, type, severity, object?, evidence?, cause?, fix?} written after triaging scan-<label>.md")

    cp = add("codex-prompt", command_codex_prompt, "write a self-contained Codex prompt for one issue or a linked group")
    cp.add_argument("--output", required=True)
    cp.add_argument("--run", default="run-0")
    cp.add_argument("--issues", required=True, help="ISS-001 or ISS-001,ISS-002 for a tightly linked group")
    cp.add_argument("--context", required=True, help="JSON with goal, object_description, evidence, measures, cause, source_files, approach, constraints, acceptance, commands, allowed_files")

    cr = add("codex-run", command_codex_run, "run the prompts with the Codex CLI if it works; otherwise keep them and say so")
    cr.add_argument("--output", required=True)
    cr.add_argument("--run", default="run-0")
    cr.add_argument("--cwd", default=".")
    cr.add_argument("--only", nargs="*")

    rep = add("qa-report", command_qa_report, "write report.md from the issues, progress files and Codex state")
    rep.add_argument("--output", required=True)
    rep.add_argument("--run", default="run-1")
    rep.add_argument("--baseline-run", default="run-0")
    rep.add_argument("--pages", type=int, nargs="+", required=True)
    rep.add_argument("--verify", help="JSON file of geometry/zoom results to quote")
    rep.add_argument("--codex-info", action="store_true")
    rep.add_argument("--unverified", action="append")

    fin = add("qa-finish", command_qa_finish, "delete the run's temp folder (nothing else); a failed run first saves its log")
    fin.add_argument("--output", required=True)
    fin.add_argument("--run-id", required=True)
    fin.add_argument("--run-dir", required=True)
    fin.add_argument("--root", default=".")
    fin.add_argument("--failed", action="store_true")
    fin.add_argument("--log")
