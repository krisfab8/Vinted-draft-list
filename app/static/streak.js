/* Streaks, Duolingo-style: the celebration when today's goal is hit (flame ignites, number flips,
   milestones and earned freezes get their own moment) and the evening "at risk" pulse.
     Streak.celebrate({streak, tip})   once per day
     <el data-streak-risk data-streak="5" data-met="0">   pulses amber after 6pm until today's goal is met */
(() => {
  if (window.Streak) return;
  const MILESTONES = [3, 7, 14, 30, 50, 100, 200, 365];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const today = () => new Date().toLocaleDateString('en-CA');
  const flame = (size = 120) => `<svg class="stk-flame" width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 1.5c1.2 4.2 6.5 6.3 6.5 12.6a6.5 6.5 0 01-13 0c0-3.3 2.1-5.3 3.2-6.4 0 2.1 1 3.2 2.1 3.2 0-4.2 0-6.3 1.2-9.4z" fill="#F08A24"/>
      <path d="M12 10.5c2.1 2.1 3.4 3.3 3.4 5.6a3.4 3.4 0 01-6.8 0c0-2.2 2.2-3.4 3.4-5.6z" fill="#FFD34D"/></svg>`;

  function burst(box) {
    if (reduce) return;
    const colours = ['#F08A24', '#FFD34D', '#2F4A3A', '#C9A45C', '#F3EDE0'];
    for (let i = 0; i < 26; i++) {
      const bit = document.createElement('span'), a = (i / 26) * Math.PI * 2, d = 110 + (i % 3) * 50;
      bit.className = 'sn-burst-bit';
      bit.style.cssText = `left:${box.left + box.width / 2}px;top:${box.top + box.height / 2}px;--dx:${Math.round(Math.cos(a) * d)}px;`
        + `--dy:${Math.round(Math.sin(a) * d - 50)}px;--rot:${(i * 47) % 360}deg;background:${colours[i % 5]};border-radius:${i % 2 ? '2px' : '50%'};z-index:10001`;
      document.body.appendChild(bit);
      setTimeout(() => bit.remove(), 1300);
    }
  }

  function celebrate({streak, tip = '', force = false} = {}) {
    streak = Math.max(1, +streak || 1);
    try {
      if (!force && localStorage.getItem('streakCelebrated') === today()) return;
      localStorage.setItem('streakCelebrated', today());
    } catch (_) {}
    const milestone = MILESTONES.includes(streak), freeze = streak % 7 === 0;
    const box = document.createElement('div');
    box.className = 'stk-overlay' + (milestone ? ' milestone' : '');
    box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true'); box.setAttribute('aria-label', `${streak}-day streak`);
    box.innerHTML = `<div class="stk-card">
        <div class="stk-glow"></div>${flame(132)}
        <div class="stk-num" aria-hidden="true"><span class="old">${streak - 1}</span><span class="new">${streak}</span></div>
        <h2>${streak === 1 ? 'Streak started!' : `${streak}-day streak!`}</h2>
        ${milestone ? `<div class="stk-badge">🏅 ${streak}-day milestone</div>` : ''}
        ${freeze ? `<div class="stk-badge ice">❄️ You earned a streak freeze</div>` : ''}
        <p>${esc(tip || 'List every day to keep your flame burning.')}</p>
        <button type="button" class="stk-go">Keep going</button>
      </div>`;
    document.body.appendChild(box);
    const close = () => { box.classList.add('out'); setTimeout(() => box.remove(), 250); };
    box.querySelector('.stk-go').onclick = close;
    box.addEventListener('click', e => { if (e.target === box) close(); });
    requestAnimationFrame(() => box.classList.add('in'));
    setTimeout(() => burst(box.querySelector('.stk-flame').getBoundingClientRect()), 650);
    box.querySelector('.stk-go').focus({preventScroll: true});
  }

  function markRisk(root = document) {
    const evening = new Date().getHours() >= 18;
    root.querySelectorAll('[data-streak-risk]').forEach(el => {
      const at = evening && el.dataset.met !== '1' && +el.dataset.streak > 0;
      el.classList.toggle('risk', at);
      if (at && el.dataset.riskText) el.textContent = el.dataset.riskText;
    });
  }

  window.Streak = {celebrate, markRisk, flame};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => markRisk());
  else markRisk();
})();
