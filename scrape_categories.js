/**
 * scrape_categories.js
 *
 * Crawls the Vinted category picker and saves every leaf path to vinted_categories.json.
 *
 * Usage:
 *   node scrape_categories.js
 *
 * The browser opens headed so you can log in if prompted.
 * Press Enter in this terminal once the /items/new page is ready.
 *
 * Output: vinted_categories.json in the same directory.
 *   [
 *     ["Men", "Clothing", "Jeans", "Slim fit jeans"],
 *     ...
 *   ]
 */

const { chromium } = require('playwright');
const fs = require('fs');
const readline = require('readline');

const VINTED_URL = 'https://www.vinted.co.uk';
const OUTPUT_FILE = 'vinted_categories.json';

// ─────────────────────────────────────────────────────────────────────────────
// Picker helpers
// ─────────────────────────────────────────────────────────────────────────────

/** Open the category picker dropdown and wait until its content is visible. */
async function openPicker(page) {
  const input = page.locator('[data-testid="catalog-select-dropdown-input"]').first();
  await input.waitFor({ state: 'visible', timeout: 10000 });
  await input.click();
  // Wait for the picker content to appear
  const content = page.locator('[data-testid="catalog-select-dropdown-content"]');
  await content.waitFor({ state: 'visible', timeout: 6000 });
}

/** Close the picker by pressing Escape. Safe to call even if picker is already closed. */
async function closePicker(page) {
  await page.keyboard.press('Escape');
  await page.waitForTimeout(350);
}

/** Return true if the picker content panel is currently visible. */
async function isPickerOpen(page) {
  return page
    .locator('[data-testid="catalog-select-dropdown-content"]')
    .isVisible()
    .catch(() => false);
}

/**
 * Return all [role="button"] option labels visible in the picker content.
 * Filters out empty strings.
 */
async function getPickerOptions(page) {
  const content = page.locator('[data-testid="catalog-select-dropdown-content"]');
  const buttons = content.locator('[role="button"]');
  const texts = await buttons.allInnerTexts();
  return texts.map(t => t.trim()).filter(t => t.length > 0);
}

/**
 * Click a single option inside the open picker by exact text.
 * Returns true if the click succeeded, false if the option was not found.
 */
