// Measures every kit primitive on a page that shows many pages of one book (the lab), for `pdfmeasure consistency`.
// Usage: node check-kit.cjs <url> <out.json> [--width 1280] [--view sheet]
// Contract (project-neutral): each primitive's root carries data-kit="<name>" (optional data-kit-variant), its inner pieces that must line up
// carry data-kit-part="<name>" (the arrow, the rule, the label text…), and each page carries data-page="<number>".
const { chromium } = require('playwright')
const fs = require('node:fs')

const [url, out, ...rest] = process.argv.slice(2)
if (!url || !out) {
  console.error('usage: check-kit.cjs <url> <out.json> [--width 1280] [--view sheet]')
  process.exit(2)
}
const option = (name, fallback) => {
  const index = rest.indexOf(`--${name}`)
  return index >= 0 ? rest[index + 1] : fallback
}
const width = Number(option('width', 1280))
const view = option('view', 'sheet')

;(async () => {
  const browser = await chromium.launch()
  try {
    const page = await browser.newPage({ viewport: { width, height: 1000 } })
    await page.goto(url, { waitUntil: 'networkidle' })
    await page.evaluate(() => document.fonts.ready)
    const items = await page.evaluate((view) => {
      const found = []
      for (const el of document.querySelectorAll('[data-kit]')) {
        const scope = el.closest('[data-view]')
        if (scope && scope.getAttribute('data-view') !== view) continue
        const box = el.getBoundingClientRect()
        if (!box.width || !box.height) continue
        const range = document.createRange()
        range.selectNodeContents(el)
        const textRects = [...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0)
        const hasText = el.textContent.trim().length > 0 && textRects.length > 0
        const text = hasText
          ? textRects.reduce((a, r) => ({ left: Math.min(a.left, r.left), top: Math.min(a.top, r.top), right: Math.max(a.right, r.right), bottom: Math.max(a.bottom, r.bottom) }), { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity })
          : null
        const parts = {}
        for (const part of el.querySelectorAll('[data-kit-part]')) {
          const r = part.getBoundingClientRect()
          parts[part.getAttribute('data-kit-part')] = { cx: r.left + r.width / 2 - box.left, cy: r.top + r.height / 2 - box.top, width: r.width, height: r.height }
        }
        found.push({
          kit: el.getAttribute('data-kit'),
          variant: el.getAttribute('data-kit-variant') ?? '',
          page: el.closest('[data-page]')?.getAttribute('data-page') ?? '',
          width: box.width,
          height: box.height,
          fontSize: parseFloat(getComputedStyle(el).fontSize),
          text: text && { cx: (text.left + text.right) / 2 - (box.left + box.width / 2), cy: (text.top + text.bottom) / 2 - (box.top + box.height / 2), height: text.bottom - text.top },
          parts,
        })
      }
      return found
    }, view)
    fs.writeFileSync(out, JSON.stringify({ url, width, view, items }))
    console.log(`wrote ${out}: ${items.length} primitive instance(s) at ${width} px`)
  } finally {
    await browser.close()
  }
})()
