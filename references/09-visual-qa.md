# Visual QA, repair loop and Codex handoff (after the page is built)

Flow: **Visual QA → Defect triage → Repair → Regression comparison → Codex handoff → Report and cleanup.**
Geometry/zoom `verify` (phases 7–8) is unchanged and still decides what it measures. This stage adds whole-page eyes and a defect record. Pixel numbers (different-pixel share, regions) only say *where to look*: they never give PASS/FAIL. Anti-aliasing, fonts and artwork differ by nature; you judge.

## Folders
```
<output>/                      kept: report.md issues.json issues.md pages/page-NNN/{pdf,react-v0,react-v1,pdf-vs-v0,triptych,overlay-*,heatmap-*}.png crops/ metrics-*.json progress.json
                               codex-prompts/*.md  codex-results/execution.md  logs/
<root>/.tmp/pdf-to-ui/<run-id>/ deleted at the end of the run: intermediate/ cache/ working-images/
```
`<output>` is git-ignored (`pdf-to-ui-output/` is in the root `.gitignore`): it holds page images of the book. Never commit it.

## Commands (from `scripts/`, `PYTHONPATH=. python3 -m pdfmeasure …`)
| Step | Command |
|---|---|
| start | `qa-start --output O --root .` → run id and temp dir |
| capture + compare | `visual-compare --pdf X --page N --output O --label v0 --url LAB_URL --sheet K --zoom 3 --run-dir TMP [--verify-config verify.json] [--crop-limit 40]` (or `--react-image file.png`) |
| record a defect | `issue add --output O --run run-0 --page N --object OBJ-003 --type shape --severity P1 --region x,top,w,h --description … --evidence pages/page-001/crops/v0/region-01.png --cause …` |
| change status | `issue status --output O --run run-1 --id ISS-003 --status NEEDS_VERIFY --note … [--evidence …]` |
| after repair | `visual-compare … --label v1` (also writes `triptych.png` PDF | V0 | V1 and `progress.json`), then `issue note-run` |
| hand over | `codex-prompt --output O --issues ISS-003[,ISS-004] --context ctx.json`, then `codex-run --output O --cwd REPO` |
| report | `qa-report --output O --run run-1 --baseline-run run-0 --pages N… --verify verify-summary.json --codex-info --unverified "…"` |
| end | `qa-finish --output O --run-id ID --run-dir DIR [--failed --log "…"]` |

## One pass gives the whole error report
Do not run the comparison again and again to discover errors. `visual-compare` writes `pages/page-NNN/scan-<label>.md`: every different region (largest first, box in pt, shape hint, crop link), registration warnings, progress against V0, and, with `--verify-config verify.json`, the failing geometry/zoom entries of the same page from the same run. Read that one file, look at the crops, search the knowhow register for each defect (`knowhow search "<symptom words>"`), then record all real defects together with `issue add-batch --file triage.json` (JSON list of `{page, description, region, type, severity, object?, evidence?, cause?, fix?, knowhow?}`), fix them together, and scan again once to confirm. The scan also runs the text-layout check (left edges, tops, bottoms, line pitch, missing/extra lines) and lists its failures with the others: a wrong indent or line spacing is a defect to fix in the same run (a whole wrong block is P1). Regions that appear only in V1 under 60 pt² of different ink are noted, not counted as regression.

## Detail pass: tiles (after the scan, before `state view`)
The scan locates differences at 3 px/pt and its crops are that same resolution enlarged; a whole-page picture shrinks again when it is shown. Details (numbered circles, arrowheads, dotted guides, stroke weight and taper, small text) are judged on `tiles --mode pair --pdf X --page N --output O --url LAB_URL --sheet K`: PDF | rebuilt, both re-rendered at ≥ 6 px/pt, one picture per non-blank tile with its box in pt. Look at every tile and write the differences you find into the triage (`issue add-batch`), then `state view --tiles-file notes.json` (one observation per tile). Tiles older than the latest scan are rejected by the harness.

## Rules for visual-compare
- PDF page and React sheet are captured at the same px/pt. If their sizes differ by more than 2 px the command exits 2 with `size_mismatch`, writes only the side-by-side and compares **nothing**: fix the page box or sheet size, never resize to hide it.
- A global shift above 0.75 pt is reported as a registration/geometry problem, not as many local ones.
- Look at: `pdf-vs-v0.png` (whole page), `heatmap-v0.png` (numbered regions), `crops/v0/region-NN.png` (PDF | React, enlarged; up to `--crop-limit` regions, default 40), then decide.

