// Field Notes documentation checks (template from the field-notes-docs skill).
// Copy to <repo>/scripts/test-docs.mjs. Needs `npm i -D @playwright/test` and
// `npx playwright install chromium`. Checks every sidebar combination at desktop and
// mobile widths, horizontal overflow, file search and navigation to every guide.
import { chromium, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const cfg = JSON.parse(readFileSync('docs/docs.config.json', 'utf8'));
const browser = await chromium.launch({ headless: true });
try {
  for (const width of [1280, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 850 } });
    await page.goto(pathToFileURL(path.resolve('docs/site/index.html')).href);
    for (const [left, right] of [[true, true], [false, true], [false, false], [true, false], [true, true]]) {
      for (const [side, shown] of [['left', left], ['right', right]]) {
        if (await page.locator(`#${side}`).isVisible() !== shown) await page.locator(`#${side}-toggle`).click();
        await expect(page.locator(`#${side}-toggle`)).toHaveAttribute('aria-expanded', String(shown));
      }
      const main = await page.locator('main').boundingBox();
      expect(main.width).toBeGreaterThan(300);
      if (width > 900) {
        expect(main.x).toBe(left ? 240 : 0);
        expect(main.width).toBe(width - (left ? 240 : 0) - (right ? 300 : 0));
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    await page.locator('#search').fill('docs.config');
    await expect(page.locator('#results a')).toContainText(['docs/docs.config.json']);
    for (const g of cfg.guides ?? []) {
      await page.locator('#left nav').getByRole('link', { name: g.title, exact: true }).click();
      await expect(page.locator('main h1').first()).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    await page.close();
  }
  console.log('PASS: four panel layouts, overflow, file search and guide navigation at desktop/mobile sizes.');
} finally { await browser.close(); }
