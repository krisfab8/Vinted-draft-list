const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const readline = require('readline');

const OUT = path.join(__dirname, 'cat_screenshots');
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT);

async function shot(page, name) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  console.log('  saved:', file);
}

async function pickItem(page, text) {
  const loc = page.locator(`[role="button"]:has-text("${text}"), [role="option"]:has-text("${text}"), [role="listitem"]:has-text("${text}")`).first();
  try {
    await loc.waitFor({ state: 'visible', timeout: 4000 });
    await loc.click();
    await page.waitForTimeout(900);
    return true;
  } catch { return false; }
}

async function waitForEnter(msg) {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(msg, () => { rl.close(); resolve(); });
  });
}

(async () => {
  const browser = await chromium.launch({
    headless: false,
    slowMo: 250,
    executablePath: '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
  });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });

  // Try loading cookies if they exist and aren't expired
  try {
    const cookies = JSON.parse(fs.readFileSync('vinted_cookies.json', 'utf8'));
    await ctx.addCookies(cookies);
  } catch {}

  const page = await ctx.newPage();
  await page.goto('https://www.vinted.co.uk/items/new', { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(2000);

  // Check if we hit the login wall
  if (page.url().includes('signup') || page.url().includes('login')) {
    console.log('\n⚠️  Not logged in. Please log in to Vinted in the browser window that just opened.');
    console.log('   After you are on the sell/new item page, press Enter here to continue.\n');
    await waitForEnter('Press Enter once you are on the sell page... ');
  }

  await shot(page, '01_sell_form');
  console.log('URL:', page.url());

  // Open category picker
  console.log('\nOpening category picker...');
  const catClicked = await (async () => {
    const sels = [
      '[data-testid="catalog-select-dropdown-input"]',
      '#catalog-select-dropdown-input',
      '[data-testid*="catalog"]',
    ];
    for (const s of sels) {
      try {
        await page.locator(s).first().click({ timeout: 3000 });
        return true;
      } catch {}
    }
    return false;
  })();

  if (!catClicked) {
    console.log('Could not find category picker automatically.');
    await waitForEnter('Please click on the Category field in the browser, then press Enter... ');
  }

  await page.waitForTimeout(1200);
  await shot(page, '02_picker_level0');

  // Path: Men > Clothing > Outerwear > Jackets > [subtype]
  console.log('Men...');
  await pickItem(page, 'Men');
  await shot(page, '03_picker_men_selected');

  console.log('Clothing...');
  await pickItem(page, 'Clothing');
  await shot(page, '04_picker_clothing');

  console.log('Outerwear...');
  const gotOuterwear = await pickItem(page, 'Outerwear') || await pickItem(page, 'Jackets & coats');
  await shot(page, '05_picker_outerwear');

  console.log('Jackets...');
  await pickItem(page, 'Jackets') || await pickItem(page, 'Jackets & coats');
  await shot(page, '06_picker_jackets');

  console.log('Subtype...');
  await pickItem(page, 'Bomber jackets') || await pickItem(page, 'Field & utility jackets') || await pickItem(page, 'Denim jackets');
  await page.waitForTimeout(1500);
  await shot(page, '07_picker_subtype_done');

  // --- Jeans path ---
  console.log('\nJeans path: re-open picker...');
  await (async () => {
    const sels = [
      '[data-testid="catalog-select-dropdown-input"]',
      '#catalog-select-dropdown-input',
      '[data-testid*="catalog"]',
    ];
    for (const s of sels) {
      try { await page.locator(s).first().click({ timeout: 3000 }); return; } catch {}
    }
  })();
  await page.waitForTimeout(900);
  await pickItem(page, 'Men');
  await pickItem(page, 'Clothing');
  await pickItem(page, 'Jeans');
  await shot(page, '08_picker_jeans_subtypes');

  // --- Women path for comparison ---
  console.log('\nWomen path: re-open picker...');
  await (async () => {
    const sels = ['[data-testid="catalog-select-dropdown-input"]', '#catalog-select-dropdown-input'];
    for (const s of sels) {
      try { await page.locator(s).first().click({ timeout: 3000 }); return; } catch {}
    }
  })();
  await page.waitForTimeout(900);
  await shot(page, '09_picker_level0_again');

  await browser.close();
  console.log('\nDone! Screenshots saved to:', OUT);
})();
