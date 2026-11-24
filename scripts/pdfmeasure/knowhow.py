"""Knowhow: the register of defects that come back from build to build (a hairline drawn 1 px thick, em spacing on the wrong element…), each with
its symptom, cause, fix, how to check it and, where a source pattern gives it away, a detector. It lives in the skill
(references/knowhow.json, rendered to references/knowhow.md) so every later build starts from it.

Use during a build: read the entries of the tags you work on; when triaging a defect, search the register and link the issue to the entry it
matches (`issue add --knowhow KH-001`); when a fixed defect is general (not specific to one book), add it; when an entry happens again, record it
with `seen`. `scan` runs the detectors on the module; gates `pilot` and `book` refuse ERROR findings.
"""
from __future__ import annotations

import fnmatch
import json
import re
import time
from pathlib import Path

REGISTER = Path(__file__).resolve().parent.parent.parent / "references" / "knowhow.json"
RENDERED = REGISTER.with_suffix(".md")
TAGS = ("lines", "css", "svg", "text", "fonts", "layout", "colour", "reading", "artwork", "measuring", "react", "tailwind")
SEVERITIES = ("ERROR", "WARNING")
REQUIRED = ("title", "tags", "symptom", "cause", "fix", "check")
ID = re.compile(r"^KH-\d{3}$")


class KnowhowError(ValueError):
    pass


def load(path: Path = REGISTER) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"entries": []}


def save(data: dict, path: Path = REGISTER) -> None:
    data["entries"].sort(key=lambda entry: entry["id"])
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    path.with_suffix(".md").write_text(render(data), encoding="utf-8")


def validate(entry: dict) -> list[str]:
    problems = [f"{key} is required" for key in REQUIRED if not entry.get(key)]
    unknown = [tag for tag in entry.get("tags", []) if tag not in TAGS]
    if unknown:
        problems.append(f"unknown tags {unknown} (use {', '.join(TAGS)})")
    for detector in entry.get("detect", []):
        if detector.get("severity") not in SEVERITIES:
            problems.append(f"detector severity must be one of {SEVERITIES}")
        try:
            re.compile(detector.get("pattern", ""))
        except re.error as error:
            problems.append(f"detector pattern does not compile: {error}")
        if not detector.get("glob") or not detector.get("message"):
            problems.append("a detector needs glob, pattern, severity and message")
    return problems


def add(data: dict, entry: dict) -> dict:
    """A new entry with the next id. Refused when it repeats the title of an existing one (record `seen` there instead)."""
    problems = validate(entry)
    if problems:
        raise KnowhowError("; ".join(problems))
    title = " ".join(entry["title"].lower().split())
    for existing in data["entries"]:
        if " ".join(existing["title"].lower().split()) == title:
            raise KnowhowError(f"{existing['id']} already covers {entry['title']!r}: record it with `knowhow seen {existing['id']}`")
    number = max((int(e["id"][3:]) for e in data["entries"]), default=0) + 1
    created = {"id": f"KH-{number:03d}", **{k: v for k, v in entry.items() if k != "id"}, "seen": entry.get("seen", []), "added": time.strftime("%Y-%m-%d")}
    data["entries"].append(created)
    return created


def update(data: dict, entry_id: str, fields: dict, reason: str) -> dict:
    """Correct an entry when new evidence shows it wrong or incomplete; the reason (what was measured) is kept in its history."""
    if not reason.strip():
        raise KnowhowError("update needs --reason (the evidence: what was measured, where)")
    entry = get(data, entry_id)
    merged = {**entry, **{k: v for k, v in fields.items() if k not in ("id", "seen", "added", "history")}}
    problems = validate(merged)
    if problems:
        raise KnowhowError("; ".join(problems))
    entry.update(merged)
    entry.setdefault("history", []).append({"date": time.strftime("%Y-%m-%d"), "reason": reason, "fields": sorted(k for k in fields if k not in ("id", "seen", "added", "history"))})
    return entry


def get(data: dict, entry_id: str) -> dict:
    for entry in data["entries"]:
        if entry["id"] == entry_id:
            return entry
    raise KnowhowError(f"unknown knowhow {entry_id}")


def seen(data: dict, entry_id: str, build: str, note: str = "") -> dict:
    if not build.strip():
        raise KnowhowError("seen needs --build (the book or build where it happened)")
    entry = get(data, entry_id)
    entry.setdefault("seen", []).append({"build": build, "date": time.strftime("%Y-%m-%d"), "note": note})
    return entry


def search(data: dict, words: str, tags: list[str] | None = None) -> list[dict]:
    """Entries whose text holds every word (any order), optionally limited to tags; most seen first."""
    terms = [word.lower() for word in words.split() if word]
    found = []
    for entry in data["entries"]:
        if tags and not set(tags) & set(entry["tags"]):
            continue
        text = " ".join(str(entry.get(key, "")) for key in ("title", "symptom", "cause", "fix", "check")).lower() + " " + " ".join(entry["tags"])
        if all(term in text for term in terms):
            found.append(entry)
    return sorted(found, key=lambda entry: -len(entry.get("seen", [])))


