/* Two views of the same confirmed monthly sales; no third-party chart bundle. */
function switchSalesChart(mode, button) {
  const card = document.querySelector('.sales-trend-card');
  if (!card || !['sales', 'profit'].includes(mode)) return;
  document.getElementById('chart-sales').hidden = mode !== 'sales';
  document.getElementById('chart-profit').hidden = mode !== 'profit';
  const raw = card.dataset[mode];
  document.getElementById('trend-value').textContent = raw === '' ? '—' :
    new Intl.NumberFormat('en-GB', {style: 'currency', currency: 'GBP'}).format(Number(raw));
  document.getElementById('trend-label').textContent = mode === 'sales' ? 'Sales' : 'Profit before fees';
  document.querySelectorAll('.chart-switch button').forEach(el => {
    el.classList.toggle('selected', el === button);
    el.setAttribute('aria-pressed', String(el === button));
  });
}
