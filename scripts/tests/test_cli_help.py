"""Every command's --help renders: argparse formats help strings with `%`, so a bare percent sign crashes `pdfmeasure --help` (it did, once)."""
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from pdfmeasure import cli  # noqa: E402


def commands() -> list[str]:
    parser = cli.build_parser()
    action = next(a for a in parser._actions if a.dest == "command")
    return sorted(action.choices)


def test_the_top_level_help_renders_and_lists_every_command():
    text = cli.build_parser().format_help()
    for name in commands():
        assert name in text


def test_every_subcommand_help_renders():
    parser = cli.build_parser()
    action = next(a for a in parser._actions if a.dest == "command")
    for name, sub in action.choices.items():
        assert sub.format_help().startswith("usage:"), name


def test_the_help_works_from_the_command_line():
    for args in (["--help"], ["typography", "--help"]):
        run = subprocess.run([sys.executable, "-m", "pdfmeasure", *args], cwd=SCRIPTS, capture_output=True, text=True, check=False, env={"PYTHONPATH": str(SCRIPTS), "PATH": "/usr/bin:/bin:/usr/local/bin"})
        assert run.returncode == 0, run.stderr[-300:]
