# Example: Sejong Korean 4A workbook

Real configs from the run that produced this skill (the PDF itself is not included: copyrighted).
- `roles.json` 16 roles (tab, hatch ground/bitmap, card, fold, bubble stroke/fill/tail/shadow, frames, …) with palette variables.
- `quantities.json` 26 invariants across 39 pages. `checks-p9/10/11/13.json`, `parts-p9/10/11/13.json`, `verify.json` for four page types.
- Result: geometry 22/22, 6/6, 11/11, 6/6; zoom 28/28, 6/6, 14/14, 5/5.
- Key measured numbers: card 48.52/128.27, 427.1×527.09, r13.5, stroke 1.2; bubble body 24.48 + tail 7.64; hatch visible band 53.86–62.37 (period 5.88 pt at 45°); frame r5.23 stroke 0.46; body letter pitch 10.08; item pitch 29.3.
- The rebuild this run produced used an earlier layout with inline geometry; paths in `qa-example-codex-handoff/` are historical. New builds follow `references/14-module-layout.md`.
To reuse: copy and adapt `roles.json` first, rerun phases 2–8 for your PDF.
