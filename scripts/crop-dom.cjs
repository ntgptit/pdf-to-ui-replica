// Screenshots a whole sheet at a fixed zoom (default 12 px per point) so parts can be compared with the PDF at pixel level.
//
//   node crop-dom.cjs <url> <out dir> --page-width-pt <pt> [--sheet 0] [--zoom 12] [--css-per-pt 8] [--attr data-wb] [--sheet-selector selector]
//
// Writes <out dir>/sheet-zoom.png. The sheet is laid out `css-per-pt` CSS pixels per point wide (8 by default): a browser rounds some positions (SVG roots)
// to whole CSS pixels, and at 8 px per point that error stays under 0.06 pt. The device scale factor is then zoom / css-per-pt. Parts are cut out of
// the image afterwards by array indexing (zoom.py), never with a browser clip, whose origin is rounded too.
const { chromium } = require('playwright')
const fs = require('node:fs')
const path = require('node:path')

const [url, outDir, ...rest] = process.argv.slice(2)
const option = (name, fallback) => {
  const index = rest.indexOf(`--${name}`)
  return index >= 0 ? rest[index + 1] : fallback
}
if (!url || !outDir || option('page-width-pt') === undefined) {
  console.error('usage: crop-dom.cjs <url> <out dir> --page-width-pt <pt> [--sheet 0] [--zoom 12] [--css-per-pt 8] [--attr data-wb] [--sheet-selector selector]')
  process.exit(2)
}
const pageWidthPt = Number(option('page-width-pt'))
const sheetIndex = Number(option('sheet', 0))
const zoom = Number(option('zoom', 12))
const cssPerPt = Number(option('css-per-pt', 8))
const attr = option('attr', 'data-wb')
const sheetSelector = option('sheet-selector', `[${attr}="sheet"]`)
const width = Math.round(pageWidthPt * cssPerPt)
const dpr = zoom / (width / pageWidthPt)

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
  // Pin the sheet to the top-left corner of the viewport so its origin is a whole CSS pixel and layout cannot shift the crops.
  await sheet.evaluate((element, w) => {
    const holder = element.parentElement
    holder.style.cssText += `;position:fixed;left:0;top:0;width:${w}px;min-width:${w}px;z-index:99999;background:white;`
    window.scrollTo(0, 0)
  }, width)
  await page.waitForTimeout(300)
  await sheet.screenshot({ path: path.join(outDir, 'sheet-zoom.png') })
  console.log(`wrote ${outDir}/sheet-zoom.png at ${zoom} px/pt (dpr ${dpr.toFixed(4)}, sheet ${width} css px wide)`)
  await browser.close()
})()
