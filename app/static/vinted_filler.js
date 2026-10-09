/* Fills Vinted's sell form inside the phone app's built-in browser.
   Same steps and form IDs as the desktop robot (app/draft_creator.py). Runs on
   https://www.vinted.co.uk/items/new; gets the listing from window.AndroidBridge.
   Never publishes: the seller checks the form and taps "Save draft". */
(() => {
  if (window.VintedFiller) return;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const byId = id => document.querySelector(`[data-testid="${id}"]`);
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const visible = el => !!el && el.getClientRects().length > 0;
  const FIELDS = ['add-photos-input', 'catalog-select-dropdown-input', 'title--input', 'description--input',
    'brand-select-dropdown-input', 'size-select-dropdown-input', 'category-condition-single-list-input',
    'color-select-dropdown-input', 'category-material-multi-list-input', 'price-input--input',
    'upload-form-save-draft-button'];

  async function waitFor(fn, timeout = 8000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) { const v = fn(); if (v) return v; await sleep(150); }
    return null;
  }
  function tap(el) {
    if (!el) return false;
    el.scrollIntoView({block: 'center'});
    const r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
    const o = {bubbles: true, cancelable: true, clientX: x, clientY: y, pointerType: 'touch', isPrimary: true};
    el.dispatchEvent(new PointerEvent('pointerdown', o)); el.dispatchEvent(new MouseEvent('mousedown', o));
    el.dispatchEvent(new PointerEvent('pointerup', o)); el.dispatchEvent(new MouseEvent('mouseup', o));
    el.click();
    return true;
  }
  function setValue(el, value) {           // React-controlled inputs need the native setter
    if (!el) return false;
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    return true;
  }
  async function typeSlowly(el, text) {
    el.focus();
    for (let i = 1; i <= text.length; i++) { setValue(el, text.slice(0, i)); await sleep(60); }
  }
  function options(contentId, selector = '[role="button"]') {
    const box = byId(contentId);
    return box ? [...box.querySelectorAll(selector)] : [];
  }
  function match(target, els) {            // exact → normalised → contains (longest first)
    const t = norm(target);
    return els.find(e => (e.innerText || '').trim() === target)
      || els.find(e => norm(e.innerText) === t)
      || [...els].sort((a, b) => (b.innerText || '').length - (a.innerText || '').length)
          .find(e => { const o = norm(e.innerText); return o && (o.includes(t) || t.includes(o)); });
  }
  async function pick(contentId, text) {
    const el = match(text, await waitFor(() => options(contentId).length && options(contentId), 4000) || []);
    if (!el) return false;
    tap(el); await sleep(500); return true;
  }
  function closeDropdowns() {
    document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
    byId('title--input')?.click();
  }
  async function dataUrlToFile(photo) {
    const blob = await (await fetch(photo.data_url)).blob();
    return new File([blob], photo.name, {type: blob.type || 'image/jpeg'});
  }

  const steps = {
    async photos(p) {
      const input = await waitFor(() => document.querySelector('input[data-testid="add-photos-input"]') || document.querySelector('input[type="file"]'));
      if (!input || !p.photos.length) return false;
      const dt = new DataTransfer();
      for (const photo of p.photos) dt.items.add(await dataUrlToFile(photo));
      input.files = dt.files;
      input.dispatchEvent(new Event('input', {bubbles: true}));
      input.dispatchEvent(new Event('change', {bubbles: true}));
      await sleep(2500);
      return true;
    },
    async category(p) {
      if (!p.category_path.length || !tap(await waitFor(() => byId('catalog-select-dropdown-input')))) return false;
      await sleep(600);
      for (const step of p.category_path) {
        if (await pick('catalog-select-dropdown-content', step)) continue;
        // Deeper levels sometimes show as a list on the page instead of in the dropdown.
        const el = match(step, [...document.querySelectorAll('[role="radio"],[role="option"],[role="listitem"],[role="button"]')].filter(visible));
        if (!el) return false;
        tap(el); await sleep(500);
      }
      closeDropdowns(); await sleep(500);
      return true;
    },
    async title(p) { return setValue(await waitFor(() => byId('title--input')), p.title); },
    async description(p) { return setValue(await waitFor(() => byId('description--input')), p.description); },
    async brand(p) {
      if (!p.brand || !tap(await waitFor(() => byId('brand-select-dropdown-input'), 10000))) return false;
      const search = await waitFor(() => byId('brand-search--input'), 3000);
      if (!search) { closeDropdowns(); return false; }
      await typeSlowly(search, p.brand); await sleep(1300);
      const box = byId('brand-select-dropdown-content');
      const rows = box ? [...box.querySelectorAll('*')].filter(e => e.children.length === 0 && visible(e)) : [];
      const row = rows.find(e => (e.innerText || '').trim() === p.brand) || rows.find(e => norm(e.innerText) === norm(p.brand));
      if (!row) { closeDropdowns(); return false; }
      tap(row); await sleep(600); return true;
    },
    async size(p) {
      if (!p.size || !tap(byId('size-select-dropdown-input'))) return false;
      await sleep(600);
      const s = p.size.trim(), wl = s.match(/[Ww]\s*(\d+)\s*(?:[/\s]+|[Ll]\s*)(\d+)/) || s.match(/(\d+)\s*\/\s*(\d+)/);
      const candidates = (wl ? [`W${wl[1]} L${wl[2]}`, `W${wl[1]}/L${wl[2]}`, `${wl[1]}/${wl[2]}`, `W${wl[1]}`, wl[1]] : [])
        .concat([s, s + 'R', s + 'S', s + 'L']);
      for (const c of candidates) if (await pick('size-select-dropdown-content', c)) return true;
      closeDropdowns(); return false;
    },
    async condition(p) {
      tap(byId('category-condition-single-list-input')); await sleep(600);
      const el = byId(`condition-${p.condition_id}`) || byId(`condition-radio-${p.condition_id}--input`)
        || match(p.condition, options('category-condition-single-list-content', '[role="button"], label, li'));
      if (!el) return false;
      tap(el); await sleep(400); return true;
    },
    async colour(p) {
      if (!p.colours.length || !tap(byId('color-select-dropdown-input'))) return false;
      await sleep(500);
      let ok = false;
      for (const c of p.colours) ok = (await pick('color-select-dropdown-content', c)) || ok;
      closeDropdowns(); return ok;
    },
    async material(p) {
      if (!p.materials.length || !tap(byId('category-material-multi-list-input'))) return false;
      await sleep(500);
      let ok = false;
      for (const name of p.materials) {
        const el = options('category-material-multi-list-content').find(e => norm(e.innerText).includes(name));
        if (el) { tap(el); ok = true; await sleep(300); }
      }
      closeDropdowns(); return ok;
    },
    async price(p) { return setValue(await waitFor(() => byId('price-input--input')), p.price); },
    async parcel(p) {
      closeDropdowns(); await sleep(400);
      return tap(byId(`package_type_selector_${p.package}--input`));
    },
  };

  function panel(report) {
    document.getElementById('vl-panel')?.remove();
    const box = document.createElement('div');
    box.id = 'vl-panel';
    box.style.cssText = 'position:fixed;left:8px;right:8px;bottom:8px;z-index:2147483647;background:#1D1D1F;color:#fff;' +
      'border-radius:18px;padding:14px 16px;font:600 14px/1.4 system-ui,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.35)';
    const rows = Object.entries(report.steps).map(([k, v]) => `<span style="opacity:${v ? 1 : .6}">${v ? '✓' : '✗'} ${k}</span>`).join(' · ');
    box.innerHTML = `<div style="font-size:16px;font-weight:800;margin-bottom:6px">Filled ${report.filled}/${report.total} — check, then save</div>
      <div style="margin-bottom:10px">${rows}</div>
      <button id="vl-save" style="width:100%;height:46px;border:0;border-radius:999px;background:#2F4A3A;color:#F3EDE0;font:800 16px system-ui">Save draft</button>
      <button id="vl-hide" style="width:100%;height:36px;border:0;background:none;color:#aaa;font:700 13px system-ui;margin-top:4px">Hide</button>`;
    document.body.appendChild(box);
    box.querySelector('#vl-hide').onclick = () => box.remove();
    box.querySelector('#vl-save').onclick = async () => {
      const save = byId('upload-form-save-draft-button');
      if (!save) { box.querySelector('#vl-save').textContent = "Couldn't find Vinted's Save draft — use the page's button"; return; }
      tap(save);
      const left = await waitFor(() => !location.pathname.includes('/items/new'), 20000);
      send(Object.assign(report, {saved: !!left, draft_url: left ? location.href : null}));
      box.remove();
    };
  }
  // The phone app wraps this script in a function that receives a one-time key (never put on window).
  function bridgeKey() { return typeof __vlKey === 'string' ? __vlKey : ''; }
  function send(report) {
    try { window.AndroidBridge?.report(bridgeKey(), JSON.stringify(report)); } catch (_) {}
  }

  async function run() {
    let payload;
    try { payload = JSON.parse(window.AndroidBridge.getPayload(bridgeKey()) || 'null'); } catch (_) { payload = null; }
    const report = {url: location.href, ua: navigator.userAgent, found: {}, steps: {}, filled: 0, total: 0, folder: payload?.folder};
    for (const id of FIELDS) report.found[id] = !!byId(id);
    if (!payload) { report.error = 'no listing to fill'; send(report); return report; }
    if (!location.pathname.includes('/items/new')) { report.error = 'not on the sell page (signed in to Vinted?)'; send(report); return report; }
    document.querySelectorAll('#onetrust-consent-sdk, .onetrust-pc-dark-filter').forEach(e => e.remove());
    for (const [name, step] of Object.entries(steps)) {
      try { report.steps[name] = !!(await step(payload)); } catch (e) { report.steps[name] = false; report.errors = (report.errors || []).concat(`${name}: ${e.message}`); }
      if (name === 'photos') for (const id of FIELDS) report.found[id] = report.found[id] || !!byId(id);
    }
    report.total = Object.keys(report.steps).length;
    report.filled = Object.values(report.steps).filter(Boolean).length;
    send(report);
    panel(report);
    return report;
  }
  window.VintedFiller = {run, steps};
})();
