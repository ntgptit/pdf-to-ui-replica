"""`init`: put this skill to work in a project with one command. Standard library only, so it runs before the dependencies are installed.

  python3 .claude/skills/pdf-to-ui-replica/scripts/init.py [--project <repo>] [--check]

What it does (every step is idempotent; --check reports without writing):
  1. checks the environment: Python, pdfplumber, numpy, Pillow, pdftoppm, Node, Playwright and its browser; installs the missing libraries, prints the exact install command for the missing tools
  2. registers the Stop hook in <project>/.claude/settings.json (merged: existing hooks and settings stay; nothing is added twice)
  3. adds pdf-to-ui-output/ and .tmp/pdf-to-ui/ to <project>/.gitignore (they hold page images of the book)
  4. reports whether the project's UI stack is supported for builds (React + shadcn/ui + Tailwind CSS v4); analysis works on any project
Missing libraries are installed (pip packages; Playwright and its Chromium inside this skill's scripts/ folder); pass --no-install to skip. Tools of the machine (Python, poppler, Node) are never installed: the report prints the command. Nothing else in the project is touched.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import stack

HOOK_FILE = "ebook-gate-stop.py"
GITIGNORE_LINES = ("pdf-to-ui-output/", ".tmp/pdf-to-ui/")
GITIGNORE_HEADER = "# pdf-to-ui-replica: output and run folders hold page images of the book (never commit them)"
PYTHON_MODULES = (("pdfplumber", "pdfplumber"), ("numpy", "numpy"), ("PIL", "Pillow"))
PIP_SPECS = {"pdfplumber": "pdfplumber>=0.10", "numpy": "numpy>=1.24", "Pillow": "Pillow>=10"}
INSTALL_TIMEOUT = 1200  # seconds: the Chromium download is large
MIN_PYTHON = (3, 10)
MIN_NODE = 18


class InitError(RuntimeError):
    pass


def skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def default_project(skill: Path) -> Path | None:
    """The project the skill is installed in: <project>/.claude/skills/<name>/ (None when it lives elsewhere)."""
    if skill.parent.name == "skills" and skill.parent.parent.name == ".claude":
        return skill.parents[2]
    return None


# ---- 1. environment ----------------------------------------------------------------------------------------------------------------------
def _check(name: str, ok: bool, detail: str, fix: str = "", required: bool = True, needed_for: str = "") -> dict:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix, "required": required, "needed_for": needed_for}


def node_major(output: str) -> int | None:
    match = re.search(r"v?(\d+)\.", output)
    return int(match.group(1)) if match else None


def check_environment(scripts: Path, which=shutil.which, run=subprocess.run, find_spec=importlib.util.find_spec, python=sys.version_info) -> list[dict]:
    """Every tool the skill needs, with the command that installs what is missing. Injected `which`, `run`, `find_spec`, `python` make it testable."""
    checks = []
    ok = tuple(python[:2]) >= MIN_PYTHON
    checks.append(_check("Python", ok, f"{python[0]}.{python[1]}", f"install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer"))
    for module, package in PYTHON_MODULES:
        found = find_spec(module) is not None
        checks.append(_check(f"Python package {package}", found, "found" if found else "missing", f"pip install -r {scripts / 'requirements.txt'}"))
    poppler = which("pdftoppm")
    checks.append(_check("poppler (pdftoppm)", bool(poppler), poppler or "missing", "sudo apt-get install -y poppler-utils   |   brew install poppler"))
    node = which("node")
    version = ""
    if node:
        version = run([node, "--version"], capture_output=True, text=True, check=False).stdout.strip()
    major = node_major(version)
    checks.append(_check("Node", bool(node) and (major or 0) >= MIN_NODE, version or "missing", f"install Node {MIN_NODE} or newer (https://nodejs.org)", required=False, needed_for="measuring the rebuilt page (verify, zoom, reflow, consistency)"))
    playwright_ok, browser_ok, browser_detail = False, False, "needs Playwright first"
    if node:
        probe = run([node, "-e", "console.log(require('playwright').chromium.executablePath())"], capture_output=True, text=True, check=False, cwd=scripts)
        playwright_ok = probe.returncode == 0
        if playwright_ok:
            executable = probe.stdout.strip().splitlines()[-1] if probe.stdout.strip() else ""
            browser_ok = bool(executable) and Path(executable).exists()
            browser_detail = executable if browser_ok else "browser not installed"
    needs = "measuring the rebuilt page"
    checks.append(_check("Playwright", playwright_ok, "found" if playwright_ok else "missing", "npm i -D playwright (init installs it inside the skill folder)", required=False, needed_for=needs))
    checks.append(_check("Playwright browser", browser_ok, browser_detail, "npx playwright install chromium", required=False, needed_for=needs))
    return checks


# ---- 1b. install what is missing ---------------------------------------------------------------------------------------------------------
def _tail(text: str, lines: int = 3) -> str:
    kept = [line.strip() for line in (text or "").strip().splitlines() if line.strip()]
    return " | ".join(kept[-lines:])


def _step(name: str, command: list[str], cwd: Path | None, run, progress) -> dict:
    progress(name)
    try:
        done = run(command, capture_output=True, text=True, check=False, cwd=cwd, timeout=INSTALL_TIMEOUT)
        ok, detail = done.returncode == 0, "" if done.returncode == 0 else _tail(done.stderr or done.stdout)
    except (OSError, subprocess.TimeoutExpired) as error:
        ok, detail = False, str(error)
    return {"name": name, "ok": ok, "detail": detail, "command": " ".join(command)}


def install_missing(checks: list[dict], scripts: Path, which=shutil.which, run=subprocess.run, progress=lambda text: None, python: str | None = None) -> list[dict]:
    """Install the libraries the checks found missing: Python packages (pip), Playwright (npm, inside the skill's scripts/ folder, so the project's package.json stays untouched) and its Chromium. Tools of the machine (Python, poppler, Node) are never installed."""
    failed = {item["name"] for item in checks if not item["ok"]}
    done: list[dict] = []
    packages = [package for _, package in PYTHON_MODULES if f"Python package {package}" in failed]
    if packages:
        done.append(_step(f"Python packages: {', '.join(packages)}", [python or sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *[PIP_SPECS[name] for name in packages]], None, run, progress))
    node, npm, npx = which("node"), which("npm"), which("npx")
    if node and npm and "Playwright" in failed:
        done.append(_step("Playwright (npm, in the skill's scripts folder)", [npm, "install", "--no-save", "--no-package-lock", "--no-audit", "--no-fund", "--prefix", str(scripts), "playwright"], scripts, run, progress))
    if node and npx and ("Playwright" in failed or "Playwright browser" in failed) and not (done and done[-1]["name"].startswith("Playwright (npm") and not done[-1]["ok"]):
        done.append(_step("Chromium browser for Playwright", [npx, "playwright", "install", "chromium"], scripts, run, progress))
    importlib.invalidate_caches()
    return done


# ---- 2. hook -----------------------------------------------------------------------------------------------------------------------------
def hook_command(skill: Path, project: Path) -> str:
    try:
        relative = skill.resolve().relative_to(project.resolve())
        return f'python3 "$CLAUDE_PROJECT_DIR"/{relative.as_posix()}/hooks/{HOOK_FILE}'
    except ValueError:
        return f'python3 "{(skill / "hooks" / HOOK_FILE).resolve()}"'


def merge_hook(settings: dict, command: str) -> tuple[dict, str]:
    """Add the Stop hook entry unless a hook running ebook-gate-stop.py is already registered. Returns (settings, 'added' | 'present')."""
    hooks = settings.setdefault("hooks", {})
    stops = hooks.setdefault("Stop", [])
    for group in stops:
        for item in group.get("hooks", []):
            if HOOK_FILE in item.get("command", ""):
                return settings, "present"
    stops.append({"hooks": [{"type": "command", "command": command}]})
    return settings, "added"


def install_hook(skill: Path, project: Path, write: bool) -> dict:
    hook = skill / "hooks" / HOOK_FILE
    if not hook.is_file():
        raise InitError(f"the hook file {hook} is missing: the skill folder is incomplete")
    path = project / ".claude" / "settings.json"
    settings: dict = {}
    if path.exists():
        try:
            settings = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as error:
            raise InitError(f"{path} is not valid JSON ({error}); fix it first, nothing was changed") from error
        if not isinstance(settings, dict):
            raise InitError(f"{path} must hold a JSON object; nothing was changed")
    command = hook_command(skill, project)
    settings, state = merge_hook(settings, command)
    if state == "added" and write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"file": str(path), "state": state, "command": command}


# ---- 3. gitignore ------------------------------------------------------------------------------------------------------------------------
def install_gitignore(project: Path, write: bool) -> dict:
    path = project / ".gitignore"
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    present = {line.strip() for line in existing}
    missing = [line for line in GITIGNORE_LINES if line not in present]
    if missing and write:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        block = ("" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")) + GITIGNORE_HEADER + "\n" + "\n".join(missing) + "\n"
        path.write_text(text + block, encoding="utf-8")
    return {"file": str(path), "added": missing}


# ---- run ---------------------------------------------------------------------------------------------------------------------------------
def run_init(project: Path, skill: Path | None = None, write: bool = True, install: bool = False, progress=lambda text: None, installer: dict | None = None, **environment) -> dict:
    skill = (skill or skill_dir()).resolve()
    project = project.resolve()
    if not project.is_dir():
        raise InitError(f"project folder {project} does not exist")
    result: dict = {"project": str(project), "skill": str(skill), "warnings": []}
    expected = project / ".claude" / "skills"
    if skill.parent != expected.resolve():
        result["warnings"].append(f"the skill is at {skill}, not under {expected}: Claude Code only loads skills from <project>/.claude/skills/<name>/. Copy or clone it there.")
    if not (skill / "SKILL.md").is_file():
        raise InitError(f"{skill} has no SKILL.md: not a skill folder")
    result["environment"] = check_environment(skill / "scripts", **environment)
    result["installed"] = []
    if install and write and any(not item["ok"] for item in result["environment"]):
        result["installed"] = install_missing(result["environment"], skill / "scripts", progress=progress, **(installer or {}))
        if result["installed"]:
            result["environment"] = check_environment(skill / "scripts", **environment)
    result["hook"] = install_hook(skill, project, write)
    result["gitignore"] = install_gitignore(project, write)
    result["stack"] = stack.detect(project)
    result["wrote"] = write
    result["ok"] = all(item["ok"] for item in result["environment"] if item["required"])
    return result


class Style:
    """Console look: colour only on a terminal (and never with NO_COLOR), symbols fall back to ASCII where the console cannot print them."""

    def __init__(self, color: bool = False, unicode: bool = False):
        self.color, self.unicode = color, unicode
        self.ok, self.fail, self.warn, self.arrow, self.dot = ("✓", "✗", "!", "→", "·") if unicode else ("+", "x", "!", "->", "-")

    def _paint(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def bold(self, text): return self._paint("1", text)
    def dim(self, text): return self._paint("2", text)
    def green(self, text): return self._paint("32", text)
    def red(self, text): return self._paint("31", text)
    def yellow(self, text): return self._paint("33", text)
    def cyan(self, text): return self._paint("36", text)


def make_style(stream=None, env=None) -> Style:
    import os

    stream = stream or sys.stdout
    env = os.environ if env is None else env
    tty = bool(getattr(stream, "isatty", lambda: False)())
    color = (tty or bool(env.get("FORCE_COLOR"))) and not env.get("NO_COLOR") and env.get("TERM") != "dumb"
    unicode = not env.get("PDF_TO_UI_ASCII") and env.get("TERM") != "dumb"
    try:
        "✓✗→·".encode(getattr(stream, "encoding", None) or "ascii")
    except (UnicodeEncodeError, LookupError):
        unicode = False
    if color and sys.platform == "win32":
        os.system("")  # switches the Windows console to ANSI escape handling
    return Style(color, unicode)


def _relative(path: str, project: str) -> str:
    try:
        return Path(path).resolve().relative_to(Path(project).resolve()).as_posix()
    except ValueError:
        return path


def format_report(result: dict, style: Style | None = None) -> str:
    st = style or Style()
    mark = {"ok": st.green(st.ok), "fail": st.red(st.fail), "warn": st.yellow(st.warn)}
    out: list[str] = ["", f"  {st.bold('pdf-to-ui-replica')} init" + (st.dim("   --check: nothing was written") if not result["wrote"] else ""), f"  {st.dim(result['project'])}", ""]
    if result.get("installed"):
        out.append(f"  {st.bold('Installed')}")
        for step in result["installed"]:
            out.append(f"    {mark['ok' if step['ok'] else 'fail']} {step['name']}")
            if not step["ok"]:
                out += [f"        {st.dim(step['detail'] or 'the command failed')}", f"        {st.cyan(st.arrow)} run it yourself: {step['command']}"]
        out.append("")
    width = max(len(item["name"]) for item in result["environment"])
    out.append(f"  {st.bold('Environment')}")
    for item in result["environment"]:
        level = "ok" if item["ok"] else ("fail" if item["required"] else "warn")
        out.append(f"    {mark[level]} {item['name'].ljust(width)}  {st.dim(item['detail'])}")
        if not item["ok"]:
            out.append(f"        {st.cyan(st.arrow)} {item['fix']}")
            if item["needed_for"]:
                out.append(f"          {st.dim('needed for ' + item['needed_for'])}")
    hook, gitignore, found = result["hook"], result["gitignore"], result["stack"]
    verb = {"added": "would register" if not result["wrote"] else "registered", "present": "already registered"}[hook["state"]]
    import os

    out += ["", f"  {st.bold('Project')}"]
    if os.environ.get("PDF_TO_UI_INSTALL"):  # set by `npx pdf-to-ui-replica init` (bin/cli.js)
        out.append(f"    {mark['ok']} {'Skill'.ljust(11)} {os.environ['PDF_TO_UI_INSTALL']}")
    out += [f"    {mark['ok']} {'Stop hook'.ljust(11)} {verb} in {_relative(hook['file'], result['project'])}", f"        {st.dim(hook['command'])}"]
    out.append(f"    {mark['ok']} {'.gitignore'.ljust(11)} " + (f"{'would add' if not result['wrote'] else 'added'} {', '.join(gitignore['added'])}" if gitignore["added"] else "already up to date"))
    if found["supported"]:
        out.append(f"    {mark['ok']} {'UI stack'.ljust(11)} {stack.SUPPORTED} found in {found['app']}: builds are supported")
    else:
        out += [f"    {mark['warn']} {'UI stack'.ljust(11)} {stack.SUPPORTED} not found ({'; '.join(found['reasons'])})", f"        {st.dim('Analysis (inventory, measuring, verifying a page) works on any project; building pages needs this stack for now.')}"]
    for warning in result["warnings"]:
        out += ["", f"  {mark['warn']} {st.yellow(warning)}"]
    required_missing = [item["name"] for item in result["environment"] if item["required"] and not item["ok"]]
    later = [item["name"] for item in result["environment"] if not item["required"] and not item["ok"]]
    out.append("")
    if required_missing:
        out.append(f"  {mark['fail']} {st.bold(st.red('Not ready'))}  install the missing required tools first: {', '.join(required_missing)}")
    else:
        out.append(f"  {mark['ok']} {st.bold(st.green('Ready'))}")
    if later:
        out.append(f"    {st.dim('Needed before you measure a rebuilt page: ' + ', '.join(later))}")
    if not required_missing:
        scripts = str(Path(result["skill"]) / "scripts")
        out += ["", f"  {st.bold('Next')}  start a build", f"    cd {scripts}", f"    PYTHONPATH=. python3 -m pdfmeasure state init --output <out> --pages <first>-<last> --pilot <p1,p2,p3> --root {result['project']}"]
    else:
        out += ["", f"  {st.bold('Next')}  run this command again after installing"]
    return "\n".join(out) + "\n"


def command_init(args) -> int:
    skill = skill_dir()
    project = Path(args.project) if args.project else default_project(skill)
    if project is None:
        print(f"init: the skill is not inside <project>/.claude/skills/; give the project with --project <folder> (skill at {skill})")
        return 2
    try:
        style = make_style()
        result = run_init(project, skill, write=not args.check, install=not (args.check or args.no_install), progress=lambda text: print(f"  {style.cyan(style.arrow)} installing {text} ...", flush=True))
    except InitError as error:
        print(f"init: {error}")
        return 2
    print(format_report(result, make_style()))
    return 0 if result["ok"] else 1


def register(add) -> None:
    cmd = add("init", command_init, "put the skill to work in a project: check the environment, register the Stop hook, update .gitignore, report the UI stack")
    cmd.add_argument("--project", help="the project folder (default: the project this skill is installed in)")
    cmd.add_argument("--check", action="store_true", help="report only, write nothing")
    cmd.add_argument("--no-install", action="store_true", help="do not install missing libraries (pip packages, Playwright and its browser)")


def main(argv: list[str] | None = None) -> int:
    """Entry of scripts/init.py: runs without importing the rest of the toolkit (which needs numpy and Pillow)."""
    import argparse

    parser = argparse.ArgumentParser(prog="init.py", description="Put the pdf-to-ui-replica skill to work in a project.")
    parser.add_argument("--project", help="the project folder (default: the project this skill is installed in)")
    parser.add_argument("--check", action="store_true", help="report only, write nothing")
    parser.add_argument("--no-install", action="store_true", help="do not install missing libraries (pip packages, Playwright and its browser)")
    return command_init(parser.parse_args(argv))
