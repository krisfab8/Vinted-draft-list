/* Price gauge: a semicircle from "sells faster" (green) to "max return" (red),
   a needle at the suggested price and the small suggested range highlighted.
   PriceGauge.html(range, price, reasons) returns markup; no network calls. */
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const W = 300, H = 140, CX = 150, CY = 124, R = 88;
  const point = (p, r = R) => {
    const a = Math.PI * (1 - Math.min(1, Math.max(0, p)));
    return [CX + r * Math.cos(a), CY - r * Math.sin(a)];
  };
  const arc = (p0, p1, r = R) => {
    const [x0, y0] = point(p0, r), [x1, y1] = point(p1, r);
    return `M${x0.toFixed(1)} ${y0.toFixed(1)} A${r} ${r} 0 0 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`;
  };
  const BASIS = {
    observed: 'Based on your matching sales',
    reference: 'Based on your saved price references',
    web: 'Based on sold prices found by web search',
    estimate: 'AI estimate — no matching sales yet, so the range is wider',
  };
  let ids = 0;

  function html(range, price, reasons) {
    if (!range || !(range.scale_high > range.scale_low) || price == null) return '';
    const span = range.scale_high - range.scale_low;
    const at = v => (v - range.scale_low) / span;
    const id = 'pg' + (++ids);
    const [nx, ny] = point(at(price), R - 14);
    const list = (reasons || []).filter(Boolean);
    return `<div class="price-gauge">
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Suggested price £${esc(price)}, range £${esc(range.low)} to £${esc(range.high)}">
        <defs><linearGradient id="${id}" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stop-color="#2e9e5b"/><stop offset=".5" stop-color="#e3a21a"/><stop offset="1" stop-color="#d9364d"/>
        </linearGradient></defs>
        <path d="${arc(0, 1)}" fill="none" stroke="url(#${id})" stroke-width="14" stroke-linecap="round" opacity=".35"/>
        <path d="${arc(at(range.low), at(range.high))}" fill="none" stroke="url(#${id})" stroke-width="14"/>
        ${[range.low, range.high].map(v => {
          // Price labels just outside the arc at each end of the suggested range.
          const [tx, ty] = point(at(v), R + 22), [ox, oy] = point(at(v), R + 9), [ix, iy] = point(at(v), R - 9);
          const anchor = tx < CX - 8 ? 'end' : tx > CX + 8 ? 'start' : 'middle';
          return `<line x1="${ix.toFixed(1)}" y1="${iy.toFixed(1)}" x2="${ox.toFixed(1)}" y2="${oy.toFixed(1)}" stroke="currentColor" stroke-width="2"/>
            <text x="${tx.toFixed(1)}" y="${(ty + 4).toFixed(1)}" text-anchor="${anchor}" font-size="13" font-weight="700" fill="currentColor">£${esc(v)}</text>`;
        }).join('')}
        <line x1="${CX}" y1="${CY}" x2="${nx.toFixed(1)}" y2="${ny.toFixed(1)}" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
        <circle cx="${CX}" cy="${CY}" r="6" fill="currentColor"/>
      </svg>
      <div class="price-gauge-ends"><span>£${esc(range.scale_low)}<br>sells faster</span><span>£${esc(range.scale_high)}<br>max return</span></div>
      <div class="price-gauge-main">£${esc(price)} <span>suggested range £${esc(range.low)}–£${esc(range.high)}</span></div>
      <div class="price-gauge-basis">${esc(BASIS[range.basis] || '')}</div>
      ${list.length ? `<ul class="price-gauge-reasons">${list.map(r => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
    </div>`;
  }

  const style = document.createElement('style');
  style.textContent = `
    .price-gauge{width:100%;max-width:340px;margin:6px auto 0;text-align:center;color:var(--black,#222)}
    .price-gauge svg{width:100%;height:auto;display:block}
    .price-gauge-ends{display:flex;justify-content:space-between;padding:0 8%;font-size:11px;line-height:1.3;color:var(--gray-7,#666);margin-top:-4px}
    .price-gauge-main{font-size:22px;font-weight:800;margin-top:6px}
    .price-gauge-main span{display:block;font-size:13px;font-weight:600;color:var(--gray-7,#666)}
    .price-gauge-basis{font-size:12px;color:var(--gray-7,#666);margin-top:4px}
    .price-gauge-reasons{text-align:left;font-size:12px;color:var(--gray-7,#666);margin:8px 0 0;padding-left:18px}`;
  document.head.appendChild(style);
  window.PriceGauge = {html};
})();
