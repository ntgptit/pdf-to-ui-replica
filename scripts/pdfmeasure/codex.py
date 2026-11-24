"""Hand hard visual defects to Codex: one self-contained Markdown prompt per defect (or per tightly linked group), then run them if the Codex CLI works.

Rules: hand over only a defect that has a technical cause (or a concrete hypothesis) and a task clear enough to do; take the CLI syntax from its own
`--help`, never from memory; never say Codex ran unless a run really finished; a finished Codex run is not a fixed defect (the agent re-captures and verifies).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED = ("goal", "object_description", "evidence", "cause", "source_files", "approach", "constraints", "acceptance", "commands", "allowed_files")
SECTIONS = (
    ("goal", "1. Technical goal"),
    ("object_description", "2. Object to draw or fix"),
    ("evidence", "3. Evidence (images)"),
    ("measures", "4. Bounding box and measurements"),
    ("cause", "5. Cause analysis"),
    ("source_files", "6. Relevant source code"),
    ("approach", "7. Intended approach (CSS / SVG / React / asset)"),
    ("constraints", "8. Architecture and conventions to keep"),
    ("acceptance", "9. Acceptance criteria"),
    ("commands", "10. Commands to run (build, test, visual compare)"),
    ("allowed_files", "11. Files you may change"),
)


class HandoffError(ValueError):
    pass


def prompt_name(issue: dict, group: list[dict] | None = None) -> str:
    obj = re.sub(r"[^a-z0-9]", "", (issue.get("object_id") or "page").lower())
    number = int(issue["id"].split("-")[1])
    name = f"p{issue['page']:03d}-{obj}-issue{number:03d}"
    return name + ("-group" if group and len(group) > 1 else "")


def _as_text(value) -> str:
    if isinstance(value, (list, tuple)):
        return "\n".join(f"- {item}" for item in value)
    return str(value).strip()


def build_prompt(issues: list[dict], context: dict) -> str:
    """Markdown for one defect, or for a group of issues that depend on each other (all IDs listed). Refuses an incomplete handoff."""
    if not issues:
        raise HandoffError("no issue to hand over")
    for issue in issues:
        if not (issue.get("cause") or "").strip():
            raise HandoffError(f"{issue['id']}: no cause or hypothesis recorded; analyse it before handing it to Codex")
    missing = [key for key in REQUIRED if not _as_text(context.get(key, ""))]
    if missing:
        raise HandoffError(f"the handoff is not self-contained, missing: {', '.join(missing)}")
    ids = ", ".join(issue["id"] for issue in issues)
    lines = [f"# Codex task: {ids}", "", f"Pages: {', '.join(sorted({str(issue['page']) for issue in issues}))}. Severity: {', '.join(sorted({issue['severity'] for issue in issues}))}.", ""]
    for issue in issues:
        lines.append(f"- **{issue['id']}** ({issue['type']}, {issue['severity']}): {issue['description']}  Region [x, top, w, h] pt: {issue['region']}")
    lines.append("")
    for key, title in SECTIONS:
        body = _as_text(context.get(key, "")) or "Not applicable."
        lines += [f"## {title}", "", body, ""]
    lines += ["## Reporting", "", "Say which files you changed and what you ran. Do not mark anything fixed: the requesting agent re-captures the page and verifies it.", ""]
    return "\n".join(lines)


def write_prompt(directory: Path, issues: list[dict], context: dict) -> Path:
    text = build_prompt(issues, context)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (prompt_name(issues[0], issues) + ".md")
    path.write_text(text, encoding="utf-8")
    return path


# ---- the CLI ----------------------------------------------------------------------------------------------------------------------------
@dataclass
class CodexInfo:
    available: bool
    reason: str = ""
    executable: str | None = None
    exec_help: str = ""
    supports_resume: bool = False
    resume_selector: str | None = None  # "--last" or "SESSION_ID", only when the resume help shows it
    takes_prompt_argument: bool = False
    notes: list[str] = field(default_factory=list)


def _run(command: list[str], timeout: int, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=cwd)


def detect(timeout: int = 30) -> CodexInfo:
    """Is `codex` there and does `codex exec` work? Syntax comes from `codex exec --help` and `codex exec resume --help`."""
    executable = shutil.which("codex")
    if not executable:
        return CodexInfo(False, "the `codex` executable is not on PATH")
    try:
        help_run = _run([executable, "exec", "--help"], timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        return CodexInfo(False, f"`codex exec --help` could not run: {error}", executable)
    if help_run.returncode != 0:
        return CodexInfo(False, f"`codex exec --help` exited with {help_run.returncode}", executable, (help_run.stdout + help_run.stderr)[-2000:])
    text = help_run.stdout + help_run.stderr
    info = CodexInfo(True, "", executable, text)
    info.takes_prompt_argument = bool(re.search(r"\[?PROMPT\]?", text))
    if not info.takes_prompt_argument:
        info.available = False
        info.reason = "`codex exec --help` shows no PROMPT argument, so the syntax is not known; run it by hand"
        return info
    if re.search(r"\bresume\b", text):
        try:
            resume_run = _run([executable, "exec", "resume", "--help"], timeout)
        except (OSError, subprocess.TimeoutExpired):
            resume_run = None
        if resume_run is not None and resume_run.returncode == 0:
            resume_text = resume_run.stdout + resume_run.stderr
            if "--last" in resume_text:
                info.supports_resume, info.resume_selector = True, "--last"
            elif "SESSION_ID" in resume_text:
                info.supports_resume, info.resume_selector = True, "SESSION_ID"
    return info


def session_reference(output: str) -> str | None:
    match = re.search(r"session[ _-]?id:?\s*([0-9a-fA-F-]{8,})", output, re.IGNORECASE)
    return match.group(1) if match else None


@dataclass
class RunResult:
    prompts: list[str]
    command: list[str]
    exit_code: int
    session: str | None
    output_tail: str


def run_prompts(prompt_files: list[Path], info: CodexInfo, cwd: Path, timeout: int = 1800, execute=_run) -> tuple[list[RunResult], str]:
    """Run the prompts. With a trustworthy resume, one session handles them in turn; otherwise they are merged into a single run.
    Returns the results and how they were run ("separate resumed runs" | "one merged run")."""
    texts = [path.read_text(encoding="utf-8") for path in prompt_files]
    results: list[RunResult] = []
    if info.supports_resume and len(prompt_files) > 1 and info.resume_selector == "--last":
        mode, session = "separate resumed runs", None
        for index, (path, text) in enumerate(zip(prompt_files, texts)):
            command = [info.executable, "exec", text] if index == 0 else [info.executable, "exec", "resume", "--last", text]
            done = execute(command, timeout, cwd)
            output = (done.stdout or "") + (done.stderr or "")
            session = session or session_reference(output)
            results.append(RunResult([path.name], command[:-1] + ["<prompt>"], done.returncode, session, output[-1500:]))
            if done.returncode != 0:
                break
        return results, mode
    merged = "\n\n---\n\n".join(texts)
    command = [info.executable, "exec", merged]
    done = execute(command, timeout, cwd)
    output = (done.stdout or "") + (done.stderr or "")
    results.append(RunResult([path.name for path in prompt_files], command[:-1] + ["<merged prompts>"], done.returncode, session_reference(output), output[-1500:]))
    return results, "one merged run"


def write_execution(path: Path, info: CodexInfo, prompt_files: list[Path], results: list[RunResult], mode: str | None) -> None:
    """execution.md: what was and was not executed, honestly."""
    lines = ["# Codex execution", ""]
    if not info.available:
        lines += ["**Codex was NOT run.**", "", f"Reason: {info.reason}", "", "The prompts are kept and their issues stay `CODEX_READY`. To run them by hand, open Codex in the repository and give it each file:", ""]
        lines += [f"- `{p}`" for p in prompt_files]
        lines += ["", "With the CLI installed: `codex exec \"$(cat <prompt file>)\"` (check `codex exec --help` for your version). Then re-capture and verify; a finished Codex run does not mean the defect is fixed."]
    else:
        lines += [f"Executable: `{info.executable}`. Mode: {mode}.", ""]
        for result in results:
            lines += [f"## {', '.join(result.prompts)}", "", f"- command: `{' '.join(result.command)}`", f"- exit code: {result.exit_code}", f"- session reference: {result.session or 'none reported'}", "", "```", result.output_tail.strip(), "```", ""]
        lines.append("Not verified: the requesting agent must re-capture the page and verify each issue.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
