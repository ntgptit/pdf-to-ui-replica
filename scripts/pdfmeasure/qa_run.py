"""Run folders, safe cleanup and the QA report.

Two places: the output folder (report, issues, evidence images, Codex prompts: kept for review) and a private temp folder of the run
(`<root>/.tmp/pdf-to-ui/<run-id>/`: deleted when the run ends). Cleanup removes only that one folder and refuses anything else.
"""
from __future__ import annotations

import json
import re
import secrets
import shutil
from datetime import datetime
from pathlib import Path

from .issues import RESOLVED, SEVERITIES, STATUSES, IssueStore

RUN_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
MARKER = ".pdf-to-ui-run"
TMP_SUBDIR = Path(".tmp") / "pdf-to-ui"


class CleanupRefused(RuntimeError):
    pass


def start_run(output_dir: str | Path, root: str | Path = ".") -> dict:
    """Create the output structure and the run's private temp folder. Returns the paths."""
    output = Path(output_dir)
    for sub in ("pages", "codex-prompts", "codex-results", "logs"):
        (output / sub).mkdir(parents=True, exist_ok=True)
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    run_dir = Path(root) / TMP_SUBDIR / run_id
    for sub in ("intermediate", "cache", "working-images"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    (run_dir / MARKER).write_text(run_id, encoding="utf-8")
    return {"run_id": run_id, "run_dir": str(run_dir), "output": str(output)}


def cleanup_run(run_dir: str | Path, root: str | Path = ".", output_dir: str | Path | None = None) -> int:
    """Delete one run's temp folder after proving it is one: right parent, right name, marker file, not a symlink, not the output folder. Returns files removed."""
    target = Path(run_dir)
    base = (Path(root) / TMP_SUBDIR).resolve()
    if target.is_symlink():
        raise CleanupRefused(f"{target} is a symlink")
    resolved = target.resolve()
    if resolved.parent != base:
        raise CleanupRefused(f"{resolved} is not directly inside {base}")
    if not RUN_ID.match(resolved.name):
        raise CleanupRefused(f"{resolved.name} is not a run id")
    marker = resolved / MARKER
    if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != resolved.name:
        raise CleanupRefused(f"{resolved} has no matching run marker")
    if output_dir is not None:
        out = Path(output_dir).resolve()
        if out == resolved or resolved in out.parents:
            raise CleanupRefused("the output folder is the run's temp folder or inside it")
    count = sum(1 for item in resolved.rglob("*") if item.is_file())
    shutil.rmtree(resolved)  # does not follow symlinks inside
    return count


def finish_run(output_dir: str | Path, run: dict, ok: bool, root: str | Path = ".", log: str = "") -> int:
    """End of a run: a failed run keeps its log in the output folder, then the temp folder goes either way. Evidence and prompts are never touched."""
    if not ok:
        logs = Path(output_dir) / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / f"{run['run_id']}-failed.log").write_text(log or "run failed (no log text given)", encoding="utf-8")
    return cleanup_run(run["run_dir"], root, output_dir)


# ---- report -----------------------------------------------------------------------------------------------------------------------------
def _link(path: str | None) -> str:
    return f"[{Path(path).name}]({path})" if path else "-"


