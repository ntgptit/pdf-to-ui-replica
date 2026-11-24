"""install.sh: installs the skill with npx (or git when npx is missing), then runs init; skips an installed copy unless --update; clear errors."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[2]
INSTALL = SKILL / "install.sh"
pytestmark = pytest.mark.skipif(shutil.which("sh") is None or not INSTALL.exists(), reason="needs sh and install.sh")


SH = shutil.which("sh")
TOOLS = ("mkdir", "rm", "cp", "cat", "echo", "dirname")


def stub(bin_dir: Path, name: str, body: str):
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


def copy_skill(destination: str) -> str:
    """Shell snippet that puts a copy of the real skill at `destination` (what npx or git clone would leave there)."""
    return f'mkdir -p "{destination}" && cp -r "{SKILL}"/. "{destination}"/ && rm -rf "{destination}/.git"\n'


def system_tool(name: str) -> str | None:
    """The real binary from /usr/bin or /bin (a wrapper earlier on the PATH, such as a safety guard for rm, would not do in a sandbox)."""
    for folder in ("/usr/bin", "/bin"):
        if (Path(folder) / name).exists():
            return str(Path(folder) / name)
    return shutil.which(name)


def sandbox(bin_dir: Path):
    """A PATH that holds only python3 and the few coreutils the script and stubs use: no real npx, no real git, no network."""
    for name in TOOLS:
        found = system_tool(name)
        if found and not (bin_dir / name).exists():
            (bin_dir / name).symlink_to(found)
    if not (bin_dir / "python3").exists():
        (bin_dir / "python3").symlink_to(sys.executable)


def run(project: Path, bin_dir: Path, *args: str):
    sandbox(bin_dir)
    env = {"PATH": str(bin_dir), "HOME": str(project)}
    return subprocess.run([SH, str(INSTALL), "--project", str(project), *args], capture_output=True, text=True, env=env, check=False)


@pytest.fixture
def setup(tmp_path):
    project, bin_dir = tmp_path / "project", tmp_path / "bin"
    project.mkdir()
    bin_dir.mkdir()
    return project, bin_dir, tmp_path / "calls.log"


def test_npx_installs_the_skill_then_init_registers_the_hook(setup):
    project, bin_dir, log = setup
    stub(bin_dir, "npx", f'echo "npx $*" >> "{log}"\n' + copy_skill(".claude/skills/pdf-to-ui-replica"))
    result = run(project, bin_dir)
    assert "npx --yes skills@1.7.6 add ntgptit/pdf-to-ui-replica --agent claude-code -y" in log.read_text()
    assert (project / ".claude/skills/pdf-to-ui-replica/SKILL.md").exists() and "running setup" in result.stdout and "Stop hook: registered" in result.stdout
    settings = json.loads((project / ".claude/settings.json").read_text())
    assert "ebook-gate-stop.py" in settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "pdf-to-ui-output/" in (project / ".gitignore").read_text()


def test_git_clone_is_the_fallback_without_npx_and_the_repo_is_configurable(setup):
    project, bin_dir, log = setup
    # git clone --depth 1 <url> <dest>: the stub copies the skill to <dest>, its last argument
    stub(bin_dir, "git", f'echo "git $*" >> "{log}"\nfor last; do :; done\n' + copy_skill("$last"))
    result = run(project, bin_dir, "--repo", "friend/skill-copy")
    assert "git clone --depth 1 https://github.com/friend/skill-copy.git .claude/skills/pdf-to-ui-replica" in log.read_text()
    assert (project / ".claude/skills/pdf-to-ui-replica/scripts/init.py").exists() and not (project / ".claude/skills/pdf-to-ui-replica/.git").exists()
    assert "npx not found" in result.stdout and "Stop hook" in result.stdout


def test_an_installed_copy_is_kept_unless_update_is_given(setup):
    project, bin_dir, log = setup
    copy = project / ".claude/skills/pdf-to-ui-replica"
    shutil.copytree(SKILL, copy, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    (copy / "LOCAL-MARK").write_text("mine")
    stub(bin_dir, "npx", f'echo "npx $*" >> "{log}"\n' + copy_skill(".claude/skills/pdf-to-ui-replica"))
    result = run(project, bin_dir)
    assert "already installed" in result.stdout and not log.exists() and (copy / "LOCAL-MARK").exists() and "Stop hook" in result.stdout
    result = run(project, bin_dir, "--update")
    assert "replacing" in result.stdout and log.exists() and not (copy / "LOCAL-MARK").exists()


def test_clear_errors(setup):
    project, bin_dir, log = setup
    result = run(project, bin_dir)  # no npx, no git on the path
    assert result.returncode == 2 and "neither npx nor git found" in result.stderr
    stub(bin_dir, "npx", f'echo "npx $*" >> "{log}"\nexit 0\n')  # npx "succeeds" but nothing arrives (a private repository without login)
    result = run(project, bin_dir)
    assert result.returncode == 1 and "did not arrive" in result.stderr and "gh auth login" in result.stderr
    assert subprocess.run([SH, str(INSTALL), "--bogus"], capture_output=True, text=True, check=False).returncode == 2
    assert subprocess.run([SH, str(INSTALL), "--project", str(project / "missing")], capture_output=True, text=True, check=False).returncode == 2
    help_text = subprocess.run([SH, str(INSTALL), "--help"], capture_output=True, text=True, check=False)
    assert help_text.returncode == 0 and "--update" in help_text.stdout


def test_an_old_python_is_refused(setup):
    project, bin_dir, log = setup
    for name in TOOLS:
        found = system_tool(name)
        if found:
            (bin_dir / name).symlink_to(found)
    stub(bin_dir, "python3", "exit 1\n")  # the version check fails like an old interpreter
    stub(bin_dir, "npx", "exit 0\n")
    result = subprocess.run([SH, str(INSTALL), "--project", str(project)], capture_output=True, text=True, env={"PATH": str(bin_dir)}, check=False)
    assert result.returncode == 2 and "Python 3.10 or newer is required" in result.stderr
