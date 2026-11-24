# Visual QA report: run-1

Pages in scope: 10

## Verdict

No unresolved P0/P1 issue; 0 P2/P3 issue(s) remain listed below with their status. (Pixel numbers never decide this; inventory and verify results still apply.)

## Pictures

### Page 10
- ![heatmap-v0.png](pages/page-010/heatmap-v0.png)
- ![heatmap-v1.png](pages/page-010/heatmap-v1.png)
- ![heatmap-v2.png](pages/page-010/heatmap-v2.png)
- ![heatmap-v3.png](pages/page-010/heatmap-v3.png)
- ![heatmap-v4.png](pages/page-010/heatmap-v4.png)
- ![heatmap-v5.png](pages/page-010/heatmap-v5.png)
- ![overlay-v0.png](pages/page-010/overlay-v0.png)
- ![overlay-v1.png](pages/page-010/overlay-v1.png)
- ![overlay-v2.png](pages/page-010/overlay-v2.png)
- ![overlay-v3.png](pages/page-010/overlay-v3.png)
- ![overlay-v4.png](pages/page-010/overlay-v4.png)
- ![overlay-v5.png](pages/page-010/overlay-v5.png)
- ![pdf-vs-v0.png](pages/page-010/pdf-vs-v0.png)
- ![pdf-vs-v1.png](pages/page-010/pdf-vs-v1.png)
- ![pdf-vs-v2.png](pages/page-010/pdf-vs-v2.png)
- ![pdf-vs-v3.png](pages/page-010/pdf-vs-v3.png)
- ![pdf-vs-v4.png](pages/page-010/pdf-vs-v4.png)
- ![pdf-vs-v5.png](pages/page-010/pdf-vs-v5.png)
- ![triptych.png](pages/page-010/triptych.png)
- [scan-v5.md](pages/page-010/scan-v5.md) (every region and failing entry of that scan)

## Issues

| Issue ID | Page/Object | Severity | Description | Before | After | Status | Codex prompt |
|---|---|---|---|---|---|---|---|
| ISS-001 | 10 / OBJ-002 | P2 | Heading bubble ends about 16 pt further right than the printed one (right 262.8 vs 246.8 pt); title ink 8.7 pt wider (parentheses and hyphen wider, word gaps 10 pt vs 5 pt) | [region-08.png](pages/page-010/crops/v0/region-08.png) | [region-08.png](pages/page-010/crops/v5/region-08.png) | VERIFIED | - |
| ISS-002 | 10 / OBJ-002 | P3 | Printed heading face is bolder with heavier strokes than the fallback face | - | - | ACCEPTED_LIMITATION | - |
| ISS-003 | 10 / OBJ-001 | P3 | Heading portrait is an original drawing, not the printed character | [region-07.png](pages/page-010/crops/v0/region-07.png) | - | ACCEPTED_LIMITATION | - |

## Counts

| Severity | OPEN | FIXING | NEEDS_VERIFY | VERIFIED | CODEX_READY | CODEX_RUNNING | BLOCKED | ACCEPTED_LIMITATION |
|---|---|---|---|---|---|---|---|---|
| P0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P2 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| P3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |

## Fixed and confirmed

- ISS-001: Heading bubble ends about 16 pt further right than the printed one (right 262.8 vs 246.8 pt); title ink 8.7 pt wider (parentheses and hyphen wider, word gaps 10 pt vs 5 pt)

## Regressions (verified earlier, open again)

- none

## New after the repair

- ISS-002: Printed heading face is bolder with heavier strokes than the fallback face
- ISS-003: Heading portrait is an original drawing, not the printed character

## Still open and why

- none

## Accepted limitations

- ISS-002: Font waiver (owner): the rounded bold heading face is not available
- ISS-003: By design: printed characters are copyrighted and are redrawn originally

## Progress against the PDF (V0 to V1)

- page 10: different pixels 0.05653 to 0.05529; improved 1, unchanged 65, worse 0, new regions 1

## Codex

- no handoff in this run

## Geometry and zoom verify

- geometry (page 10): 8 of 8 metrics within tolerance (incl. bubble right edge, bubble width)
- zoom (page 10): 7 of 7 parts match (incl. bubble-title-ink)

## Not verified

- Page text differs by design (original fixtures); illustrations are original artwork
