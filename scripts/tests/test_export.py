"""The export mirrors the skill folder into a standalone checkout: new and changed files copied, removed files deleted, itself and caches left out."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "export-standalone.py"
if not SCRIPT.exists():  # the standalone copy does not carry the export script
    pytest.skip("export-standalone.py is only in the source repository", allow_module_level=True)
spec = importlib.util.spec_from_file_location("export_standalone", SCRIPT)
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "t@t")
    git(path, "config", "user.name", "t")
    return path


def test_mirror_copies_new_files_removes_old_ones_and_skips_itself_and_caches(tmp_path):
    skill = make_repo(tmp_path / "project" / "skill")
    (skill / ".gitignore").write_text("__pycache__/\n")
    (skill / "SKILL.md").write_text("v1")
    (skill / "scripts").mkdir()
    (skill / "scripts" / "export-standalone.py").write_text("# not copied")
    (skill / "scripts" / "tool.py").write_text("print(1)")
    (skill / "scripts" / "__pycache__").mkdir()
    (skill / "scripts" / "__pycache__" / "tool.pyc").write_text("x")
    git(skill, "add", "-A")
    git(skill, "commit", "-qm", "init")
    (skill / "NEW.md").write_text("uncommitted new file")  # a new file that is not committed yet is exported too
    dest = make_repo(tmp_path / "standalone")
    (dest / "old.md").write_text("gone from the skill")
    (dest / "old").mkdir()
    (dest / "old" / "deep.md").write_text("x")
    git(dest, "add", "-A")
    git(dest, "commit", "-qm", "old")
    result = export.mirror(skill, dest)
    assert (dest / "SKILL.md").read_text() == "v1" and (dest / "NEW.md").exists() and (dest / "scripts" / "tool.py").exists()
    assert not (dest / "scripts" / "export-standalone.py").exists() and not (dest / "scripts" / "__pycache__").exists()
    assert result["removed"] == ["old.md", "old/deep.md"] and not (dest / "old.md").exists() and not (dest / "old").exists()
    (skill / "SKILL.md").write_text("v2")
    export.mirror(skill, dest)
    assert (dest / "SKILL.md").read_text() == "v2"


def test_mirror_refuses_a_bad_destination(tmp_path):
    skill = make_repo(tmp_path / "skill")
    (skill / "SKILL.md").write_text("x")
    with pytest.raises(SystemExit, match="not a git checkout"):
        export.mirror(skill, tmp_path / "plain")
    (tmp_path / "plain").mkdir()
    with pytest.raises(SystemExit, match="not a git checkout"):
        export.mirror(skill, tmp_path / "plain")
    inside = make_repo(skill / "inner")
    with pytest.raises(SystemExit, match="outside the skill folder"):
        export.mirror(skill, inside)
