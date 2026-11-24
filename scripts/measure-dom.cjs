// Measures a rebuilt page in the browser: a screenshot of one "sheet" and the box and computed style of every element that carries the measuring attribute.
//
//   node measure-dom.cjs <url> <out dir> --page-width-pt <pt> [--sheet 0] [--dpr 4] [--width 800] [--attr data-wb] [--sheet-selector '[data-wb="sheet"]']
//
// Writes <out dir>/dom.json and sheet.png. Positions are CSS pixels relative to the sheet; `compare` divides them by the sheet's pixels per point.
// An element can opt in to extra detail: a child `<svg><rect>` (a stroke drawn as SVG) is recorded as `frame`, and `data-measure-before` makes the
// computed style of its ::before recorded as `before` (a thin rule drawn as a pseudo-element). Needs `playwright` (npm i -D playwright).
const { chromium } = require('playwright')
const fs = require('node:fs')
const path = require('node:path')

const [url, outDir, ...rest] = process.argv.slice(2)
const option = (name, fallback) => {
  const index = rest.indexOf(`--${name}`)
  return index >= 0 ? rest[index + 1] : fallback
}
if (!url || !outDir || option('page-width-pt') === undefined) {
  console.error('usage: measure-dom.cjs <url> <out dir> --page-width-pt <pt> [--sheet 0] [--dpr 4] [--width 800] [--attr data-wb] [--sheet-selector selector]')
  process.exit(2)
}
const pageWidthPt = Number(option('page-width-pt'))
const sheetIndex = Number(option('sheet', 0))
const dpr = Number(option('dpr', 4))
const width = Number(option('width', 800))
const attr = option('attr', 'data-wb')
const sheetSelector = option('sheet-selector', `[${attr}="sheet"]`)

;(async () => {
  fs.mkdirSync(outDir, { recursive: true })
  const browser = await chromium.launch()
  const page = await (await browser.newContext({ viewport: { width: width + 80, height: 1400 }, deviceScaleFactor: dpr })).newPage()
  await page.goto(url, { waitUntil: 'networkidle' })
  // Wait for web fonts and every image to be decoded before measuring: late fonts shift text, late images shift boxes.
  await page.evaluate(async () => {
    await document.fonts.ready
    await Promise.all([...document.images].map((image) => image.decode().catch(() => undefined)))
  })
  await page.waitForTimeout(300)
  const sheet = page.locator(sheetSelector).nth(sheetIndex)
  await sheet.evaluate((element, w) => {
    element.parentElement.style.width = `${w}px`
    element.parentElement.style.minWidth = `${w}px`
  }, width)
  await page.waitForTimeout(300)
  await sheet.screenshot({ path: path.join(outDir, 'sheet.png') })
  const data = await sheet.evaluate(
    (root, attrName) => {
      const origin = root.getBoundingClientRect()
      const elements = []
      for (const element of root.querySelectorAll(`[${attrName}]`)) {
        const rect = element.getBoundingClientRect()
        const style = getComputedStyle(element)
        const entry = {
          role: element.getAttribute(attrName),
          x: rect.x - origin.x,
          y: rect.y - origin.y,
          w: rect.width,
          h: rect.height,
          text: (element.textContent || '').trim().slice(0, 24),
          aria: element.getAttribute('aria-current'),
          style: {
            color: style.color,
            background: style.backgroundColor,
            fontFamily: style.fontFamily.split(',')[0],
            fontSize: parseFloat(style.fontSize),
            fontWeight: style.fontWeight,
            letterSpacing: parseFloat(style.letterSpacing) || 0,
            wordSpacing: parseFloat(style.wordSpacing) || 0,
            borderTopWidth: parseFloat(style.borderTopWidth),
            borderColor: style.borderTopColor,
            borderRadius: parseFloat(style.borderTopLeftRadius),
          },
        }
        const frame = element.querySelector(':scope > svg > rect')
        if (frame) {
          const frameStyle = getComputedStyle(frame)
          entry.frame = { rx: parseFloat(frameStyle.rx), strokeWidth: parseFloat(frameStyle.strokeWidth), stroke: frameStyle.stroke }
        }
        if (element.hasAttribute('data-measure-before')) {
          const before = getComputedStyle(element, '::before')
          entry.before = { height: parseFloat(before.height), bottom: parseFloat(before.bottom), background: before.backgroundColor }
        }
        elements.push(entry)
      }
      return { sheet: { w: origin.width, h: origin.height }, elements }
    },
    attr,
  )
  fs.writeFileSync(path.join(outDir, 'dom.json'), JSON.stringify({ ...data, dpr, page_width_pt: pageWidthPt }, null, 1))
  console.log(`wrote ${outDir}/sheet.png and dom.json: ${data.elements.length} elements, sheet ${data.sheet.w}x${data.sheet.h} css px @${dpr}x`)
  await browser.close()
})()
