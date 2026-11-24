"""Spacing of text measured on rasters: line bands, word boxes and the letter pitch of a line.

Both sides (the PDF page and the lab sheet) are rasterised at the same zoom and measured by the same code, so the numbers are comparable even
though the typefaces differ. Everything is in points.

- bands: the lines of a text column, from the rows that hold ink; gives each line's top and bottom, so line pitch and line height can be compared.
- words: the ink boxes of the words of one line (columns of ink separated by a gap wider than a letter gap): word widths and the width of the spaces.
- pitch: the letter pitch of a line, from the autocorrelation of its column profile; a proportional face has a fixed syllable advance, and the
  profile repeats at that advance.
"""
from __future__ import annotations

import numpy as np

ZOOM = 12


def text_mask(image: np.ndarray, kind: str = "text") -> np.ndarray:
    """Ink of black or grey text: dark and neutral pixels (frames are green, so they drop out)."""
    spread = image.max(axis=2) - image.min(axis=2)
    lum = image @ np.array([0.299, 0.587, 0.114])
    if kind == "caption":
        return (lum < 215) & (spread < 40)
    return (lum < 175) & (spread < 40)


def runs(flags: np.ndarray, min_gap: int) -> list[tuple[int, int]]:
    """Index runs of True separated by at least `min_gap` False entries."""
    indexes = np.where(flags)[0]
    if indexes.size == 0:
        return []
    out: list[tuple[int, int]] = []
    start = previous = int(indexes[0])
    for index in indexes[1:]:
        if index - previous > min_gap:
            out.append((start, previous + 1))
            start = int(index)
        previous = int(index)
    out.append((start, previous + 1))
    return out


def bands(mask: np.ndarray, min_gap_pt: float = 0.8, min_ink_px: int = 6) -> list[tuple[float, float]]:
    """Lines of a column: (top, bottom) in points of every run of rows that hold ink, separated by blank rows of at least `min_gap_pt`."""
    rows = mask.sum(axis=1) >= min_ink_px
    return [(a / ZOOM, b / ZOOM) for a, b in runs(rows, int(min_gap_pt * ZOOM))]


def words(mask: np.ndarray, min_gap_pt: float = 2.0) -> list[tuple[float, float]]:
    """Word boxes of one line: (x0, x1) in points of the ink columns separated by a gap wider than `min_gap_pt` (a space, not a letter gap)."""
    columns = mask.sum(axis=0) > 0
    return [(a / ZOOM, b / ZOOM) for a, b in runs(columns, int(min_gap_pt * ZOOM))]


def _pooled_autocorrelation(mask: np.ndarray, max_lag_pt: float = 45.0) -> np.ndarray | None:
    """Autocorrelation of the column profile of every text line, summed: lags in pixels from 0 to `max_lag_pt`. The bottom quarter of each line
    is left out, where the answer rules run into the words."""
    size = int(max_lag_pt * ZOOM)
    total = np.zeros(size)
    lines = 0
    for top, bottom in bands(mask):
        rows = mask[int(top * ZOOM) : int((top + 0.75 * (bottom - top)) * ZOOM)]
        profile = rows.sum(axis=0).astype(float)
        if profile.size < int(60 * ZOOM):
            continue
        profile -= profile.mean()
        correlation = np.correlate(profile, profile, mode="full")[profile.size - 1 : profile.size - 1 + size]
        if correlation[0] == 0:
            continue
        total[: correlation.size] += correlation
        lines += 1
    return total / total[0] if lines else None


def pitch(mask: np.ndarray, lo_pt: float = 8.0, hi_pt: float = 12.5, harmonics: int = 1) -> dict[str, float] | None:
    """Letter pitch of a text block in points, and the median gap of its word spaces.

    Hangul syllables are not separable by ink gaps (the strokes of one syllable are as far apart as two syllables), so the pitch is the period of the
    column profile: the autocorrelation of every line, pooled, peaks at one pitch. Only the first peak is used: higher peaks (2, 3, 4 pitches) reach
    across word spaces, which are not periodic, and bias the result upwards (by 4% at four harmonics). Checked on the lab against the exact advance
    read from the DOM: 10.665 and 10.750 against 10.669 pt (within 1%); the estimate needs a few lines of text and is not for single lines.
    `space_gap` is the median ink gap between words, taken from the gaps of 3.5 to 12 pt (a letter gap is smaller, a column gap larger).
    """
    correlation = _pooled_autocorrelation(mask)
    if correlation is None:
        return None
    best_score, best = -1e9, lo_pt
    for candidate in np.arange(lo_pt, hi_pt, 0.005):
        score = 0.0
        for k in range(1, harmonics + 1):
            position = candidate * k * ZOOM
            index = int(position)
            if index + 1 >= correlation.size:
                break
            fraction = position - index
            score += correlation[index] * (1 - fraction) + correlation[index + 1] * fraction
        if score > best_score:
            best_score, best = score, float(candidate)
    gaps: list[float] = []
    for top, bottom in bands(mask):
        rows = mask[int(top * ZOOM) : int((top + 0.75 * (bottom - top)) * ZOOM)]
        found = words(rows, 0.6)
        gaps.extend(b[0] - a[1] for a, b in zip(found, found[1:]) if 3.5 <= b[0] - a[1] < 12.0)
    return {"pitch": best, "space_gap": float(np.median(gaps)) if gaps else float("nan"), "space_samples": float(len(gaps))}
