# QA example (one real baseline run, page 10)

Text outputs of `qa-start`, `visual-compare --label v0`, `issue add/status`, `codex-prompt`, `codex-run`, `qa-report`, `qa-finish` on the Sejong lab page.
- The image files the report links to (PDF render, overlay, heatmap, crops) are not committed: they contain the printed book. Run the commands to regenerate them.
- The two issues are an illustration of the record and the Codex handoff (the bubble-width defect would normally be fixed by the agent itself); they are not a claim about the final state of the page.
- Codex CLI was not installed in that environment, so `execution.md` says it was NOT run and the issue stays `CODEX_READY`.
