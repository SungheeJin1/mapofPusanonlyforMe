// Render busan_map.svg to busan_map.png at the SVG's native size.
// Usage: node scripts/render_png.js
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
(async () => {
  const root = path.resolve(__dirname, '..');
  const svg = fs.readFileSync(path.join(root, 'busan_map.svg'), 'utf8');
  const [, w, h] = svg.match(/viewBox="0 0 (\d+) (\d+)"/).map(Number);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  await page.goto('file://' + path.join(root, 'busan_map.svg'));
  await page.screenshot({ path: path.join(root, 'busan_map.png') });
  await browser.close();
  console.log(`wrote busan_map.png (${w}x${h})`);
})();
