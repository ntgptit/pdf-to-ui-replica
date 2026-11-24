#!/bin/sh
# Install the pdf-to-ui-replica skill into a project and set it up, in one command.
#
#   sh install.sh [--project DIR] [--repo OWNER/REPO] [--update]
#
# From a project, without cloning first:
#   curl -fsSL https://raw.githubusercontent.com/ntgptit/pdf-to-ui-replica/main/install.sh | sh                          (public repository)
#   gh api repos/ntgptit/pdf-to-ui-replica/contents/install.sh -H "Accept: application/vnd.github.raw" | sh               (private: uses your gh login)
#
# What it does: (1) installs the skill into <project>/.claude/skills/pdf-to-ui-replica (npx skills when npx exists, else git clone),
# (2) runs scripts/init.py (environment check, Stop hook, .gitignore, stack report). It never installs system packages.
# Options: --project DIR (default: the current directory), --repo OWNER/REPO (default: ntgptit/pdf-to-ui-replica, or $PDF_TO_UI_REPO),
# --update (replace an installed copy with the latest). POSIX sh: works on Linux, macOS and Git Bash on Windows.
set -eu

REPO="${PDF_TO_UI_REPO:-ntgptit/pdf-to-ui-replica}"
SKILLS_CLI="skills@1.7.6"   # pinned, like every skill install in the projects this was built for
NAME="pdf-to-ui-replica"
PROJECT="."
UPDATE=0

usage() {
  cat <<'USAGE'
Install the pdf-to-ui-replica skill into a project and set it up, in one command.

  sh install.sh [--project DIR] [--repo OWNER/REPO] [--update]

  --project DIR      the project to install into (default: the current directory)
  --repo OWNER/REPO  where to install from (default: ntgptit/pdf-to-ui-replica, or $PDF_TO_UI_REPO)
  --update           replace an installed copy with the latest

It installs the skill into <project>/.claude/skills/pdf-to-ui-replica (npx skills when npx exists, else git clone), then runs
scripts/init.py: environment check, Stop hook, .gitignore, stack report. It never installs system packages.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --project) [ $# -ge 2 ] || { echo "install: --project needs a folder" >&2; exit 2; }; PROJECT="$2"; shift 2 ;;
    --repo) [ $# -ge 2 ] || { echo "install: --repo needs OWNER/REPO" >&2; exit 2; }; REPO="$2"; shift 2 ;;
    --update) UPDATE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "install: unknown option $1 (try --help)" >&2; exit 2 ;;
  esac
done

[ -d "$PROJECT" ] || { echo "install: project folder '$PROJECT' does not exist" >&2; exit 2; }
cd "$PROJECT"
DEST=".claude/skills/$NAME"

PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
done
[ -n "$PYTHON" ] || { echo "install: Python 3.10 or newer is required (install it, then run this again)" >&2; exit 2; }

if [ -d "$DEST" ] && [ "$UPDATE" -eq 0 ]; then
  echo "install: $DEST is already installed (use --update to replace it with the latest); running setup"
else
  if [ -d "$DEST" ]; then
    echo "install: replacing $DEST"
    rm -rf "$DEST"
  fi
  mkdir -p .claude/skills
  if command -v npx >/dev/null 2>&1; then
    echo "install: installing $REPO with npx $SKILLS_CLI"
    npx --yes "$SKILLS_CLI" add "$REPO" --agent claude-code -y </dev/null
  elif command -v git >/dev/null 2>&1; then
    echo "install: npx not found; cloning https://github.com/$REPO.git"
    git clone --depth 1 "https://github.com/$REPO.git" "$DEST"
    rm -rf "$DEST/.git"
  else
    echo "install: neither npx nor git found; install one of them (Node from https://nodejs.org, or git), then run this again" >&2
    exit 2
  fi
  [ -f "$DEST/SKILL.md" ] || { echo "install: the skill did not arrive in $DEST (a private repository needs a GitHub login: gh auth login, or an SSH key)" >&2; exit 1; }
fi

echo "install: running setup"
"$PYTHON" "$DEST/scripts/init.py"