def write_report(output_dir: str | Path, store: IssueStore, *, run: str, baseline_run: str, pages: list[int], progress: dict[int, dict] | None = None, verify: dict | None = None, codex: dict | None = None, unverified: list[str] | None = None, coverage: list[str] | None = None) -> Path:
    """report.md of a run. `progress` maps page -> compare_runs() result, `verify` the geometry/zoom summary, `codex` {info, prompts, executed}."""
    output = Path(output_dir)
    complete, blockers = store.page_complete()
    lines = [f"# Visual QA report: {run}", "", f"Pages in scope: {', '.join(map(str, pages))}", ""]
    lines += ["## Verdict", ""]
    minor = [i for i in store.unresolved() if i["severity"] in ("P2", "P3")]
    lines.append(f"No unresolved P0/P1 issue; {len(minor)} P2/P3 issue(s) remain listed below with their status. (Pixel numbers never decide this; inventory and verify results still apply.)" if complete else "**NOT complete**: unresolved P0/P1: " + ", ".join(blockers))
    if coverage:
        lines += ["", "## Page coverage (from ebook-state.json)", ""] + coverage
        if any(f"| {status} |" in row for row in coverage for status in ("NOT_STARTED", "IN_PROGRESS", "BLOCKED")):
            lines += ["", "**Book NOT complete**: pages above are not VERIFIED or ACCEPTED_LIMITATION."]
    lines += ["", "## Pictures", ""]
    for page in pages:
        folder = f"pages/page-{page:03d}"
        files = sorted(path.name for path in (output / folder).glob("*") if path.is_file())
        shown = [name for name in files if name.endswith(".png") and name.split("-")[0] in ("triptych.png", "pdf", "overlay", "heatmap") and name != "pdf.png"]
        shown += [name for name in files if name.startswith("scan-") and name.endswith(".md")]
        lines.append(f"### Page {page}")
        lines += [(f"- ![{name}]({folder}/{name})" if name.endswith(".png") else f"- [{name}]({folder}/{name}) (every region and failing entry of that scan)") for name in shown] or ["- no comparison images"]
        lines.append("")
    lines += ["## Issues", "", "| Issue ID | Page/Object | Severity | Description | Before | After | Status | Codex prompt |", "|---|---|---|---|---|---|---|---|"]
    for i in sorted(store.issues, key=lambda item: (SEVERITIES.index(item["severity"]), item["id"])):
        before = i["evidence"][0] if i["evidence"] else None
        after = i["evidence"][-1] if len(i["evidence"]) > 1 else None
        lines.append(f"| {i['id']} | {i['page']} / {i['object_id'] or '-'} | {i['severity']} | {i['description']} | {_link(before)} | {_link(after)} | {i['status']} | {_link(i['codex_prompt'])} |")
    lines += ["", "## Counts", "", "| Severity | " + " | ".join(STATUSES) + " |", "|---|" + "---|" * len(STATUSES)]
    for severity, row in store.counts().items():
        lines.append(f"| {severity} | " + " | ".join(str(row[status]) for status in STATUSES) + " |")
    fixed = [i for i in store.issues if i["status"] == "VERIFIED"]
    reopened = [i for i in store.issues if any(h["status"] == "VERIFIED" for h in i["history"]) and i["status"] != "VERIFIED"]
    new = [i for i in store.issues if i["history"] and i["history"][0]["run"] == run and run != baseline_run]
    lines += ["", "## Fixed and confirmed", ""] + ([f"- {i['id']}: {i['description']}" for i in fixed] or ["- none"])
    lines += ["", "## Regressions (verified earlier, open again)", ""] + ([f"- {i['id']}: {i['description']}" for i in reopened] or ["- none"])
    lines += ["", "## New after the repair", ""] + ([f"- {i['id']}: {i['description']}" for i in new] or ["- none"])
    remaining = store.unresolved()
    lines += ["", "## Still open and why", ""] + ([f"- {i['id']} ({i['severity']}, {i['status']}): {i['cause'] or 'cause not analysed'}" for i in remaining] or ["- none"])
    accepted = [i for i in store.issues if i["status"] == "ACCEPTED_LIMITATION"]
    lines += ["", "## Accepted limitations", ""] + ([f"- {i['id']}: {i['history'][-1]['note']}" for i in accepted] or ["- none"])
    linked = [i for i in store.issues if i.get("knowhow")]
    candidates = [i for i in store.issues if i["status"] == "VERIFIED" and not i.get("knowhow")]
    lines += ["", "## Knowhow", ""] + ([f"- {i['id']} matched {i['knowhow']} (record it: `knowhow seen --id {i['knowhow']} --build <book>`)" for i in linked] or ["- no defect linked to a knowhow entry"])
    lines += ["", "Fixed defects without a knowhow entry (add the general ones with `knowhow add`; skip what is specific to this book):", ""] + ([f"- {i['id']} ({i['type']}): {i['description']}; cause: {i['cause'] or '-'}" for i in candidates] or ["- none"])
    if progress:
        lines += ["", "## Progress against the PDF (V0 to V1)", ""]
        for page, result in progress.items():
            if not result.get("comparable"):
                lines.append(f"- page {page}: not comparable ({result.get('reason')})")
                continue
            lines.append(f"- page {page}: different pixels {result['diff_ratio_before']} to {result['diff_ratio_after']}; improved {len(result['improved'])}, unchanged {len(result['unchanged'])}, worse {len(result['worse'])}, new regions {len(result['new_regions'])}" + ("  **regression**" if result["regression"] else ""))
    lines += ["", "## Codex", ""]
    if codex is None:
        lines.append("- no handoff in this run")
    else:
        info = codex["info"]
        lines.append(f"- CLI: {'available, ' + (info.executable or '') if info.available else 'NOT available: ' + info.reason}")
        lines += [f"- prompt: {_link(path)}" for path in codex["prompts"]]
        lines.append(f"- executed: {'yes, see codex-results/execution.md' if codex['executed'] else 'NO (prompts kept, issues stay CODEX_READY)'}")
    lines += ["", "## Geometry and zoom verify", ""]
    lines += [f"- {key}: {value}" for key, value in (verify or {}).items()] or ["- not run in this report"]
    lines += ["", "## Not verified", ""] + ([f"- {item}" for item in unverified or []] or ["- nothing declared"])
    path = output / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
