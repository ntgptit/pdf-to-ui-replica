"""`npx pdf-to-ui-replica init` (bin/cli.js): installs the skill into a project and runs init."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[2] / "bin" / "cli.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")


def run(*args):
    return subprocess.run(["node", str(CLI), *args], capture_output=True, text=True, timeout=120)


def test_init_installs_skill_and_registers_hook(tmp_path):
    first = run("init", "--project", str(tmp_path))
    installed = tmp_path / ".claude" / "skills" / "pdf-to-ui-replica"
    assert (installed / "SKILL.md").is_file() and (installed / "scripts" / "init.py").is_file()
    assert not (installed / "scripts" / "tests" / "__pycache__").exists()
    assert "Stop hook" in first.stdout
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "ebook-gate-stop.py" in json.dumps(settings)
    assert "pdf-to-ui-output/" in (tmp_path / ".gitignore").read_text()
    again = run("init", "--project", str(tmp_path))                 # idempotent, installed copy kept
    assert "kept the installed copy" in again.stdout and "installed in .claude" in first.stdout
    assert json.dumps(json.loads((tmp_path / ".claude" / "settings.json").read_text())).count("ebook-gate-stop.py") == 1
    (installed / "SKILL.md").write_text("old")
    run("init", "--project", str(tmp_path), "--update")
    assert (installed / "SKILL.md").read_text() != "old"


def test_check_writes_nothing_and_errors_are_clear(tmp_path):
    result = run("--check", "--project", str(tmp_path))
    assert "Environment" in result.stdout and not (tmp_path / ".claude").exists()
    assert run("--project", str(tmp_path / "missing")).returncode == 2
    assert run("--bogus").returncode == 2
    assert "Usage" in run("--help").stdout