def scan(module: str | Path, data: dict | None = None) -> list[dict]:
    """Run every detector on the module's files. Returns findings {id, severity, file, line, message}."""
    data = data or load()
    root = Path(module)
    findings = []
    files = [path for path in sorted(root.rglob("*")) if path.is_file() and path.suffix in (".css", ".ts", ".tsx")]
    for entry in data["entries"]:
        for detector in entry.get("detect", []):
            pattern = re.compile(detector["pattern"], re.IGNORECASE)
            for path in files:
                relative = str(path.relative_to(root))
                if not fnmatch.fnmatch(relative, detector["glob"]) and not fnmatch.fnmatch(path.name, detector["glob"]):
                    continue
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                    if pattern.search(line):
                        findings.append({"id": entry["id"], "severity": detector["severity"], "file": relative, "line": number, "message": detector["message"]})
    return findings


def render(data: dict) -> str:
    lines = ["# Knowhow: defects that come back", "", "GENERATED from `knowhow.json` by `pdfmeasure knowhow`. Do not edit by hand; add or update entries with the command.", "",
             "| ID | Title | Tags | Seen | Detector |", "|---|---|---|---|---|"]
    for entry in data["entries"]:
        detector = ", ".join(d["severity"] for d in entry.get("detect", [])) or "-"
        lines.append(f"| {entry['id']} | {entry['title']} | {', '.join(entry['tags'])} | {len(entry.get('seen', []))} | {detector} |")
    for entry in data["entries"]:
        lines += ["", f"## {entry['id']} · {entry['title']}", "", f"- **Symptom:** {entry['symptom']}", f"- **Cause:** {entry['cause']}", f"- **Fix:** {entry['fix']}", f"- **Check:** {entry['check']}"]
        if entry.get("detect"):
            lines.append("- **Detector:** " + "; ".join(f"{d['severity']} in `{d['glob']}`: {d['message']}" for d in entry["detect"]))
        for item in entry.get("history", []):
            lines.append(f"- **Corrected {item['date']}:** {item['reason']}")
        if entry.get("seen"):
            lines.append("- **Seen:** " + ", ".join(f"{s['build']} ({s['date']})" for s in entry["seen"]))
    return "\n".join(lines) + "\n"


def command_knowhow(args) -> int:
    data = load()
    try:
        if args.action == "list":
            found = search(data, "", args.tag)
            print("\n".join(f"{e['id']}  [{', '.join(e['tags'])}]  {e['title']}  (seen {len(e.get('seen', []))})" for e in found) or "no entry")
        elif args.action == "search":
            found = search(data, args.words or "", args.tag)
            print("\n".join(f"{e['id']}  {e['title']}\n    fix: {e['fix']}" for e in found) or "no entry matches: if the fixed defect is general, add it (`knowhow add`)")
        elif args.action == "show":
            print(render({"entries": [get(data, args.id)]}).split("\n", 6)[-1])
        elif args.action == "add":
            entry = json.loads(Path(args.file).read_text(encoding="utf-8"))
            created = add(data, entry)
            save(data)
            print(f"knowhow: {created['id']} added ({created['title']}); references/knowhow.md regenerated. Commit both with the build.")
        elif args.action == "update":
            entry = update(data, args.id, json.loads(Path(args.file).read_text(encoding="utf-8")), args.reason or "")
            save(data)
            print(f"knowhow: {entry['id']} updated ({len(entry['history'])} correction(s)); references/knowhow.md regenerated")
        elif args.action == "seen":
            entry = seen(data, args.id, args.build or "", args.note or "")
            save(data)
            print(f"knowhow: {entry['id']} seen {len(entry['seen'])} time(s)")
        elif args.action == "scan":
            findings = scan(args.module, data)
            for f in findings:
                print(f"{f['severity']} {f['id']} {f['file']}:{f['line']}: {f['message']}")
            errors = sum(f["severity"] == "ERROR" for f in findings)
            print(f"knowhow scan: {errors} error(s), {len(findings) - errors} warning(s)")
            return 1 if errors else 0
        elif args.action == "render":
            save(data)
            print(f"knowhow: {RENDERED} regenerated")
    except (KnowhowError, FileNotFoundError, json.JSONDecodeError) as error:
        print(f"knowhow: {error}")
        return 2
    return 0


def register(add_command) -> None:
    cmd = add_command("knowhow", command_knowhow, "register of defects that come back: list | search | show | add | update | seen | scan | render")
    cmd.add_argument("action", choices=["list", "search", "show", "add", "update", "seen", "scan", "render"])
    cmd.add_argument("words", nargs="?", help="search: words of the symptom or cause")
    cmd.add_argument("--tag", action="append", choices=TAGS)
    cmd.add_argument("--id", help="show / seen: KH-nnn")
    cmd.add_argument("--file", help='add: JSON entry {title, tags, symptom, cause, fix, check, detect?: [{glob, pattern, severity, message}]}')
    cmd.add_argument("--build", help="seen: the book or build where it happened")
    cmd.add_argument("--note")
    cmd.add_argument("--reason", help="update: the evidence for the correction")
    cmd.add_argument("--module", help="scan: the ebook module folder")
