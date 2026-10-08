/* Bottom sheets (<dialog class="sn-sheet">): swipe down to close, or tap outside.
   Same feel as the item sheet on Drafts; a field being typed in keeps the sheet open. */
(() => {
  let sheet = null, startY = 0, startT = 0, dy = 0;
  document.addEventListener('touchstart', e => {
    const s = e.target.closest?.('dialog.sn-sheet[open]:not(#hintsPanel)');  // the Details sheet has its own
    if (!s || e.target.closest('input, textarea, select') || s.scrollTop > 0) { sheet = null; return; }
    sheet = s; startY = e.touches[0].clientY; startT = Date.now(); dy = 0;
  }, {passive: true});
  document.addEventListener('touchmove', e => {
    if (!sheet) return;
    dy = Math.max(0, e.touches[0].clientY - startY);
    sheet.style.transition = 'none';
    sheet.style.transform = dy ? `translateY(${dy}px)` : '';
    if (dy) e.preventDefault();
  }, {passive: false});
  document.addEventListener('touchend', () => {
    if (!sheet) return;
    const s = sheet, fast = dy > 40 && dy / Math.max(1, Date.now() - startT) > 0.5;
    sheet = null;
    s.style.transition = 'transform .22s ease';
    if (dy > 110 || fast) {
      s.style.transform = 'translateY(100%)';
      setTimeout(() => { s.close('cancel'); s.style.transform = ''; s.style.transition = ''; }, 220);
    } else {
      s.style.transform = '';
    }
  });
  // Tap on the dimmed area outside the sheet closes it.
  document.addEventListener('click', e => {
    const s = e.target;
    if (!(s instanceof HTMLDialogElement) || !s.classList.contains('sn-sheet') || !s.open) return;
    const r = s.getBoundingClientRect();
    if (e.clientY < r.top || e.clientY > r.bottom || e.clientX < r.left || e.clientX > r.right) s.close('cancel');
  });
})();
