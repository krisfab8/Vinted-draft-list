/* Brass XP coin: a real 3D coin (two faces + a stacked rim) that sways, flips round every
   few seconds and catches the light as it turns. Usage:
     <span class="coin" data-coin="idle" style="--coin:120px"></span>   (idle sway + flips)
     <span class="coin" data-coin="still"></span>                       (no idle motion)
     Coin.earn(el)        fast spin + pop + sparkles (XP earned)
     Coin.fly(x, y, text) a coin pops out at (x, y), spins up and fades with "+10 XP" */
(() => {
  if (window.Coin) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const RING = '<circle cx="100" cy="100" r="80" fill="none" stroke="#7A5A26" stroke-width="2.6" stroke-dasharray="1 7" stroke-linecap="round"/>';
  const SHOE = '<path d="M22.5 15h-21V7.333a.333.333 0 0 1 .6-.2l.327.436a3.578 3.578 0 0 0 6.062-.547l.726-1.451a1.032 1.032 0 0 1 1.568-.345l1.259 1.007c.595.476.892.714 1.195.943a27 27 0 0 0 4.939 2.96c.344.158.694.308 1.395.609l.172.073c.32.138.48.206.622.28a4 4 0 0 1 2.122 3.22c.013.16.013.334.013.682"/>'
    + '<path d="M22.5 15c0 1.414 0 2.121-.44 2.56c-.439.44-1.146.44-2.56.44h-15c-1.414 0-2.121 0-2.56-.44c-.44-.439-.44-1.146-.44-2.56M12 9.5L13.5 8m1.5 3l1.5-1.5"/>';
  const MARK = '<g transform="translate(100,100) scale(0.86) translate(-100,-100)"><g transform="translate(0,107.4)" fill="none" stroke="#5E4419" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round">'
    + '<path d="M100 -46 C100 -56 101 -61 107 -65 C115 -70 116 -81 108 -85 C101 -89 92 -85 93 -77"/>'
    + '<path d="M100 -46 C84 -36 43.2 -22 33.2 -10 C27.2 -4 29.2 0 39.2 0 L160.8 0 C170.8 0 172.8 -4 166.8 -10 C156.8 -22 116 -36 100 -46"/>'
    + '<g transform="translate(35.2,97.2) scale(5.4,-5.4)" stroke-width="0.78">' + SHOE + '</g></g></g>';
  const svg = inner => `<svg viewBox="0 0 200 200" aria-hidden="true">${RING}${inner}</svg>`;
  const FRONT = svg(MARK);
  const BACK = svg('<text x="100" y="121" text-anchor="middle" font-family="Manrope, system-ui, sans-serif" font-weight="800" font-size="62" fill="#5E4419" letter-spacing="-2">XP</text>');
  const coins = new Set();

  function build(el) {
    if (el._coin) return el._coin;
    const px = parseFloat(getComputedStyle(el).getPropertyValue("--coin")) || 40;
    const layers = Math.max(3, Math.min(14, Math.round(px / 9)));
    let edge = "";
    for (let i = 0; i < layers; i++) edge += `<i class="coin-edge" style="--k:${(i / (layers - 1) - 0.5).toFixed(3)}"></i>`;
    el.innerHTML = `<span class="coin-tilt"><span class="coin-body">${edge}`
      + `<span class="coin-face coin-front">${FRONT}<span class="coin-shade"></span><span class="coin-sheen"></span></span>`
      + `<span class="coin-face coin-back">${BACK}<span class="coin-shade"></span><span class="coin-sheen"></span></span>`
      + `</span></span><span class="coin-shadow"></span>`;
    if (!el.hasAttribute("aria-label") && !el.closest("[aria-label]")) el.setAttribute("aria-hidden", "true");
    const c = {el, body: el.querySelector(".coin-body"), angle: -14, burst: null,
               idle: el.dataset.coin !== "still", phase: Math.random() * 5000};
    el._coin = c;
    coins.add(c);
    paint(c, reduce ? -18 : c.angle);
    return c;
  }

  const ease = t => 1 - Math.pow(1 - t, 3);
  const PERIOD = 5200, SWAY = 3600;          // sway for 3.6s, then one flip round

  function idleAngle(t) {
    const p = t % PERIOD, turns = Math.floor(t / PERIOD) * 360;
    if (p < SWAY) return turns + 16 * Math.sin((p / SWAY) * Math.PI * 4);
    return turns + 360 * ease((p - SWAY) / (PERIOD - SWAY));
  }

  function paint(c, deg) {
    const r = deg * Math.PI / 180, cos = Math.cos(r), sin = Math.sin(r), s = c.el.style;
    c.body.style.transform = `rotateY(${deg.toFixed(2)}deg)`;
    s.setProperty("--shade-f", Math.min(.62, (1 - cos) * .5).toFixed(3));   // darker as a face turns away
    s.setProperty("--shade-b", Math.min(.62, (1 + cos) * .5).toFixed(3));
    s.setProperty("--sheen", (sin * 130).toFixed(1) + "%");                  // light band slides across
    s.setProperty("--hx", (34 - sin * 22).toFixed(1) + "%");                 // hot spot follows the light
    s.setProperty("--shadow", Math.max(.16, Math.abs(cos)).toFixed(3));      // floor shadow narrows edge-on
  }

  function frame(now) {
    for (const c of coins) {
      if (!c.el.isConnected) { coins.delete(c); continue; }
      let deg = c.idle ? idleAngle(now + c.phase) : -14;
      if (c.burst) {
        const t = (now - c.burst.start) / c.burst.ms;
        if (t >= 1) { c.phase -= c.burst.ms; c.burst = null; deg = c.idle ? idleAngle(now + c.phase) : -14; }  // resume the idle pose where it paused
        else deg = c.burst.from + c.burst.turns * 360 * ease(t);
      }
      c.angle = deg;
      paint(c, deg);
    }
    requestAnimationFrame(frame);
  }

  function sparkles(el, n = 10) {
    const box = el.getBoundingClientRect(), cx = box.left + box.width / 2, cy = box.top + box.height / 2;
    for (let i = 0; i < n; i++) {
      const bit = document.createElement("span"), a = (i / n) * Math.PI * 2 + Math.random() * .4;
      const d = box.width * (.75 + Math.random() * .5);
      bit.className = "coin-spark";
      bit.style.cssText = `left:${cx}px;top:${cy}px;--dx:${Math.round(Math.cos(a) * d)}px;--dy:${Math.round(Math.sin(a) * d)}px;animation-delay:${(i % 3) * 40}ms`;
      document.body.appendChild(bit);
      setTimeout(() => bit.remove(), 900);
    }
  }

  function earn(el, turns = 3) {
    const c = build(el);
    if (reduce) return;
    // Whole turns from the current pose, so the idle sway picks up exactly where it left off.
    c.burst = {start: performance.now(), ms: 1100, from: c.angle, turns};
    el.classList.remove("coin-pop"); void el.offsetWidth; el.classList.add("coin-pop");
    sparkles(el);
  }

  function fly(x, y, text = "+10 XP") {
    const wrap = document.createElement("span");
    wrap.className = "coin-fly";
    wrap.style.cssText = `left:${x}px;top:${y}px`;
    wrap.innerHTML = `<span class="coin" data-coin="still" style="--coin:64px"></span><b>${text}</b>`;
    document.body.appendChild(wrap);
    const coin = wrap.querySelector(".coin");
    build(coin);
    if (!reduce) setTimeout(() => earn(coin, 4), 60);
    setTimeout(() => wrap.remove(), 1700);
  }

  function init(root = document) {
    root.querySelectorAll(".coin:not(.coin-fly .coin)").forEach(build);
    root.querySelectorAll(".coin[data-coin-tap]").forEach(el => {
      if (el._tapBound) return;
      el._tapBound = true;
      el.addEventListener("click", () => earn(el));
    });
  }

  window.Coin = {init, earn, fly, build};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => init());
  else init();
  if (!reduce) requestAnimationFrame(frame);
})();
