# Config file reference (JSON)

All numbers are PDF points. Colours are `#rrggbb` (sRGB after CMYK conversion).

## roles.json — list of rules
`role` (name), `kind` (`rect|curve|line|image|glyph`), `fill`, `stroke` (hex or `"any"`), `tolerance` (per channel, default small), `linewidth`, `width`, `height`, `x0`, `x1`, `top`, `bottom` (each `[min,max]`, `null` = open), `sides` (`["left"]` / `["right"]`), `pages`, `palette` (custom property name to emit), `palette_from` (`fill|stroke`).

## quantities.json — list for `report`
`{name, role, field, pick: first|min|max, sides: both|left|right}`; fields `x0 x1 top bottom width height linewidth corner_radius`.

## checks-pN.json — list for `compare`
```
{ "name": "...", "tolerance": 0.3,
  "pdf": {"role": "card", "field": "top", "index": 0},      // or "expect": 14.1 | "#45a665"
  "dom": {"id": "card", "field": "y", "index": 0}            // or {"id","path":"style.borderRadius","unit":"px"|"colour"}
  "offset_from": {...}                                        // optional: measure relative to another element
}
```
DOM fields: `x y w h right bottom`; `path` walks `style.*`, `frame.*` (svg rect), `before.*`.

## parts-pN.json — list for `zoom`
`{name, box:[x,top,w,h] (whole pt), method: align|extent|ink|line|lines|words|columns|pitch, colour: "#hex"|"ink"|"any"|"text"|"caption", tolerance_shift (0.5), tolerance_thickness (0.15), thickness (true), centre (false), spacing (0.35), min_overlap (0.7, align only), tolerance_colour (10, hex colours)}`.

## verify.json — drives everything
```
{ "title", "url", "attr": "data-wb", "sheet_selector": "[data-wb=\"sheet\"]" (optional),
  "rules": "roles.json", "first_side": "left", "geometry_css_per_pt": 8 (optional), "zoom": 12, "css_per_pt": 8,
  "pages": [ {"pdf_page": 9, "sheet": 0, "checks": "checks-p9.json", "parts": "parts-p9.json"} ] }
// each page needs checks, parts AND text_layout (e.g. "text_layout": {}), or "skip": {"<layer>": "reason"}; not all three
// text_layout keys: tolerance_left 0.5, tolerance_vertical 0.5, tolerance_pitch 0.3, regions [[x, top, w, h]], colours ["#hex"], zoom 6, gap_pt 3.5
```
Paths are relative to the verify.json. `sheet` is the index of the sheet element on the lab page for that PDF page.

## Commands
`text-layout`, `shapes`, `signatures`, `lines`, `roles`, `report`, `palette`, `compare`, `zoom`, `verify` — `python3 -m pdfmeasure <cmd> -h`.
