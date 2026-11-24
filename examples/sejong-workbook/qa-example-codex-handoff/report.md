# Visual QA report: run-0

Pages in scope: 10

## Verdict

No unresolved P0/P1 issue; 1 P2/P3 issue(s) remain listed below with their status. (Pixel numbers never decide this; inventory and verify results still apply.)

## Pictures

### Page 10
- ![pdf-vs-v0.png](pages/page-010/pdf-vs-v0.png)
- ![overlay-v0.png](pages/page-010/overlay-v0.png)
- ![heatmap-v0.png](pages/page-010/heatmap-v0.png)

## Issues

| Issue ID | Page/Object | Severity | Description | Before | After | Status | Codex prompt |
|---|---|---|---|---|---|---|---|
| ISS-001 | 10 / OBJ-002 | P2 | Heading bubble ends about 16 pt further right than the printed one (right end near x 263 pt vs 247 pt) | [region-08.png](pages/page-010/crops/v0/region-08.png) | - | CODEX_READY | [p010-obj002-issue001.md](codex-prompts/p010-obj002-issue001.md) |
| ISS-002 | 10 / OBJ-001 | P3 | Heading portrait is an original drawing, not the printed character | [region-07.png](pages/page-010/crops/v0/region-07.png) | - | ACCEPTED_LIMITATION | - |

## Counts

| Severity | OPEN | FIXING | NEEDS_VERIFY | VERIFIED | CODEX_READY | CODEX_RUNNING | BLOCKED | ACCEPTED_LIMITATION |
|---|---|---|---|---|---|---|---|---|
| P0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P2 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| P3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |

## Fixed and confirmed

- none

## Regressions (verified earlier, open again)

- none

## New after the repair

- none

## Still open and why

- ISS-001 (P2, CODEX_READY): Hypothesis: the bubble width follows the text width and the fallback heading face is wider than the printed rounded face; the printed bubble has a fixed measured width.

## Accepted limitations

- ISS-002: By design: the printed characters are copyrighted and are redrawn originally

## Codex

- CLI: NOT available: the `codex` executable is not on PATH
- prompt: [p010-obj002-issue001.md](codex-prompts/p010-obj002-issue001.md)
- executed: NO (prompts kept, issues stay CODEX_READY)

## Geometry and zoom verify

- geometry (page 10): 6 of 6 metrics within tolerance (verify run, earlier commit)
- zoom (page 10): 6 of 6 parts match

## Not verified

- Heading font face (waived), illustrations (original artwork), V1 repair not run in this example