## Defect record (`issues.json`)
Fields: ID (`ISS-001`, stable), page, object_id (link to `object-inventory.md`), type, severity, description, region (pt), status, evidence, cause, fix_plan, codex_prompt, history (one line per run).
- Same unresolved defect (same page, object, type, overlapping region) is never given a second ID; a regression reopens the same ID.
- Severity is your judgement from the original and the goal, not from pixel area: **P0** missing important object / wrong content / broken structure; **P1** clearly different shape, layout, proportion, character, frame or decoration; **P2** local detail (spacing, curvature, colour, stroke, small size); **P3** cosmetic.
- Status: `OPEN → FIXING → NEEDS_VERIFY → VERIFIED`; also `CODEX_READY`, `CODEX_RUNNING`, `BLOCKED`, `ACCEPTED_LIMITATION` (needs a reason). `VERIFIED` is allowed only from `NEEDS_VERIFY` and needs image evidence of the fix; an improved number alone is not evidence.

## Loop (repair is part of the task)
Findings from Run 0 are fixed in the same session; a report that only lists defects, or only hands them to Codex, is not a finished build. Each fixed defect gets a measured check or zoom part so the repair is guarded.
- **Run 0**: capture V0, compare, look, record defects, order P0 → P3.
- **Run 1**: fix what React/CSS/SVG/tokens can fix; capture V1; read `triptych.png` and `progress.json` (improved / unchanged / worse / new regions; `regression: true` means stop and look); update statuses; check for new defects.
- A fix that did not hold counts as a failed round; at the cap (default 3) the issue becomes `CODEX_READY` (with a cause) or `BLOCKED` and cannot go back to `FIXING` without `--reset-rounds <reason>` ([10-harness.md](10-harness.md)).
- More rounds only while P0/P1 remain and each round makes progress. Never random tries, never a looser tolerance to get a green.
- Keep at least the baseline and the final snapshot.

## Knowhow after the fix
A defect that matched an entry: `knowhow seen --id KH-nnn --build <book>`. A fixed defect that is general and has no entry: `knowhow add --file entry.json`. `qa-report` lists both groups (section "Knowhow"). See SKILL.md, "Knowhow register".

## Codex handoff (only for hard defects)
Hand over a defect only when you have a technical cause or concrete hypothesis and a clear task. `codex-prompt` refuses an issue without a cause and a context missing any of: goal, object_description, evidence, cause, source_files, approach, constraints, acceptance, commands, allowed_files (also give `measures`). One file per defect: `codex-prompts/p<page>-obj<id>-issue<n>.md`; tightly linked issues may share one prompt that lists every ID (`-group`).
`codex-run` checks the CLI itself:
1. `codex` on PATH and `codex exec --help` works and shows a PROMPT argument; resume is used only if `codex exec resume --help` works and shows `--last`. Syntax is never guessed.
2. Resume works → prompts run in one session in turn; otherwise they are merged into one run. Prompt, exit code and session reference are written to `codex-results/execution.md`.
3. Codex missing or unusable → exit 3, prompts kept, issues stay `CODEX_READY`, `execution.md` says **NOT run** and how to run them by hand. Never claim Codex ran when it did not.
4. A finished run moves the issues to `NEEDS_VERIFY`, not `VERIFIED`: re-capture, `visual-compare --label v2`, verify, then decide.

## Report and cleanup
`qa-report` writes `report.md`: verdict, pictures, issue table (Issue ID | Page/Object | Severity | Description | Before | After | Status | Codex prompt), counts by severity and status, fixed, regressions, new after repair, still open and why, accepted limitations, progress V0→V1, Codex state, geometry/zoom results, not verified. Do not call a page complete with an unresolved P0/P1 (the report says NOT complete); P2/P3 stay listed with status and reason.
`qa-finish` removes only `<root>/.tmp/pdf-to-ui/<run-id>/` after checking its parent, its name, its marker file, that it is not a symlink and that the output folder is not inside it. A failed run (`--failed`) first saves its log in `<output>/logs/`. Evidence, report, issues and prompts are never deleted.

## Which modes run it
Inventory/analysis only: no QA stage, no repair, no Codex. Build a page: QA is mandatory before saying it is done. Review an existing page: `visual-compare` + triage + report; repair only if the task allows it.
