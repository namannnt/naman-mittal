// Local rendering/structural QA only; no network requests are allowed.
// Usage: node analysis/render_report.cjs <playwright-module> <browser-executable>
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.argv[2]);
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'tmp', 'report-render');
fs.mkdirSync(output, { recursive: true });
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[3], headless: true });
  // Match A4's 186 mm content width after the configured 12 mm side margins.
  const page = await browser.newPage({ viewport: { width: 703, height: 1400 }, deviceScaleFactor: 1 });
  const attempted = [];
  await page.context().setOffline(true);
  await page.route('**/*', async route => {
    const url = route.request().url();
    if (url.startsWith('file:') || url.startsWith('data:')) await route.continue();
    else { attempted.push(url); await route.abort(); }
  });
  await page.goto(pathToFileURL(path.join(root, 'report.html')).href, { waitUntil: 'load' });
  await page.emulateMedia({ media: 'print' });
  const checks = await page.evaluate(() => {
    const main = document.querySelector('main');
    return {
      title: document.title,
      viewport_width: innerWidth,
      document_width: document.documentElement.scrollWidth,
      table_rows: document.querySelectorAll('tbody tr').length,
      station_ids: [...document.querySelectorAll('tbody th')].map(el => el.textContent),
      smallest_font_pt: Math.min(...[...document.querySelectorAll('main *')]
        .filter(el => el.textContent.trim()).map(el => parseFloat(getComputedStyle(el).fontSize) * 72 / 96)),
      main_height_px: main.getBoundingClientRect().height,
      horizontal_overflow: [...document.querySelectorAll('main *')].filter(el =>
        el.getBoundingClientRect().right > main.getBoundingClientRect().right + 1).map(el => el.tagName),
      external_assets: [...document.querySelectorAll('[src],link[href],script')].map(el => el.outerHTML),
    };
  });
  await page.pdf({ path: path.join(output, 'report-print.pdf'), format: 'A4', preferCSSPageSize: true, printBackground: true });
  await page.screenshot({ path: path.join(output, 'report-print-screen.png'), fullPage: true });
  await page.addStyleTag({ content: 'html { filter: grayscale(1); }' });
  await page.pdf({ path: path.join(output, 'report-grayscale.pdf'), format: 'A4', preferCSSPageSize: true, printBackground: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ media: 'screen' });
  const mobile = await page.evaluate(() => ({ width: innerWidth, scroll_width: document.documentElement.scrollWidth }));
  fs.writeFileSync(path.join(output, 'layout-checks.json'), JSON.stringify({ ...checks, mobile, blocked_network_requests: attempted }, null, 2) + '\n');
  console.log(JSON.stringify({ ...checks, mobile, blocked_network_requests: attempted }, null, 2));
  await browser.close();
})().catch(error => { console.error(error); process.exitCode = 1; });
