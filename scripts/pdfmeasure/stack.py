"""The UI stack the skill supports: React + shadcn/ui + Tailwind CSS v4. Other stacks are planned, not supported yet: the harness refuses them at
`gate scope` so a build does not start on guidance that does not fit. Detection: a `components.json` (shadcn) next to a `package.json` that depends on
react and tailwindcss >= 4, somewhere under the repository root (monorepos keep the app in a sub-folder)."""
from __future__ import annotations

import json
import re
from pathlib import Path

SUPPORTED = "React + shadcn/ui + Tailwind CSS v4"
SKIP = {"node_modules", ".git", "dist", "build", ".next", ".turbo", ".tmp", "coverage"}
MAX_DEPTH = 4


def _major(version: str | None) -> int | None:
    match = re.search(r"(\d+)", version or "")
    return int(match.group(1)) if match else None


def _candidates(root: Path, depth: int = 0):
    if depth > MAX_DEPTH or not root.is_dir():
        return
    if (root / "components.json").is_file():
        yield root
    for child in sorted(root.iterdir()):
        if child.is_dir() and child.name not in SKIP and not child.name.startswith("."):
            yield from _candidates(child, depth + 1)


def detect(root: str | Path) -> dict:
    """{supported, app, react, tailwind, style, reasons}: the first app folder that fits, or why none does."""
    root = Path(root).resolve()
    reasons = []
    for app in _candidates(root):
        package = app / "package.json"
        if not package.is_file():
            reasons.append(f"{app.relative_to(root)}: components.json without package.json")
            continue
        data = json.loads(package.read_text(encoding="utf-8"))
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        components = json.loads((app / "components.json").read_text(encoding="utf-8"))
        react, tailwind = deps.get("react"), deps.get("tailwindcss")
        problems = []
        if not react:
            problems.append("no react dependency")
        if _major(tailwind) is None or _major(tailwind) < 4:
            problems.append(f"tailwindcss {tailwind or 'missing'} (v4 needed: the guidance uses @custom-variant and container queries)")
        if "tailwind" not in components:
            problems.append("components.json has no tailwind section")
        if problems:
            reasons.append(f"{app.relative_to(root) or '.'}: " + "; ".join(problems))
            continue
        return {"supported": True, "app": str(app.relative_to(root)) or ".", "react": react, "tailwind": tailwind, "style": components.get("style", ""),
                "css": components.get("tailwind", {}).get("css", ""), "aliases": components.get("aliases", {}), "reasons": []}
    if not reasons:
        reasons.append("no components.json (shadcn/ui) found under the repository")
    return {"supported": False, "app": None, "reasons": reasons}