async function clickPickerOption(page, optionText) {
  const content = page.locator('[data-testid="catalog-select-dropdown-content"]');
  // Escape special regex characters in the label
  const escaped = optionText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp('^\\s*' + escaped + '\\s*$');
  const btn = content.locator('[role="button"]').filter({ hasText: pattern }).first();
  try {
    await btn.waitFor({ state: 'visible', timeout: 4000 });
    await btn.click();
    await page.waitForTimeout(500);
    return true;
  } catch {
    return false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Inline-radio fallback (some categories show sub-types outside the picker)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * After the picker closes, Vinted sometimes shows sub-category options as
 * inline radio buttons on the form itself (e.g. trouser styles after selecting
 * "Trousers"). This function returns those labels if any are present.
 *
 * We look for [role="radio"] or [role="listitem"] elements that are visible
 * and contain text. We exclude elements that look like condition/size pickers
 * by limiting the search to elements near the top of the page.
 */
async function getInlineSubOptions(page) {
  // Brand input appearing means category is fully selected — no inline sub-options
  const brandVisible = await page
    .locator('[data-testid="brand-select-dropdown-input"]')
    .isVisible()
    .catch(() => false);
  if (brandVisible) return [];

  // Look for radio-style elements that could be sub-category pickers
  const radios = page.locator('[role="radio"]');
  const count = await radios.count().catch(() => 0);
  if (count === 0) return [];

  const texts = [];
  for (let i = 0; i < count; i++) {
    const text = (await radios.nth(i).innerText().catch(() => '')).trim();
    if (text.length > 0) texts.push(text);
  }
  return texts;
}

// ─────────────────────────────────────────────────────────────────────────────
// Core crawler
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Open the picker, navigate step-by-step through `path`, and return the
 * child options visible at the end of that path.
 *
 * Returns:
 *   { type: 'picker', options: [...] }  — picker stayed open, these are children
 *   { type: 'inline', options: [...] }  — picker closed, inline sub-options found
 *   { type: 'leaf' }                    — picker closed, nothing more to select
 *
 * Leaves the picker CLOSED when it returns.
 */
async function navigatePath(page, path) {
  await openPicker(page);

  for (const step of path) {
    const found = await clickPickerOption(page, step);
    if (!found) {
      // Option not in picker — close and bail
      await closePicker(page);
      console.warn(`  [warn] Option not found in picker: "${step}" (path so far: ${path.slice(0, path.indexOf(step)).join(' > ')})`);
      return { type: 'leaf' };
    }

    // Check if picker is still open after clicking this step
    const open = await isPickerOpen(page);
    if (!open) {
      // Picker closed — might be a leaf or might have inline sub-options
      const inlineOptions = await getInlineSubOptions(page);
      if (inlineOptions.length > 0) {
        return { type: 'inline', options: inlineOptions };
      }
      return { type: 'leaf' };
    }
  }

  // Picker is still open — collect options at this level
  const options = await getPickerOptions(page);
  await closePicker(page);
  return { type: 'picker', options };
}

/**
 * Recursive DFS over the category tree.
 *
 * @param {object} page       Playwright page
 * @param {string[]} path     Current path (labels clicked so far)
 * @param {string[][]} results Accumulator for leaf paths
 */
async function explore(page, path, results) {
  const label = path.length === 0 ? '(root)' : path.join(' > ');
  console.log(`Exploring: ${label}`);

  // Get options at current path
  const { type, options } = await navigatePath(page, path);

  if (type === 'leaf') {
    // Path itself is a leaf (unusual at non-terminal nodes, but handle it)
    if (path.length > 0) {
      console.log(`  ✓ Leaf: ${path.join(' > ')}`);
      results.push([...path]);
    }
    return;
  }

  if (!options || options.length === 0) {
    // No children found — treat this path as a leaf
    if (path.length > 0) {
      console.log(`  ✓ Leaf (no children): ${path.join(' > ')}`);
      results.push([...path]);
    }
    return;
  }

  // For each child option, determine if it is a leaf or a branch
  for (const option of options) {
    const childPath = [...path, option];

    if (type === 'inline') {
      // Inline options are always leaves (Vinted shows them as the final selector)
      console.log(`  ✓ Leaf (inline): ${childPath.join(' > ')}`);
      results.push(childPath);
      continue;
    }

    // type === 'picker' — open fresh and try clicking one more level
    const child = await navigatePath(page, childPath);

    if (child.type === 'leaf') {
      console.log(`  ✓ Leaf: ${childPath.join(' > ')}`);
      results.push(childPath);
    } else if (child.type === 'inline') {
      // childPath has inline sub-options
      for (const sub of child.options) {
        const subPath = [...childPath, sub];
        console.log(`  ✓ Leaf (inline): ${subPath.join(' > ')}`);
        results.push(subPath);
      }
    } else {
      // Branch — recurse deeper
      await explore(page, childPath, results);
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Entry point
// ─────────────────────────────────────────────────────────────────────────────

(async () => {
  const browser = await chromium.launch({
    headless: false,
    channel: 'chrome',
    args: ['--disable-blink-features=AutomationControlled'],
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    userAgent:
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ' +
      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  });

  const page = await context.newPage();

  console.log('Opening Vinted create-listing page...');
  await page.goto(`${VINTED_URL}/items/new`, { waitUntil: 'domcontentloaded', timeout: 30000 });

  // Pause for manual login if needed
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  await new Promise(resolve => {
    rl.question('\nLog in if prompted, then press Enter to start crawling... ', () => {
      rl.close();
      resolve();
    });
  });

  // Dismiss cookie banner if present
  await page.evaluate(() => {
    ['#onetrust-consent-sdk', '.onetrust-pc-dark-filter'].forEach(sel => {
      const el = document.querySelector(sel);
      if (el) el.remove();
    });
    document.body.style.overflow = 'auto';
  });
  await page.waitForTimeout(500);

  console.log('\nStarting category tree exploration...\n');
  const results = [];

  try {
    await explore(page, [], results);
  } catch (err) {
    console.error('Exploration error:', err.message);
  }

  // Deduplicate by string key
  const seen = new Set();
  const unique = results.filter(path => {
    const key = path.join('|||');
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  // Sort for readability
  unique.sort((a, b) => a.join('|').localeCompare(b.join('|')));

  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(unique, null, 2), 'utf8');
  console.log(`\nDone. ${unique.length} leaf paths saved to ${OUTPUT_FILE}`);

  await browser.close();
})();
