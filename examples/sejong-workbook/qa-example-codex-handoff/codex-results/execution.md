# Codex execution

**Codex was NOT run.**

Reason: the `codex` executable is not on PATH

The prompts are kept and their issues stay `CODEX_READY`. To run them by hand, open Codex in the repository and give it each file:

- `codex-prompts/p010-obj002-issue001.md`

With the CLI installed: `codex exec "$(cat <prompt file>)"` (check `codex exec --help` for your version). Then re-capture and verify; a finished Codex run does not mean the defect is fixed.
