"""Harness of a PDF-to-ebook build: one state file, page statuses that only move through checks, and gates that a machine evaluates.

The agent never writes "PASS" by hand. A page becomes VERIFIED only through `EbookState.set_page`, which re-reads the evidence in the output
folder (latest scan, failing entries, unresolved P0/P1 issues, a recorded visual check newer than that scan, inventory rows). A gate is a
function that returns the list of problems; an empty list is the only way to pass. State file: `<output>/ebook-state.json` (git-ignored with
the rest of the output folder).
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import date
from pathlib import Path

from . import artwork, consistency, knowhow, reflow, stack, structure, tiles, typography
from .issues import IssueStore
from .qa_run import MARKER, TMP_SUBDIR

STATE_FILE = "ebook-state.json"
OUTPUT_KINDS = ("analysis", "replica-lab", "web-fixed", "web-reflowable", "epub-fixed")
READ_ON_PHONES = ("web-fixed", "web-reflowable")  # web ebooks: every page also needs a reading view that passes `reflow` (phones cannot read the print sheet)
PAGE_STATUSES = ("NOT_STARTED", "IN_PROGRESS", "VERIFIED", "ACCEPTED_LIMITATION", "BLOCKED")
RESOLVED_PAGE = ("VERIFIED", "ACCEPTED_LIMITATION")
PAGE_TRANSITIONS = {
    "NOT_STARTED": {"IN_PROGRESS", "BLOCKED"},
    "IN_PROGRESS": {"VERIFIED", "ACCEPTED_LIMITATION", "BLOCKED"},
    "VERIFIED": {"IN_PROGRESS"},  # a regression reopens the page
    "ACCEPTED_LIMITATION": {"IN_PROGRESS"},
    "BLOCKED": {"IN_PROGRESS"},
}
GATES = ("scope", "inventory", "pilot", "book", "delivery")
NEEDS_SCAN_NOTE = "every entry within tolerance"
INVENTORY_ROW = re.compile(r"^\|\s*(OBJ-\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]+?)\s*\|\s*$")


class StateError(ValueError):
    pass


def parse_pages(spec: str) -> list[int]:
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            first, last = part.split("-")
            pages.extend(range(int(first), int(last) + 1))
        elif part:
            pages.append(int(part))
    return sorted(set(pages))


def page_dir(output: Path, page: int) -> Path:
    return output / "pages" / f"page-{page:03d}"


class EbookState:
    def __init__(self, output: str | Path):
        self.output = Path(output)
        self.path = self.output / STATE_FILE
        self.data: dict = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    # -- persistence ----
    @property
    def exists(self) -> bool:
        return bool(self.data)

    def save(self) -> None:
        self.output.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def require(self) -> None:
        if not self.exists:
            raise StateError(f"no {STATE_FILE} in {self.output}: run `state init` first")

    # -- scope ----
    def init(self, *, kind: str, pages: list[int], pilot: list[int], max_failed_rounds: int = 3) -> None:
        if self.exists:
            raise StateError("state already exists; change it with `state page`, never re-init (it would drop the page history)")
        if kind not in OUTPUT_KINDS:
            raise StateError(f"output kind must be one of {OUTPUT_KINDS}, got {kind!r}")
        if not pages:
            raise StateError("the pages in scope are required")
        stray = [page for page in pilot if page not in pages]
        if stray:
            raise StateError(f"pilot pages {stray} are not in scope")
        if kind not in ("analysis",) and not pilot:
            raise StateError("a build needs pilot pages (one of each layout type and special object) approved before the rest of the book")
        self.data = {
            "scope": {"output_kind": kind, "pages": pages, "pilot_pages": pilot, "max_failed_rounds": max_failed_rounds, "created": date.today().isoformat()},
            "pages": {str(page): {"status": "NOT_STARTED", "reason": "", "viewed_ts": None, "viewed_note": "", "tiles_viewed_ts": None, "tiles_viewed_note": "", "history": []} for page in pages},
            "gates": {},
            "blocked": None,
        }

    @property
    def scope(self) -> dict:
        self.require()
        return self.data["scope"]

    @property
    def pages(self) -> dict:
        self.require()
        return self.data["pages"]

    def entry(self, page: int) -> dict:
        try:
            return self.pages[str(page)]
        except KeyError:
            raise StateError(f"page {page} is not in scope {self.scope['pages']}") from None

    def set_module(self, path: str, book: str, mapping: dict | None = None) -> None:
        """Where the ebook module lives (core + books/<id>, references/14-module-layout.md), which book this build is, and how the top folders map
        onto the host's names."""
        self.require()
        if not path.strip() or not book.strip():
            raise StateError("module needs --path (the ebook module folder) and --book (this book's id under books/)")
        self.data["scope"]["module"] = {"path": path, "book": book, "map": mapping or {}}

    def _structure_problems(self, root: Path) -> list[str]:
        module = self.scope.get("module")
        if not module:
            return ["no module declared (`state module --path <module folder> [--map …]`): the ebook's React code follows references/14-module-layout.md"]
        path = Path(module["path"])
        path = path if path.is_absolute() else root / path
        problems = [f"structure: {item}" for item in structure.check(path, module.get("map"))]
        problems += [f"knowhow {f['id']}: {f['file']}:{f['line']}: {f['message']}" for f in knowhow.scan(path) if f["severity"] == "ERROR"]
        problems += self._consistency_problems()
        books = path / {**structure.DEFAULT_MAP, **(module.get("map") or {})}["books"]
        if not (books / module.get("book", "")).is_dir():
            problems.append(f"structure: this build's book {module.get('book')!r} has no folder {books.name}/{module.get('book')}/ in the module")
        return problems

    def _consistency_problems(self) -> list[str]:
        """Every kit primitive renders the same on every page (`consistency` on the lab), measured after the latest scan of the book."""
        result = consistency.read_result(self.output)
        if result is None:
            return ["no kit consistency result (run `consistency --url <lab with the book's pages>`): one pattern must render the same on every page"]
        scans = [p.stat().st_mtime for p in self.output.glob("pages/page-*/scan-*.md")]
        problems = []
        if scans and result["created"] < max(scans):
            problems.append("kit consistency result is older than the latest scan: run `consistency` again")
        if result["verdict"] == "ERROR":
            problems.append("kit consistency ERROR: " + (result["problems"][0]["text"] if result["problems"] else "no primitive measured"))
        return problems

    def block(self, reason: str) -> None:
        self.require()
        if not reason.strip():
            raise StateError("a block needs a reason")
        self.data["blocked"] = {"reason": reason, "date": date.today().isoformat()}

    def unblock(self) -> None:
        self.require()
        self.data["blocked"] = None

    # -- pages ----
    def record_view(self, page: int, note: str, kind: str = "qa", tile_notes: dict[str, str] | None = None) -> None:
        """The agent states that it looked at pictures. kind `inventory`: every PDF tile of the page (phase 2A). kind `qa`: the PDF | rebuilt tiles and the crops
        of the latest scan (phase 10). Each record counts only for tiles/scans made before it, and needs one observation per non-blank tile (`tile_notes`:
        id -> what is on it, smallest parts first; "nothing small" is a valid answer, a missing tile is not)."""
        if kind not in ("qa", "inventory"):
            raise StateError("view kind must be qa or inventory")
        if not note.strip():
            raise StateError("say what you looked at and what you saw, including the smallest parts you found (a note is required)")
        entry = self.entry(page)
        mode = "pdf" if kind == "inventory" else "pair"
        manifest = tiles.read_manifest(self.output, page, mode)
        if manifest is None:
            raise StateError(f"no {mode} tiles for page {page}: run `tiles --mode {mode}` first, then look at them")
        wanted = [tile["id"] for tile in manifest["tiles"] if not tile["blank"]]
        given = {key: str(value).strip() for key, value in (tile_notes or {}).items()}
        unknown = sorted(set(given) - set(wanted))
        missing = [tile_id for tile_id in wanted if len(given.get(tile_id, "")) < 3]
        if unknown:
            raise StateError(f"tiles not in the {mode} manifest of page {page}: {', '.join(unknown)}")
        if missing:
            raise StateError(f"page {page}: one observation per tile is required; missing or empty for {len(missing)} of {len(wanted)} tile(s): {', '.join(missing[:12])}{' ...' if len(missing) > 12 else ''} (give --tiles-file notes.json)")
        if kind == "inventory":
            entry["tiles_viewed_ts"], entry["tiles_viewed_note"], entry["inventory_tile_notes"] = time.time(), note, given
            return
        entry["viewed_ts"], entry["viewed_note"], entry["qa_tile_notes"] = time.time(), note, given

    def set_page(self, page: int, status: str, *, note: str, reason: str = "", inventory: str | Path | None = None) -> dict:
        entry = self.entry(page)
        if status not in PAGE_STATUSES:
            raise StateError(f"unknown page status {status!r}")
        current = entry["status"]
        if status != current and status not in PAGE_TRANSITIONS[current]:
            raise StateError(f"page {page}: {current} -> {status} is not allowed (allowed: {sorted(PAGE_TRANSITIONS[current])})")
        if not note.strip():
            raise StateError(f"page {page}: a status change needs a note")
        if status in ("ACCEPTED_LIMITATION", "BLOCKED") and not reason.strip():
            raise StateError(f"page {page}: {status} needs a reason")
        if current == "NOT_STARTED" and status == "IN_PROGRESS":
            problems = self._start_problems(page)
            if problems:
                raise StateError(f"page {page} cannot start: " + "; ".join(problems))
        if status == "VERIFIED":
            problems = self.page_problems(page, inventory)
            if problems:
                raise StateError(f"page {page} cannot be VERIFIED: " + "; ".join(problems))
        if status == "ACCEPTED_LIMITATION":
            blockers = self._open_blockers(page)
            if blockers:
                raise StateError(f"page {page} has unresolved P0/P1 ({', '.join(blockers)}); a limitation cannot cover them")
        entry.update(status=status, reason=reason)
        entry["history"].append({"date": date.today().isoformat(), "status": status, "note": note})
        return entry

    def _start_problems(self, page: int) -> list[str]:
        scope, gates = self.scope, self.data["gates"]
        if scope["output_kind"] == "analysis":
            return ["an analysis-only scope builds no page"]
        problems = []
        if not gates.get("scope", {}).get("passed"):
            problems.append(f"gate scope has not passed (output kind, pages, and a supported UI stack: {stack.SUPPORTED})")
        if not gates.get("inventory", {}).get("passed"):
            problems.append("gate inventory has not passed (INVENTORY_COMPLETE first)")
        if page not in scope["pilot_pages"] and not gates.get("pilot", {}).get("passed"):
            problems.append(f"gate pilot has not passed: only pilot pages {scope['pilot_pages']} may start")
        if not (page_dir(self.output, page) / typography.SPEC_FILE).exists():
            problems.append("no typography spec (run `typography --spec-only`): size, weight, family, indents and line pitch are determined before building")
        return problems

    # -- evidence ----
    def issue_store(self) -> IssueStore:
        return IssueStore(self.output / "issues.json")

    def _open_blockers(self, page: int) -> list[str]:
        return [f"{i['id']} {i['severity']} {i['status']}" for i in self.issue_store().unresolved(page) if i["severity"] in ("P0", "P1")]

    def page_problems(self, page: int, inventory: str | Path | None = None) -> list[str]:
        """Everything that stops this page from being VERIFIED, read from files. Empty list = it may be."""
        problems: list[str] = []
        folder = page_dir(self.output, page)
        scans = sorted(folder.glob("scan-*.md"), key=lambda path: path.stat().st_mtime)
        if not scans:
            return [f"no scan in {folder} (run visual-compare with --verify-config)"]
        scan = scans[-1]
        text = scan.read_text(encoding="utf-8")
        if "- status: **size_mismatch**" in text:
            problems.append(f"{scan.name}: size_mismatch, nothing was compared")
        failing = self._failing_entries(text)
        if failing:
            problems.append(f"{scan.name}: {len(failing)} failing geometry/zoom/text-layout entr{'y' if len(failing) == 1 else 'ies'} (first: {failing[0][:80]})")
        if NEEDS_SCAN_NOTE not in text:
            problems.append(f"{scan.name}: no passing verify run in the scan (run it with --verify-config; the page needs an entry in verify.json)")
        if not list(folder.glob("overlay-*.png")) and not list(folder.glob("heatmap-*.png")):
            problems.append(f"no comparison image in {folder}")
        problems += self._typography_problems(page, scan.stat().st_mtime)
        problems += artwork.page_problems(self.output, page)
        if self.scope["output_kind"] in READ_ON_PHONES:
            problems += self._reflow_problems(page, scan.stat().st_mtime)
        blockers = self._open_blockers(page)
        if blockers:
            problems.append("unresolved P0/P1: " + ", ".join(blockers))
        pair = tiles.read_manifest(self.output, page, "pair")
        tile_problems = tiles.manifest_problems(pair, "pair", f"page {page}")
        problems += tile_problems
        if pair and not tile_problems and pair["created"] < scan.stat().st_mtime:
            problems.append(f"pair tiles are older than the latest scan ({scan.name}): run `tiles --mode pair` again, the rebuilt page changed")
        viewed = self.entry(page).get("viewed_ts")
        needed = max(scan.stat().st_mtime, pair["created"] if pair else 0)
        if not viewed or viewed < needed:
            problems.append(f"no `state view` recorded after the latest scan ({scan.name}) and its pair tiles: look at every tile and the crops, then record it")
        if inventory:
            rows = [row for row in inventory_rows(inventory) if row["page"] == str(page) and row["status"] not in ("VERIFIED",) and not row["status"].startswith("EXCLUDED")]
            if rows:
                problems.append("inventory rows not VERIFIED/EXCLUDED: " + ", ".join(f"{row['id']} ({row['status']})" for row in rows))
        return problems

    def _reflow_problems(self, page: int, scan_mtime: float) -> list[str]:
        """A web ebook page must be readable on a phone: the reading view passes `reflow` (no ERROR), measured on the current page."""
        result = reflow.read_result(page_dir(self.output, page))
        if result is None:
            return ["no reading-view result (run `reflow --url <reading view> --fixed-url <print view>`): web ebooks must be readable on phones (references/12-reflow.md)"]
        problems = []
        if result["created"] < scan_mtime:
            problems.append("reading-view result is older than the latest scan: run `reflow` again on the current page")
        if self.scope["output_kind"] == "web-fixed" and not result.get("auto_checked"):
            problems.append("desktop and mobile are both required: run `reflow` with --auto-url (reading view at 360 px, print sheet at 1280 and 1920 px)")
        if result["verdict"] == "ERROR":
            first = next(p for p in result["problems"] if p["level"] == "ERROR")
            problems.append(f"reading view ERROR at {first['width']} px: {first['text']} (see reflow.md)")
        return problems

    def _typography_problems(self, page: int, scan_mtime: float) -> list[str]:
        """Typography must be confirmed on the current rebuilt page: no ERROR (any attribute of any style under 92 %). WARNING (under 95 %) is allowed but listed."""
        result = typography.read_result(page_dir(self.output, page))
        if result is None:
            return ["no typography result (run `typography --url`; size, weight, family, indent and line spacing are scored per style)"]
        problems = []
        if result["zoom"] < typography.MIN_ZOOM:
            problems.append(f"typography was measured at {result['zoom']} px/pt, under the minimum {typography.MIN_ZOOM}")
        if result["created"] < scan_mtime:
            problems.append("typography result is older than the latest scan: run `typography --url` again on the current page")
        if result.get("empty"):
            problems.append("typography scored no line (regions or ink colours wrong?)")
        elif result["verdict"] == "ERROR":
            worst = result["worst"]
            problems.append(f"typography ERROR: {worst['attribute']} of style {worst['style']} at {worst['score']:.1%} (under 92 %); see typography.md")
        return problems

    @staticmethod
    def _failing_entries(scan_text: str) -> list[str]:
        marker = "## Failing geometry / zoom / text-layout entries"
        if marker not in scan_text:
            return []
        failing = []
        for line in scan_text.split(marker, 1)[1].splitlines()[1:]:
            if not line.startswith("- "):
                continue
            if line.startswith("- none") or line.startswith("- verify ran") or line.startswith("- verify config has no entry"):
                continue
            failing.append(line[2:])
        return failing

    # -- gates ----
    def run_gate(self, gate: str, *, inventory: str | Path | None = None, root: str | Path = ".", build_cmd: str | None = None) -> list[str]:
        """Evaluate one gate now and record the result. Returns the problems (empty = passed)."""
        self.require()
        if gate not in GATES:
            raise StateError(f"gate must be one of {GATES}")
        problems = getattr(self, f"_gate_{gate}")(inventory=inventory, root=Path(root), build_cmd=build_cmd)
        self.data["gates"][gate] = {"passed": not problems, "date": date.today().isoformat(), "problems": problems}
        return problems

    def _gate_scope(self, *, root: Path, **_: object) -> list[str]:
        scope = self.scope
        problems = []
        if scope["output_kind"] not in OUTPUT_KINDS:
            problems.append("output kind is not chosen")
        if not scope["pages"]:
            problems.append("no pages in scope")
        if scope["output_kind"] != "analysis":  # analysis builds nothing; every build follows the stack guidance (references/13-react-shadcn-tailwind.md)
            found = stack.detect(root)
            scope["stack"] = found
            if not found["supported"]:
                problems.append(f"UI stack not supported yet (supported: {stack.SUPPORTED}; other stacks come later): " + "; ".join(found["reasons"]))
        return problems

    def _gate_inventory(self, *, inventory: str | Path | None, **_: object) -> list[str]:
        if not inventory:
            return ["give --inventory <object-inventory.md>"]
        path = Path(inventory)
        if not path.is_file():
            return [f"{path} does not exist"]
        text = path.read_text(encoding="utf-8")
        problems = []
        if "INVENTORY_COMPLETE" not in text:
            problems.append("the marker INVENTORY_COMPLETE is not in the file (you have not looked at every page yet)")
        rows = inventory_rows(path)
        if not rows:
            problems.append("no OBJ rows found (table: | ID | Page | Object | Region | Approach | Status |)")
        listed = {row["page"] for row in rows}
        missing = [page for page in self.scope["pages"] if str(page) not in listed]
        if missing:
            problems.append(f"no inventory row for pages {missing} (a page with no object still needs a row that says so)")
        for page in self.scope["pages"]:  # the detail pass: small parts are only found on tiles rendered at >= 6 px/pt
            manifest = tiles.read_manifest(self.output, page, "pdf")
            found = tiles.manifest_problems(manifest, "pdf", f"page {page}")
            problems += found
            seen = self.entry(page).get("tiles_viewed_ts")
            if manifest and not found and (not seen or seen < manifest["created"]):
                problems.append(f"page {page}: no `state view --kind inventory` after its PDF tiles (look at every tile; list small parts such as numbered markers, arrowheads, dotted guides as their own rows)")
        return problems

    def _gate_pilot(self, *, inventory: str | Path | None, root: Path, **_: object) -> list[str]:
        if self.scope["output_kind"] == "analysis":
            return ["an analysis-only scope has no pilot"]
        problems = self._structure_problems(root)
        for page in self.scope["pilot_pages"]:
            status = self.entry(page)["status"]
            if status not in RESOLVED_PAGE:
                problems.append(f"pilot page {page} is {status}")
                continue
            if status == "VERIFIED":
                problems += [f"pilot page {page}: {item}" for item in self.page_problems(page, inventory)]
        return problems

    def _gate_book(self, *, inventory: str | Path | None, root: Path = Path("."), **_: object) -> list[str]:
        if self.scope["output_kind"] == "analysis":
            return ["an analysis-only scope has no book gate; it ends at gate inventory"]
        problems = self._structure_problems(root)
        for page in self.scope["pages"]:
            entry = self.entry(page)
            if entry["status"] not in RESOLVED_PAGE:
                problems.append(f"page {page} is {entry['status']}")
            elif entry["status"] == "VERIFIED":  # re-read the evidence: a later change may have broken a page that was fine
                problems += [f"page {page}: {item}" for item in self.page_problems(page, inventory)]
        problems += [f"{i['id']} (page {i['page']}, {i['severity']}, {i['status']})" for i in self.issue_store().unresolved() if i["severity"] in ("P0", "P1")]
        return problems

    def _gate_delivery(self, *, root: Path, build_cmd: str | None, inventory: str | Path | None, **_: object) -> list[str]:
        problems = [f"book: {item}" for item in self._gate_book(inventory=inventory, root=root)] if self.scope["output_kind"] != "analysis" else ["an analysis-only scope has nothing to deliver"]
        base = root / TMP_SUBDIR
        left = [path.name for path in base.glob("*") if (path / MARKER).exists()] if base.is_dir() else []
        if left:
            problems.append(f"qa-finish has not been run, temp folders left: {', '.join(left)}")
        report = self.output / "report.md"
        if not report.exists():
            problems.append("no report.md (run qa-report)")
        elif "NOT complete" in report.read_text(encoding="utf-8"):
            problems.append("report.md says NOT complete (regenerate it after the fixes)")
        problems += copyright_problems(root, self.output)
        if not build_cmd:
            problems.append("build not verified: give --build-cmd (the project's build command)")
        else:
            result = subprocess.run(build_cmd, shell=True, cwd=root, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                tail = (result.stdout + result.stderr).strip().splitlines()[-3:]
                problems.append(f"build `{build_cmd}` failed (exit {result.returncode}): " + " | ".join(tail))
        return problems

    # -- summaries ----
    def coverage_lines(self) -> list[str]:
        self.require()
        lines = ["| Page | Status | Pilot | Typography | Reason / last note |", "|---|---|---|---|---|"]
        for page in self.scope["pages"]:
            entry = self.entry(page)
            last = entry["reason"] or (entry["history"][-1]["note"] if entry["history"] else "")
            result = typography.read_result(page_dir(self.output, page))
            typo = "-" if result is None else f"{result['verdict']} ({result['worst']['attribute']} {result['worst']['score']:.1%})"
            lines.append(f"| {page} | {entry['status']} | {'yes' if page in self.scope['pilot_pages'] else ''} | {typo} | {last} |")
        counts = {status: sum(1 for p in self.scope["pages"] if self.entry(p)["status"] == status) for status in PAGE_STATUSES}
        lines += ["", "Counts: " + ", ".join(f"{status} {n}" for status, n in counts.items()) + f" of {len(self.scope['pages'])} pages"]
        gates = self.data["gates"]
        lines += ["", "Gates: " + ", ".join(f"{gate} {'PASSED' if gates.get(gate, {}).get('passed') else ('FAILED' if gate in gates else 'not run')}" for gate in GATES)]
        return lines

    def stop_problems(self) -> list[str]:
        """What must be settled before this session may end (used by the Stop hook). Empty when the state is blocked on purpose."""
        if not self.exists or self.data.get("blocked"):
            return []
        problems = []
        for page in self.scope["pages"]:
            status = self.entry(page)["status"]
            if status == "IN_PROGRESS":
                problems.append(f"page {page} is IN_PROGRESS: finish it (VERIFIED), accept a limitation with a reason, or block it")
            elif status == "VERIFIED":
                problems += [f"page {page} was VERIFIED but no longer passes: {item}" for item in self.page_problems(page)]
        problems += [f"{i['id']} (page {i['page']}, {i['severity']}, {i['status']}) is unresolved" for i in self.issue_store().unresolved() if i["severity"] in ("P0", "P1")]
        return problems


def inventory_rows(path: str | Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = INVENTORY_ROW.match(line)
        if match:
            rows.append({"id": match.group(1), "page": match.group(2), "object": match.group(3), "region": match.group(4), "approach": match.group(5), "status": match.group(6).strip("* ")})
    return rows


def copyright_problems(root: Path, output: Path) -> list[str]:
    """The PDF, its page images and the QA output hold the printed book: none of it may be tracked or staged."""
    def git(*args: str) -> list[str]:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
        return result.stdout.split("\n") if result.returncode == 0 else []

    problems = [f"tracked PDF: {path}" for path in git("ls-files", "--", "*.pdf") if path]
    try:
        relative = output.resolve().relative_to(root.resolve())
    except ValueError:
        return problems
    problems += [f"QA output tracked or staged: {path}" for path in git("ls-files", "--", str(relative))[:5] if path]
    return problems
