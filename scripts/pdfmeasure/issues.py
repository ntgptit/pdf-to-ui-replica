"""Visual defect inventory: issues with stable IDs, a status lifecycle and a history, kept in issues.json (and rendered to issues.md).

The agent decides what is a defect and how severe it is. This module only keeps the record straight: an unresolved defect is never given a
second ID, a status cannot jump to VERIFIED without evidence, and the history survives across runs.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

SEVERITIES = ("P0", "P1", "P2", "P3")
TYPES = ("missing", "content", "structure", "shape", "layout", "scale", "character", "decoration", "spacing", "colour", "stroke", "other")
STATUSES = ("OPEN", "FIXING", "NEEDS_VERIFY", "VERIFIED", "CODEX_READY", "CODEX_RUNNING", "BLOCKED", "ACCEPTED_LIMITATION")
RESOLVED = ("VERIFIED", "ACCEPTED_LIMITATION")
TRANSITIONS = {
    "OPEN": {"FIXING", "CODEX_READY", "BLOCKED", "ACCEPTED_LIMITATION"},
    "FIXING": {"NEEDS_VERIFY", "OPEN", "BLOCKED", "CODEX_READY"},
    "NEEDS_VERIFY": {"VERIFIED", "OPEN", "FIXING", "ACCEPTED_LIMITATION"},
    "CODEX_READY": {"CODEX_RUNNING", "FIXING", "BLOCKED", "ACCEPTED_LIMITATION"},
    "CODEX_RUNNING": {"NEEDS_VERIFY", "CODEX_READY", "BLOCKED"},
    "BLOCKED": {"OPEN", "CODEX_READY", "ACCEPTED_LIMITATION"},
    "ACCEPTED_LIMITATION": {"OPEN"},
    "VERIFIED": {"OPEN"},  # a regression reopens the same issue, it does not create a new one
}
SAME_ISSUE_OVERLAP = 0.3
DEFAULT_MAX_FAILED_ROUNDS = 3  # fixes that did not hold (NEEDS_VERIFY/VERIFIED back to OPEN/FIXING) before the issue must leave the agent's own loop


class IssueError(ValueError):
    pass


def _iou(a: list[float], b: list[float]) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union else 0.0


class IssueStore:
    def __init__(self, path: str | Path, max_failed_rounds: int = DEFAULT_MAX_FAILED_ROUNDS):
        self.path = Path(path)
        self.max_failed_rounds = max_failed_rounds
        self.data = {"next_id": 1, "issues": []}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    # -- persistence ----
    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.path.with_suffix(".md").write_text(self.to_markdown(), encoding="utf-8")

    @property
    def issues(self) -> list[dict]:
        return self.data["issues"]

    def get(self, issue_id: str) -> dict:
        for issue in self.issues:
            if issue["id"] == issue_id:
                return issue
        raise IssueError(f"unknown issue {issue_id}")

    # -- lifecycle ----
    def add(self, *, run: str, page: int, description: str, region: list[float], type: str, severity: str, object_id: str | None = None, evidence: list[str] | None = None, cause: str = "", fix_plan: str = "", knowhow: str = "") -> dict:
        """A new issue, or the existing unresolved one when it is the same defect (same page, object and type, overlapping region): then only its history grows."""
        if severity not in SEVERITIES:
            raise IssueError(f"severity must be one of {SEVERITIES}, got {severity!r}")
        if type not in TYPES:
            raise IssueError(f"type must be one of {TYPES}, got {type!r}")
        if len(region) != 4:
            raise IssueError("region must be [x, top, width, height] in points")
        for issue in self.issues:
            if issue["status"] in RESOLVED:
                continue
            if issue["page"] == page and issue["object_id"] == object_id and issue["type"] == type and _iou(issue["region"], region) >= SAME_ISSUE_OVERLAP:
                self._note(issue, run, issue["status"], "seen again: " + description)
                for item in evidence or []:
                    if item not in issue["evidence"]:
                        issue["evidence"].append(item)
                return issue
        issue = {
            "id": f"ISS-{self.data['next_id']:03d}",
            "page": page,
            "object_id": object_id,
            "type": type,
            "severity": severity,
            "description": description,
            "region": region,
            "status": "OPEN",
            "evidence": list(evidence or []),
            "cause": cause,
            "fix_plan": fix_plan,
            "knowhow": knowhow,  # KH-nnn of the register entry this defect matches (references/knowhow.json)
            "codex_prompt": None,
            "history": [],
        }
        self.data["next_id"] += 1
        self._note(issue, run, "OPEN", "found: " + description)
        self.issues.append(issue)
        return issue

    def set_status(self, issue_id: str, status: str, *, run: str, note: str, evidence: list[str] | None = None, reset_rounds: str = "") -> dict:
        """Move an issue. Besides the lifecycle: a fix that did not hold counts as a failed round; at the cap the issue is forced out of the agent's loop
        (CODEX_READY when it has a cause to hand over, else BLOCKED) and cannot go back to FIXING/OPEN without `reset_rounds` (a written reason)."""
        issue = self.get(issue_id)
        if status not in STATUSES:
            raise IssueError(f"unknown status {status!r}")
        if status != issue["status"] and status not in TRANSITIONS[issue["status"]]:
            raise IssueError(f"{issue_id}: {issue['status']} -> {status} is not allowed (allowed: {sorted(TRANSITIONS[issue['status']])})")
        if not note.strip():
            raise IssueError(f"{issue_id}: a status change needs a note")
        if status == "VERIFIED" and not (evidence or issue["evidence"]):
            raise IssueError(f"{issue_id}: VERIFIED needs image evidence of the fix")
        rounds = issue.get("failed_rounds", 0)
        previous = issue["status"]
        if reset_rounds.strip():
            issue["failed_rounds"] = rounds = 0
            self._note(issue, run, previous, f"failed-round counter reset: {reset_rounds}")
        if rounds >= self.max_failed_rounds and status in ("FIXING", "OPEN") and previous in ("OPEN", "CODEX_READY", "BLOCKED"):
            raise IssueError(f"{issue_id}: {rounds} fixes did not hold (cap {self.max_failed_rounds}); hand it over (codex-prompt), accept it, or restart the count with a written reason (--reset-rounds)")
        for item in evidence or []:
            if item not in issue["evidence"]:
                issue["evidence"].append(item)
        issue["status"] = status
        self._note(issue, run, status, note)
        if previous in ("NEEDS_VERIFY", "VERIFIED") and status in ("OPEN", "FIXING"):
            issue["failed_rounds"] = rounds + 1
            if issue["failed_rounds"] >= self.max_failed_rounds:
                forced = "CODEX_READY" if issue["cause"].strip() else "BLOCKED"
                issue["status"] = forced
                self._note(issue, run, forced, f"no progress: {issue['failed_rounds']} fixes did not hold; out of the agent's own loop ({'hand over with codex-prompt' if forced == 'CODEX_READY' else 'write the cause, then hand over or accept'})")
        return issue

    def update(self, issue_id: str, **fields) -> dict:
        issue = self.get(issue_id)
        for key, value in fields.items():
            if key not in ("severity", "description", "region", "cause", "fix_plan", "codex_prompt", "type", "object_id", "knowhow"):
                raise IssueError(f"cannot update {key}")
            if key == "severity" and value not in SEVERITIES:
                raise IssueError(f"severity must be one of {SEVERITIES}")
            issue[key] = value
        return issue

    def note_run(self, run: str, note: str = "checked") -> None:
        """Every unresolved issue gets a history line for this run, so the record shows it was looked at again."""
        for issue in self.issues:
            if issue["status"] not in RESOLVED and not any(item["run"] == run for item in issue["history"]):
                self._note(issue, run, issue["status"], note)

    @staticmethod
    def _note(issue: dict, run: str, status: str, note: str) -> None:
        issue["history"].append({"run": run, "date": date.today().isoformat(), "status": status, "note": note})

    # -- views ----
    def unresolved(self, page: int | None = None) -> list[dict]:
        return [i for i in self.issues if i["status"] not in RESOLVED and (page is None or i["page"] == page)]

    def counts(self) -> dict:
        table: dict[str, dict[str, int]] = {severity: {status: 0 for status in STATUSES} for severity in SEVERITIES}
        for issue in self.issues:
            table[issue["severity"]][issue["status"]] += 1
        return table

    def page_complete(self, page: int | None = None) -> tuple[bool, list[str]]:
        """A page is complete only when no P0/P1 issue is unresolved. P2/P3 may stay, but they must be listed with their status."""
        blockers = [f"{i['id']} ({i['severity']}, {i['status']})" for i in self.unresolved(page) if i["severity"] in ("P0", "P1")]
        return (not blockers, blockers)

    def to_markdown(self) -> str:
        lines = ["# Visual defect inventory", "", "| ID | Page | Object | Sev | Type | Status | Description |", "|---|---|---|---|---|---|---|"]
        for i in sorted(self.issues, key=lambda item: (item["severity"], item["id"])):
            lines.append(f"| {i['id']} | {i['page']} | {i['object_id'] or '-'} | {i['severity']} | {i['type']} | {i['status']} | {i['description']} |")
        return "\n".join(lines) + "\n"
