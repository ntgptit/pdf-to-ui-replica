# QA example: baseline, repair and verification on page 10 (one scan, one report)

Text outputs only (the images contain the printed book and are not committed).
- `scan-v5.md`: the single report that `visual-compare --verify-config` produced: every different region with its crop, progress against V0, and failing geometry/zoom entries.
- `issues.json` / `issues.md`: ISS-001 (heading bubble 16 pt too wide) went OPEN → FIXING → NEEDS_VERIFY → VERIFIED after the repair (bubble width/start hints, narrower punctuation, word and letter spacing from the PDF ink positions); ISS-002/003 are accepted limitations with reasons.
- `report.md`: the run report. New geometry checks (bubble right edge, bubble width) and a zoom part (title ink) now guard the fix.
See `../qa-example-codex-handoff/` (an earlier baseline run of the same page) for a Codex prompt and the "Codex NOT run" record.
