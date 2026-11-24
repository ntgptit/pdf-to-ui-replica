# Scan: page 10, v5

- status: **needs_review**; different pixels: 0.0553; global shift (pt): +0.00, +0.00
- against V0: different pixels 0.05653 to 0.05529; improved 1, unchanged 65, worse 0, new 1
  - new: region 68 [213.0, 117.0, 6.0, 6.0] (0.034)

## Regions to triage (largest first). Look at each crop, then record the real defects with `issue add` or `issue add-batch`.

| # | Box [x, top, w, h] pt | Different | Hint | Crop |
|---|---|---|---|---|
| 1 | [90.0, 375.0, 372.0, 72.0] | 0.30 | large area (picture, table, frame) | [region-01.png](crops/v5/region-01.png) |
| 2 | [90.0, 174.0, 372.0, 51.0] | 0.11 | large area (picture, table, frame) | [region-02.png](crops/v5/region-02.png) |
| 3 | [0.0, 51.0, 533.0, 12.0] | 0.25 | large area (picture, table, frame) | [region-03.png](crops/v5/region-03.png) |
| 4 | [90.0, 342.0, 234.0, 27.0] | 0.22 | large area (picture, table, frame) | [region-04.png](crops/v5/region-04.png) |
| 5 | [105.0, 585.0, 360.0, 45.0] | 0.06 | large area (picture, table, frame) | [region-05.png](crops/v5/region-05.png) |
| 6 | [90.0, 141.0, 162.0, 15.0] | 0.34 | text or detail | [region-06.png](crops/v5/region-06.png) |
| 7 | [72.0, 573.0, 30.0, 33.0] | 0.54 | solid block (fill or picture) | [region-07.png](crops/v5/region-07.png) |
| 8 | [60.0, 78.0, 39.0, 36.0] | 0.38 | text or detail | [region-08.png](crops/v5/region-08.png) |
| 9 | [108.0, 297.0, 123.0, 12.0] | 0.35 | text or detail | [region-09.png](crops/v5/region-09.png) |
| 10 | [132.0, 87.0, 93.0, 27.0] | 0.20 | large area (picture, table, frame) | [region-10.png](crops/v5/region-10.png) |
| 11 | [357.0, 36.0, 129.0, 12.0] | 0.30 | text or detail | [region-11.png](crops/v5/region-11.png) |
| 12 | [108.0, 237.0, 120.0, 12.0] | 0.31 | text or detail | [region-12.png](crops/v5/region-12.png) |
| 13 | [90.0, 159.0, 219.0, 9.0] | 0.21 | text or detail | [region-13.png](crops/v5/region-13.png) |
| 14 | [108.0, 267.0, 354.0, 12.0] | 0.10 | large area (picture, table, frame) | [region-14.png](crops/v5/region-14.png) |
| 15 | [372.0, 684.0, 114.0, 9.0] | 0.36 | text or detail | [region-15.png](crops/v5/region-15.png) |
| 16 | [159.0, 183.0, 81.0, 12.0] | 0.25 | text or detail | [region-16.png](crops/v5/region-16.png) |
| 17 | [120.0, 261.0, 333.0, 3.0] | 0.22 | rule / line | [region-17.png](crops/v5/region-17.png) |
| 18 | [279.0, 615.0, 78.0, 12.0] | 0.22 | text or detail | [region-18.png](crops/v5/region-18.png) |
| 19 | [123.0, 540.0, 66.0, 12.0] | 0.25 | text or detail | [region-19.png](crops/v5/region-19.png) |
| 20 | [123.0, 486.0, 66.0, 15.0] | 0.18 | text or detail | [region-20.png](crops/v5/region-20.png) |
| 21 | [192.0, 486.0, 54.0, 15.0] | 0.22 | text or detail | [region-21.png](crops/v5/region-21.png) |
| 22 | [267.0, 180.0, 42.0, 15.0] | 0.25 | text or detail | [region-22.png](crops/v5/region-22.png) |
| 23 | [192.0, 540.0, 54.0, 12.0] | 0.23 | text or detail | [region-23.png](crops/v5/region-23.png) |
| 24 | [105.0, 615.0, 63.0, 12.0] | 0.19 | text or detail | [region-24.png](crops/v5/region-24.png) |
| 25 | [99.0, 87.0, 30.0, 18.0] | 0.26 | text or detail | [region-25.png](crops/v5/region-25.png) |
| 26 | [261.0, 414.0, 54.0, 9.0] | 0.27 | text or detail | [region-26.png](crops/v5/region-26.png) |
| 27 | [129.0, 324.0, 333.0, 12.0] | 0.03 | large area (picture, table, frame) | [region-27.png](crops/v5/region-27.png) |
| 28 | [243.0, 180.0, 21.0, 15.0] | 0.36 | text or detail | [region-28.png](crops/v5/region-28.png) |
| 29 | [120.0, 291.0, 333.0, 3.0] | 0.11 | rule / line | [region-29.png](crops/v5/region-29.png) |
| 30 | [120.0, 321.0, 333.0, 3.0] | 0.11 | rule / line | [region-30.png](crops/v5/region-30.png) |
| 31 | [123.0, 474.0, 330.0, 3.0] | 0.11 | rule / line | [region-31.png](crops/v5/region-31.png) |
| 32 | [123.0, 525.0, 330.0, 3.0] | 0.11 | rule / line | [region-32.png](crops/v5/region-32.png) |
| 33 | [138.0, 600.0, 57.0, 9.0] | 0.21 | text or detail | [region-33.png](crops/v5/region-33.png) |
| 34 | [318.0, 414.0, 27.0, 9.0] | 0.32 | text or detail | [region-34.png](crops/v5/region-34.png) |
| 35 | [279.0, 597.0, 21.0, 12.0] | 0.31 | text or detail | [region-35.png](crops/v5/region-35.png) |
| 36 | [303.0, 600.0, 39.0, 9.0] | 0.20 | text or detail | [region-36.png](crops/v5/region-36.png) |
| 37 | [105.0, 597.0, 30.0, 12.0] | 0.19 | text or detail | [region-37.png](crops/v5/region-37.png) |
| 38 | [108.0, 183.0, 18.0, 12.0] | 0.23 | text or detail | [region-38.png](crops/v5/region-38.png) |
| 39 | [75.0, 342.0, 9.0, 12.0] | 0.39 | mark / glyph | [region-39.png](crops/v5/region-39.png) |
| 40 | [90.0, 294.0, 12.0, 15.0] | 0.23 | text or detail | [region-40.png](crops/v5/region-40.png) |
| 41 | [90.0, 234.0, 12.0, 15.0] | 0.21 | text or detail | (no crop: over the limit, see heatmap) |
| 42 | [339.0, 36.0, 15.0, 12.0] | 0.21 | text or detail | (no crop: over the limit, see heatmap) |
| 43 | [108.0, 465.0, 12.0, 12.0] | 0.19 | mark / glyph | (no crop: over the limit, see heatmap) |
| 44 | [108.0, 516.0, 12.0, 12.0] | 0.19 | mark / glyph | (no crop: over the limit, see heatmap) |
| 45 | [90.0, 264.0, 12.0, 15.0] | 0.15 | text or detail | (no crop: over the limit, see heatmap) |
| 46 | [90.0, 516.0, 12.0, 12.0] | 0.19 | mark / glyph | (no crop: over the limit, see heatmap) |
| 47 | [108.0, 540.0, 12.0, 12.0] | 0.18 | mark / glyph | (no crop: over the limit, see heatmap) |
| 48 | [108.0, 489.0, 12.0, 12.0] | 0.18 | mark / glyph | (no crop: over the limit, see heatmap) |
| 49 | [90.0, 465.0, 12.0, 12.0] | 0.17 | mark / glyph | (no crop: over the limit, see heatmap) |
| 50 | [474.0, 126.0, 12.0, 15.0] | 0.09 | text or detail | (no crop: over the limit, see heatmap) |
| 51 | [72.0, 141.0, 9.0, 12.0] | 0.15 | mark / glyph | (no crop: over the limit, see heatmap) |
| 52 | [57.0, 645.0, 12.0, 12.0] | 0.11 | mark / glyph | (no crop: over the limit, see heatmap) |
| 53 | [57.0, 126.0, 12.0, 15.0] | 0.08 | text or detail | (no crop: over the limit, see heatmap) |
| 54 | [108.0, 252.0, 12.0, 9.0] | 0.14 | mark / glyph | (no crop: over the limit, see heatmap) |
| 55 | [108.0, 282.0, 12.0, 9.0] | 0.14 | mark / glyph | (no crop: over the limit, see heatmap) |
| 56 | [108.0, 312.0, 12.0, 9.0] | 0.14 | mark / glyph | (no crop: over the limit, see heatmap) |
| 57 | [114.0, 432.0, 9.0, 9.0] | 0.17 | mark / glyph | (no crop: over the limit, see heatmap) |
| 58 | [456.0, 252.0, 6.0, 9.0] | 0.20 | mark / glyph | (no crop: over the limit, see heatmap) |
| 59 | [456.0, 282.0, 6.0, 9.0] | 0.20 | mark / glyph | (no crop: over the limit, see heatmap) |
| 60 | [456.0, 312.0, 6.0, 9.0] | 0.20 | mark / glyph | (no crop: over the limit, see heatmap) |
| 61 | [456.0, 516.0, 6.0, 12.0] | 0.15 | mark / glyph | (no crop: over the limit, see heatmap) |
| 62 | [114.0, 414.0, 6.0, 9.0] | 0.20 | mark / glyph | (no crop: over the limit, see heatmap) |
| 63 | [456.0, 465.0, 6.0, 9.0] | 0.19 | mark / glyph | (no crop: over the limit, see heatmap) |
| 64 | [111.0, 327.0, 9.0, 6.0] | 0.18 | mark / glyph | (no crop: over the limit, see heatmap) |
| 65 | [234.0, 84.0, 12.0, 21.0] | 0.03 | text or detail | (no crop: over the limit, see heatmap) |
| 66 | [135.0, 189.0, 9.0, 9.0] | 0.04 | mark / glyph | (no crop: over the limit, see heatmap) |
| 67 | [57.0, 105.0, 6.0, 6.0] | 0.03 | mark / glyph | (no crop: over the limit, see heatmap) |
| 68 | [213.0, 117.0, 6.0, 6.0] | 0.03 | mark / glyph | (no crop: over the limit, see heatmap) |

## Failing geometry / zoom entries (same run)

- verify ran (exit 0); every entry within tolerance

Text and artwork regions usually differ by design (fonts, original drawings): judge from the crops, severity is yours.
