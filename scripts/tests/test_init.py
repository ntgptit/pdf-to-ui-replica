"""`init`: environment report with the install command for each gap, a merged and idempotent Stop hook entry, .gitignore lines, stack report, --check writes nothing."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmeasure import setup_project as sp  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent
COMMAND = 'python3 "$CLAUDE_PROJECT_DIR"/.claude/skills/pdf-to-ui-replica/hooks/ebook-gate-stop.py'


def install_skill(project: Path) -> Path:
    """A skill folder at the standard place, with the files init needs."""
    skill = project / ".claude" / "skills" / "pdf-to-ui-replica"
    (skill / "hooks").mkdir(parents=True)
    (skill / "scripts").mkdir()
    (skill / "SKILL.md").write_text("---\nname: pdf-to-ui-replica\n---\n")
    (skill / "hooks" / sp.HOOK_FILE).write_text("# hook\n")
    return skill


class Done:
    def __init__(self, out="", code=0):
        self.stdout, self.returncode = out, code


def fake_run(node_version="v20.11.0", playwright=True, browser=True, browser_path="/browser/chrome"):
    def run(command, **kwargs):
        if "--version" in command:
            return Done(node_version + "\n")
        if "-e" in command:
            return Done(browser_path + "\n" if playwright else "", 0 if playwright else 1)
        raise AssertionError(command)
    return run


def environment(tmp_path, **overrides):
    options = dict(which=lambda name: f"/usr/bin/{name}", run=fake_run(), find_spec=lambda name: object(), python=(3, 12, 0))
    options.update(overrides)
    return sp.check_environment(tmp_path, **options)


def by_name(checks):
    return {item["name"]: item for item in checks}


def test_a_complete_environment_is_all_ok(tmp_path):
    (tmp_path / "browser").mkdir()
    chrome = tmp_path / "browser" / "chrome"
    chrome.write_text("")
    found = by_name(environment(tmp_path, run=fake_run(browser_path=str(chrome))))
    assert all(item["ok"] for item in found.values()), [n for n, i in found.items() if not i["ok"]]


def test_each_gap_reports_its_install_command_and_what_is_required(tmp_path):
    found = by_name(environment(tmp_path, which=lambda name: None, find_spec=lambda name: None, python=(3, 9, 1)))
    assert not found["Python"]["ok"] and "3.10" in found["Python"]["fix"]
    assert not found["Python package numpy"]["ok"] and "pip install -r" in found["Python package numpy"]["fix"]
    assert not found["poppler (pdftoppm)"]["ok"] and "apt-get install -y poppler-utils" in found["poppler (pdftoppm)"]["fix"] and found["poppler (pdftoppm)"]["required"]
    assert not found["Node"]["ok"] and not found["Node"]["required"] and "rebuilt page" in found["Node"]["needed_for"]
    assert "npm i -D playwright" in found["Playwright"]["fix"] and "playwright install chromium" in found["Playwright browser"]["fix"]


def test_an_old_node_and_a_missing_browser_are_reported(tmp_path):
    found = by_name(environment(tmp_path, run=fake_run(node_version="v16.20.2")))
    assert not found["Node"]["ok"] and found["Node"]["detail"] == "v16.20.2"
    found = by_name(environment(tmp_path, run=fake_run(browser_path=str(tmp_path / "nope"))))
    assert found["Playwright"]["ok"] and not found["Playwright browser"]["ok"] and found["Playwright browser"]["detail"] == "browser not installed"


def test_the_hook_is_merged_without_touching_the_rest_and_only_once():
    settings = {"model": "x", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other.py"}]}], "PreToolUse": [{"hooks": []}]}}
    merged, state = sp.merge_hook(settings, COMMAND)
    assert state == "added" and merged["model"] == "x" and "PreToolUse" in merged["hooks"]
    assert merged["hooks"]["Stop"][0]["hooks"][0]["command"] == "other.py" and merged["hooks"]["Stop"][1]["hooks"][0]["command"] == COMMAND
    assert sp.merge_hook(merged, COMMAND)[1] == "present"
    assert sp.merge_hook(merged, "python3 /elsewhere/ebook-gate-stop.py")[1] == "present"  # registered from another path: not added twice
    empty, state = sp.merge_hook({}, COMMAND)
    assert state == "added" and empty["hooks"]["Stop"][0]["hooks"][0]["type"] == "command"


def test_init_installs_hook_and_gitignore_and_is_idempotent(tmp_path):
    skill = install_skill(tmp_path)
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "keep.py"}]}]}, "model": "m"}))
    first = sp.run_init(tmp_path, skill, **{"which": lambda n: "/usr/bin/" + n, "run": fake_run(), "find_spec": lambda n: object(), "python": (3, 12, 0)})
    assert first["hook"]["state"] == "added" and first["hook"]["command"] == COMMAND and first["gitignore"]["added"] == list(sp.GITIGNORE_LINES)
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert settings["model"] == "m" and [h["hooks"][0]["command"] for h in settings["hooks"]["Stop"]] == ["keep.py", COMMAND]
    ignore = (tmp_path / ".gitignore").read_text()
    assert ignore.startswith("node_modules/\n") and "pdf-to-ui-output/\n" in ignore and ".tmp/pdf-to-ui/\n" in ignore
    second = sp.run_init(tmp_path, skill, **{"which": lambda n: "/usr/bin/" + n, "run": fake_run(), "find_spec": lambda n: object(), "python": (3, 12, 0)})
    assert second["hook"]["state"] == "present" and second["gitignore"]["added"] == []
    assert (tmp_path / ".gitignore").read_text() == ignore and json.loads((tmp_path / ".claude" / "settings.json").read_text()) == settings


def test_check_writes_nothing(tmp_path):
    skill = install_skill(tmp_path)
    result = sp.run_init(tmp_path, skill, write=False, which=lambda n: None, run=fake_run(), find_spec=lambda n: None, python=(3, 12, 0))
    assert result["hook"]["state"] == "added" and result["gitignore"]["added"] and not result["ok"]
    assert not (tmp_path / ".claude" / "settings.json").exists() and not (tmp_path / ".gitignore").exists()
    assert "--check: nothing was written" in sp.format_report(result) and "would register" in sp.format_report(result)


def test_broken_settings_a_missing_hook_and_a_misplaced_skill_are_reported(tmp_path, tmp_path_factory):
    skill = install_skill(tmp_path)
    (tmp_path / ".claude" / "settings.json").write_text("{ not json")
    with pytest.raises(sp.InitError, match="not valid JSON"):
        sp.install_hook(skill, tmp_path, write=True)
    assert (tmp_path / ".claude" / "settings.json").read_text() == "{ not json"  # never overwritten
    (skill / "hooks" / sp.HOOK_FILE).unlink()
    (tmp_path / ".claude" / "settings.json").unlink()
    with pytest.raises(sp.InitError, match="hook file .* is missing"):
        sp.install_hook(skill, tmp_path, write=True)
    other = tmp_path_factory.mktemp("outside") / "pdf-to-ui-replica"  # a skill folder outside the project
    (other / "hooks").mkdir(parents=True)
    (other / "hooks" / sp.HOOK_FILE).write_text("#")
    (other / "SKILL.md").write_text("x")
    result = sp.run_init(tmp_path, other, write=False, which=lambda n: "/x", run=fake_run(), find_spec=lambda n: object(), python=(3, 12, 0))
    assert any("not under" in w for w in result["warnings"]) and str(other.resolve()) in result["hook"]["command"]
    inside = tmp_path / "vendor" / "pdf-to-ui-replica"  # inside the project but not at .claude/skills: still warned, hook path relative
    (inside / "hooks").mkdir(parents=True)
    (inside / "hooks" / sp.HOOK_FILE).write_text("#")
    (inside / "SKILL.md").write_text("x")
    result = sp.run_init(tmp_path, inside, write=False, which=lambda n: "/x", run=fake_run(), find_spec=lambda n: object(), python=(3, 12, 0))
    assert any("not under" in w for w in result["warnings"]) and result["hook"]["command"].startswith('python3 "$CLAUDE_PROJECT_DIR"/vendor/')


def test_the_project_is_found_from_the_skill_location_and_the_stack_is_reported(tmp_path):
    skill = install_skill(tmp_path)
    assert sp.default_project(skill) == tmp_path
    assert sp.default_project(tmp_path / "somewhere" / "skill") is None
    result = sp.run_init(tmp_path, skill, write=False, which=lambda n: "/x", run=fake_run(), find_spec=lambda n: object(), python=(3, 12, 0))
    assert not result["stack"]["supported"] and "builds need this stack for now" not in sp.format_report(result) and "Analysis" in sp.format_report(result)
    app = tmp_path / "web"
    app.mkdir()
    (app / "package.json").write_text(json.dumps({"dependencies": {"react": "^19.0.0"}, "devDependencies": {"tailwindcss": "^4.1.0"}}))
    (app / "components.json").write_text(json.dumps({"style": "new-york", "tailwind": {"css": "src/index.css"}}))
    result = sp.run_init(tmp_path, skill, write=False, which=lambda n: "/x", run=fake_run(), find_spec=lambda n: object(), python=(3, 12, 0))
    assert result["stack"]["supported"] and "builds are supported" in sp.format_report(result)


def test_the_entry_script_runs_without_importing_the_rest_of_the_toolkit(tmp_path):
    skill = install_skill(tmp_path)
    for name in ("init.py",):
        (skill / "scripts" / name).write_text((SCRIPTS / name).read_text())
    (skill / "scripts" / "pdfmeasure").mkdir()
    for module in ("__init__.py", "setup_project.py", "stack.py"):
        (skill / "scripts" / "pdfmeasure" / module).write_text((SCRIPTS / "pdfmeasure" / module).read_text())
    run = subprocess.run([sys.executable, "-S", str(skill / "scripts" / "init.py"), "--check"], capture_output=True, text=True, check=False)  # -S: no site-packages, like a machine without numpy
    assert run.returncode in (0, 1), run.stderr[-300:]
    assert "pdf-to-ui-replica" in run.stdout and "Python package numpy" in run.stdout and "Stop hook" in run.stdout
    assert not (tmp_path / ".claude" / "settings.json").exists()
