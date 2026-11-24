// Measures the reading view of a rebuilt page at phone and tablet widths, for `pdfmeasure reflow` (which judges the numbers).
// Usage:
//   node check-reflow.cjs <reflow url> <out.json> [--widths 320,360,390,768] [--fixed-url <url of the print-sheet view>] [--auto-url <url of the page in auto view>] [--shots <dir>]
// Contract with the page (project-neutral): every content block carries `data-block="<content id>"` in both views; optional
// `data-text-role="body|heading|caption|label|ruby|decorative"` on text that is not body text. Nothing else is assumed about the framework.
const { chromium } = require('playwright')
const fs = require('node:fs')

const [url, out, ...rest] = process.argv.slice(2)
if (!url || !out) {
  console.error('usage: check-reflow.cjs <reflow url> <out.json> [--widths 320,360,390,768] [--fixed-url <url>]')
  process.exit(2)
}
const option = (name, fallback) => {
  const index = rest.indexOf(`--${name}`)
  return index >= 0 ? rest[index + 1] : fallback
}
const widths = option('widths', '320,360,390,768').split(',').map(Number)
const fixedUrl = option('fixed-url', null)
const shots = option('shots', null)
const autoUrl = option('auto-url', null)
const AUTO_WIDTHS = [360, 1280, 1920]

function collect() {
  const visible = (el) => {
    const style = getComputedStyle(el)
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false
    const box = el.getBoundingClientRect()
    return box.width > 0 && box.height > 0
  }
  const roleOf = (el) => {
    const marked = el.closest('[data-text-role]')
    if (marked) return marked.dataset.textRole
    if (el.closest('h1,h2,h3,h4,h5,h6')) return 'heading'
    if (el.closest('figcaption,small,sup,sub,rt,caption')) return 'caption'
    if (el.closest('label,button,[role=button]')) return 'label'
    return 'body'
  }
  const texts = []
  for (const el of document.body.querySelectorAll('*')) {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(el.tagName)) continue
    const own = [...el.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim()).map((n) => n.textContent.trim()).join(' ')
    if (!own || !visible(el) || el.closest('[aria-hidden=true]')) continue
    const box = el.getBoundingClientRect()
    texts.push({ block: el.closest('[data-block]')?.dataset.block ?? null, role: roleOf(el), px: parseFloat(getComputedStyle(el).fontSize), width: box.width, text: own.slice(0, 40) })
  }
  const targets = []
  for (const el of document.body.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=link],[tabindex]:not([tabindex="-1"])')) {
    if (!visible(el)) continue
    const box = el.getBoundingClientRect()
    targets.push({ tag: el.tagName.toLowerCase(), label: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 30), width: box.width, height: box.height })
  }
  const media = [...document.querySelectorAll('img,svg,video,canvas,picture')].filter(visible).map((el) => {
    const box = el.getBoundingClientRect()
    return { tag: el.tagName.toLowerCase(), block: el.closest('[data-block]')?.dataset.block ?? null, left: box.left, right: box.right, width: box.width }
  })
  const blocks = []
  for (const el of document.querySelectorAll('[data-block]')) if (!blocks.includes(el.dataset.block)) blocks.push(el.dataset.block)
  return {
    innerWidth: window.innerWidth,
    scrollWidth: document.scrollingElement.scrollWidth,
    viewport: document.querySelector('meta[name=viewport]')?.getAttribute('content') ?? '',
    texts,
    targets,
    media,
    blocks,
  }
}

;(async () => {
  const browser = await chromium.launch()
  const result = { url, fixedUrl, autoUrl, widths: {}, fixed: null, auto: null }
  try {
    for (const width of widths) {
      const page = await browser.newPage({ viewport: { width, height: 800 } })
      await page.goto(url, { waitUntil: 'networkidle' })
      await page.evaluate(() => document.fonts.ready)
      result.widths[width] = await page.evaluate(collect)
      if (shots) await page.screenshot({ path: `${shots}/reflow-${width}.png`, fullPage: true })
      await page.close()
    }
    if (fixedUrl) {
      const page = await browser.newPage({ viewport: { width: widths[0], height: 800 } })
      await page.goto(fixedUrl, { waitUntil: 'networkidle' })
      await page.evaluate(() => document.fonts.ready)
      const fixed = await page.evaluate(collect)
      result.fixed = { width: widths[0], blocks: fixed.blocks, texts: fixed.texts }
      await page.close()
    }
    if (autoUrl) {
      // The page as a reader opens it (view chosen automatically): phones must get the reading view, desktops the print sheet.
      result.auto = {}
      for (const width of AUTO_WIDTHS) {
        const page = await browser.newPage({ viewport: { width, height: width < 768 ? 800 : 1080 } })
        await page.goto(autoUrl, { waitUntil: 'networkidle' })
        await page.evaluate(() => document.fonts.ready)
        result.auto[width] = await page.evaluate(() => ({
          view: document.querySelector('[data-view]')?.getAttribute('data-view') ?? null,
          innerWidth: window.innerWidth,
          scrollWidth: document.scrollingElement.scrollWidth,
        }))
        if (shots) await page.screenshot({ path: `${shots}/auto-${width}.png`, fullPage: false })
        await page.close()
      }
    }
  } finally {
    await browser.close()
  }
  fs.writeFileSync(out, JSON.stringify(result))
  console.log(`wrote ${out}: ${widths.join(', ')} px${fixedUrl ? ' and the print-sheet view' : ''}`)
})()
