#!/usr/bin/env python3
"""Stop hook: do not let a session end while a PDF-to-ebook build (skill pdf-to-ui-replica) has pages IN_PROGRESS, a VERIFIED page that no longer passes,
or an unresolved P0/P1 issue. It only fires when `<output>/ebook-state.json` exists (default output: pdf-to-ui-output/ at the repo root, or the folder in
$PDF_TO_UI_OUTPUT). Blocks with the list of problems; gives up after MAX_BLOCKS reminders per session. A build that is truly blocked runs
`python3 -m pdfmeasure state block --output O --reason "..."` (from the skill's scripts/ folder), which also lets the session stop.
Logic lives in the skill (scripts/pdfmeasure/ebook_state.py); this file only wires it to the Stop event."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

MAX_BLOCKS = 4
SKILL_SCRIPTS = Path('.claude/skills/pdf-to-ui-replica/scripts')  # fallback when the hook is not inside the skill folder
OWN_SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'  # the skill's own scripts: this hook lives in <skill>/hooks/


def main() -> int:
    payload = json.loads(sys.stdin.read() or '{}')
    cwd = Path(payload.get('cwd') or '.')
    top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=cwd, capture_output=True, text=True, check=False).stdout.strip()
    root = Path(top or cwd)
    output = Path(os.environ.get('PDF_TO_UI_OUTPUT') or root / 'pdf-to-ui-output')
    if not (output / 'ebook-state.json').exists():
        return 0
    sys.path.insert(0, str(OWN_SCRIPTS if (OWN_SCRIPTS / 'pdfmeasure').is_dir() else root / SKILL_SCRIPTS))
    from pdfmeasure.ebook_state import EbookState  # noqa: E402

    problems = EbookState(output).stop_problems()
    if not problems:
        return 0
    counter = Path('/tmp') / f'ebook-gate-{payload.get("session_id", "x")}.count'
    blocks = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(blocks))
    if blocks > MAX_BLOCKS:
        print(f'ebook gate: still unsettled after {MAX_BLOCKS} reminders, letting the session stop', file=sys.stderr)
        return 0
    lines = ['Bản dựng ebook chưa xong, chưa được dừng hay báo hoàn thành (skill pdf-to-ui-replica, references/10-harness.md). Còn lại:']
    lines += [f'  • {item}' for item in problems[:12]] + ([f'  • ... và {len(problems) - 12} mục nữa'] if len(problems) > 12 else [])
    lines += ['Sửa trong cùng lượt rồi chạy lại visual-compare, `state view`, `state page`; trang không thể xong thì `state page --status BLOCKED|ACCEPTED_LIMITATION --reason ...`.',
              'Chỉ khi cả bản dựng thật sự bị chặn mới chạy `state block --reason "..."` rồi dừng, và nói rõ blocker trong báo cáo.']
    print(json.dumps({'decision': 'block', 'reason': '\n'.join(lines)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
