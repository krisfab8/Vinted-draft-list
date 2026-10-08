/* Browser camera: no photos leave the device until the listing is submitted.
   Modes (options.getMode): 'free' (default, original behaviour), 'guided' (one
   stitched ghost shape per step that shows the size then fades; the operator always
   presses the shutter; label shots wait for focus, retake when blurry) and
   'pro' (stitched frame, live quality dots, manual shots). Quality checks run on
   the phone via window.PhotoQuality; missing it, guided/pro still work manually. */
const CAMERA_SHAPES = {
  top: {label: 'Top', d: 'M140 196l-96 54 34 88 44-17v250h146V321l44 17 34-88-96-54c-10 25-37 42-55 42s-45-17-55-42z',
        back: 'M140 196l-96 54 34 88 44-17v250h146V321l44 17 34-88-96-54c-14 8-35 12-55 12s-41-4-55-12z', extra: 'M178 210l17 22 17-22'},
  long: {label: 'Long sleeve', d: 'M140 196l-70 30-34 260 46 8 26-190v267h174V304l26 190 46-8-34-260-70-30c-10 25-37 42-55 42s-45-17-55-42z',
         back: 'M140 196l-70 30-34 260 46 8 26-190v267h174V304l26 190 46-8-34-260-70-30c-14 8-35 12-55 12s-41-4-55-12z', extra: 'M178 210l17 22 17-22'},
  coat: {label: 'Coat', d: 'M140 196l-70 30-34 260 46 8 26-190v336h174V304l26 190 46-8-34-260-70-30c-10 25-37 42-55 42s-45-17-55-42z',
         back: 'M140 196l-70 30-34 260 46 8 26-190v336h174V304l26 190 46-8-34-260-70-30c-14 8-35 12-55 12s-41-4-55-12z', extra: 'M140 196l55 120 55-120M195 316v324'},
  trousers: {label: 'Trousers', d: 'M110 190h170l14 450h-78l-21-300-21 300h-78z', extra: 'M110 222h170'},
  shorts: {label: 'Shorts', d: 'M100 250h190l18 230h-88l-25-120-25 120h-88z', extra: 'M100 280h190'},
  dress: {label: 'Dress', d: 'M160 180h70l10 70 70 380H80l70-380z', extra: 'M150 250h90'},
  shoes: {label: 'Shoes', d: 'M45 540c0-40 10-90 30-120l60 30c20 10 50 10 70 0l20-10c20 40 60 60 110 70 20 4 30 20 30 40v30H45z', extra: 'M45 550h320'},
  hat: {label: 'Hat', d: 'M90 470c0-95 45-160 115-160s115 65 115 160h50c15 0 25 10 25 22H90z', extra: 'M205 310v-10'},
  other: {label: 'Other', d: 'M86 200h218a16 16 0 0116 16v388a16 16 0 01-16 16H86a16 16 0 01-16-16V216a16 16 0 0116-16z', extra: ''},
  brand: {label: 'Brand', d: 'M118 300h154a8 8 0 018 8v104a8 8 0 01-8 8H118a8 8 0 01-8-8V308a8 8 0 018-8z', extra: 'M140 345h110M160 375h70', label_: true},
  size: {label: 'Size', d: 'M148 320h94a8 8 0 018 8v74a8 8 0 01-8 8h-94a8 8 0 01-8-8v-74a8 8 0 018-8z', extra: 'M180 365h30', label_: true},
  care: {label: 'Care label', d: 'M136 190h118a8 8 0 018 8v424a8 8 0 01-8 8H136a8 8 0 01-8-8V198a8 8 0 018-8z', extra: 'M155 260h80M155 300h80M155 340h50M155 400h80', label_: true},
  frame: {label: '', d: 'M44 150h302a16 16 0 0116 16v290a16 16 0 01-16 16H44a16 16 0 01-16-16V166a16 16 0 0116-16z', extra: ''},
};
const CAMERA_NOUNS = {top: 'top', long: 'top', coat: 'coat', trousers: 'trousers', shorts: 'shorts', dress: 'dress',
                      shoes: 'shoe', hat: 'hat', other: 'item'};
const CAMERA_LABEL_HINTS = {brand: 'Brand label, in focus', size: 'Size label, in focus', care: 'Care label, in focus'};
const GUIDE_SHOW_MS = 2000, FOCUS_WAIT_MS = 2500;
// Few groups, each with the shots that sell that kind of item. Roles map to the saved photo slots.
const CAMERA_GARMENTS = ['top', 'coat', 'trousers', 'dress', 'shoes', 'hat', 'other'];
const CAMERA_GROUPS = {top: {label: 'Tops', sub: 'T-shirts, jumpers'}, coat: {label: 'Coats', sub: 'Jackets, gilets'},
  trousers: {label: 'Bottoms', sub: 'Trousers, shorts'}, dress: {label: 'Dresses', sub: 'Dresses, skirts'},
  shoes: {label: 'Shoes', sub: 'Trainers, boots'}, hat: {label: 'Hats', sub: 'Caps, beanies'}, other: {label: 'Other', sub: 'Bags, scarves'}};

function cameraSteps(shape) {
  const label = (role, text, ghost, hint) => ({role, label: text, ghost, kind: 'label', hint});
  const shot = (role, text, ghost, hint, back = false) => ({role, label: text, ghost, kind: 'garment', hint, back});
  if (shape === 'shoes') return [
    shot('front', 'Left side', 'shoes', 'Photograph the left side about this size'),
    shot('back', 'Right side', 'shoes', 'Now the right side'),
    shot('extra', 'Sole', 'other', 'Turn it over: the whole sole'),
    label('model_size', 'Size tag', 'size', 'Size tag inside, in focus'),
    label('brand', 'Logo', 'brand', 'Logo or brand, in focus'),
  ];
  if (shape === 'hat') return [
    shot('front', 'Front', 'hat'),
    shot('back', 'Back', 'hat', 'Now the back'),
    shot('extra', 'Brim', 'other', 'Close-up of the brim'),
    label('material', 'Inside', 'care', 'Inside and its tags, in focus'),
    label('brand', 'Logo', 'brand', 'Logo or brand, in focus'),
  ];
  if (shape === 'other') return [
    shot('front', 'Front', 'other'),
    shot('back', 'Back', 'other', 'Now the back'),
    shot('extra', 'Side', 'other', 'Another angle'),
    label('brand', 'Logo', 'brand', 'Logo or brand, in focus'),
    label('model_size', 'Tag', 'size', 'Any tag or size, in focus'),
  ];
  return [
    shot('front', 'Front', shape),
    shot('back', 'Back', shape, '', true),
    label('brand', 'Brand', 'brand'),
    label('model_size', 'Size', 'size'),
    label('material', 'Care label', 'care'),
  ];
}

function cameraIcon(key, {back = false, stroke = '#1D1D1F', size = 56, filled = false} = {}) {
  const s = CAMERA_SHAPES[key] || CAMERA_SHAPES.other;
  const d = back && s.back ? s.back : s.d;
  const extra = back ? '' : s.extra;
  // Viewbox fitted per shape so every icon reads at the same size.
  const boxes = {top: '24 176 342 415', long: '16 176 358 415', coat: '16 176 358 484', trousers: '40 170 310 490',
    shorts: '42 200 306 330', dress: '50 160 290 490', shoes: '25 330 360 300', hat: '70 250 345 300',
    other: '50 180 290 460', brand: '70 220 250 280', size: '95 250 200 230', care: '60 170 270 480', frame: '0 120 390 540'};
  if (filled) return `<svg width="${size}" height="${size}" viewBox="${boxes[key]}" aria-hidden="true"><path d="${d}" fill="${stroke}"/></svg>`;
  return `<svg width="${size}" height="${size}" viewBox="${boxes[key]}" fill="none" stroke="${stroke}" stroke-width="14" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">`
    + `<path d="${d}" stroke-dasharray="26 20"/>${extra ? `<path d="${extra}" stroke-width="12"/>` : ''}</svg>`;
}

function createPhotoCamera({getPhotos, addPhotos, removePhoto, pickGallery, pickNativeCamera,
                            getMode = () => 'free', setMode = () => {}, getRole = () => null,
                            noteQuality = () => {}, getQuality = () => null, onAnalyse = () => {}}) {
  const el = id => document.getElementById(id);
  const dialog = el('photoCamera'), video = el('cameraPreview');
  let stream = null, generation = 0, facing = 'environment', busy = false;
  let thumbnailUrls = [], resumeOnVisible = false, torchOn = false;
  // Guided/pro state.
  let shape = 'top', steps = cameraSteps('top'), stepIndex = 0, extraStep = false;
  let qualityTimer = null, previousGrey = null, ticks = 0, qualityCanvas = null, lastGrade = null;
  let guideTimer = null, guideShowing = false, focusWait = null;
  let review = null, panelUrls = [];
  const debug = typeof location !== 'undefined' && /[?&]camdebug=1/.test(location.search || '');
  const mode = () => { const m = getMode(); return m === 'guided' || m === 'pro' ? m : 'free'; };
  const quality = () => (typeof window !== 'undefined' && window.PhotoQuality) || null;

  function message(text) { el('cameraMessage').textContent = text; }
  function stop() {
    generation++;
    stopQuality();
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null; video.srcObject = null; torchOn = false;
    el('cameraTorch').hidden = true;
    el('cameraTorch').setAttribute('aria-pressed', 'false');
    el('cameraShutter').disabled = true;
  }
  function currentStep() {
    if (mode() === 'pro') return {role: null, label: '', ghost: 'frame', kind: 'garment'};
    if (extraStep) return {role: 'extra', label: 'Flaws', ghost: 'other', kind: 'garment'};
    return steps[stepIndex] || steps[0];
  }
  function refresh() {
    thumbnailUrls.forEach(url => URL.revokeObjectURL(url)); thumbnailUrls = [];
    const files = getPhotos(), strip = el('cameraPhotos'); strip.replaceChildren();
    files.forEach((file, index) => {
      const url = URL.createObjectURL(file); thumbnailUrls.push(url);
      const thumb = document.createElement('button'); thumb.type = 'button';
      thumb.className = 'camera-thumb'; thumb.setAttribute('aria-label', `Remove photo ${index + 1}`);
      const image = document.createElement('img'); image.src = url; image.alt = `Photo ${index + 1}`;
      const cross = document.createElement('span'); cross.textContent = '×'; cross.setAttribute('aria-hidden', 'true');
      thumb.append(image, cross); thumb.onclick = () => { removePhoto(index); refresh(); };
      const q = getQuality(file);
      if (q && !q.ok) { const flag = document.createElement('i'); flag.className = 'camera-thumb-flag'; flag.textContent = '!'; thumb.append(flag); }
      strip.appendChild(thumb);
    });
    strip.scrollLeft = strip.scrollWidth;
    // Guided: the photo just taken sits bottom-left, in place of the gallery button.
    const last = el('cameraLast'), showLast = mode() === 'guided' && files.length > 0;
    if (last) {
      last.hidden = !showLast;
      if (showLast) last.innerHTML = `<img src="${thumbnailUrls[thumbnailUrls.length - 1]}" alt="Last photo">`;
    }
    el('cameraGallery').hidden = showLast;
    el('cameraDone').textContent = files.length ? `Done · ${files.length}` : 'Done';
    el('cameraShutter').disabled = busy || !stream || !video.videoWidth || files.length >= 20;
    if (files.length >= 20) message('20 photos added. Remove a photo to take another.');
  }

  /* ── Guide overlay ── */
  function setGuide() {
    const guided = mode() !== 'free';
    const modeBtn = el('cameraModeBtn');   // switch Guided/Pro from inside the camera
    if (modeBtn) { modeBtn.hidden = !el('cameraIntro'); modeBtn.querySelector('span').textContent = mode() === 'pro' ? 'Pro' : 'Guided'; }
    dialog.classList?.toggle?.('camera-guided', mode() === 'guided');
    dialog.classList?.toggle?.('camera-pro', mode() === 'pro');
    const ghost = el('cameraGhost');
    if (!ghost) return;
    ghost.hidden = !guided;
    if (!guided) return;
    const step = currentStep(), s = CAMERA_SHAPES[step.ghost] || CAMERA_SHAPES.other;
    const d = step.back && s.back ? s.back : s.d;
    const [fill, stitch, extra] = ['cameraGhostFill', 'cameraGhostStitch', 'cameraGhostExtra'].map(el);
    fill.setAttribute('d', d); stitch.setAttribute('d', d);
    extra.setAttribute('d', step.back ? '' : s.extra);
    // Stitch runs parallel to the edge: inside garments, just outside labels.
    ['cameraMaskInFill', 'cameraMaskInEdge', 'cameraMaskOutFill', 'cameraMaskOutEdge'].forEach(id => el(id)?.setAttribute('d', d));
    stitch.setAttribute('mask', s.label_ ? 'url(#ghostMaskOut)' : 'url(#ghostMaskIn)');
    if (el('cameraStep')) el('cameraStep').textContent = step.label;
    const example = el('cameraExample');
    if (example) {
      example.hidden = mode() !== 'guided';
      el('cameraExampleArt').innerHTML = cameraIcon(step.ghost, {back: step.back, stroke: s.label_ ? '#F8FAFC' : '#4A6B8A', size: 46, filled: true});
    }
    const dots = el('cameraDots');
    if (dots) {
      dots.hidden = mode() !== 'guided' || extraStep;
      dots.innerHTML = steps.map((_, i) => `<i class="${i === stepIndex ? 'on' : i < stepIndex ? 'done' : ''}"></i>`).join('');
      dots.setAttribute('aria-label', `Step ${stepIndex + 1} of ${steps.length}`);
    }
    if (el('cameraSkip')) el('cameraSkip').hidden = mode() !== 'guided' || (!extraStep && stepIndex === 0);
    if (el('cameraQuality')) el('cameraQuality').hidden = mode() !== 'pro';
    el('cameraPhotos').hidden = mode() === 'guided';
    el('cameraDone').hidden = mode() === 'guided';
    clearGuideTimer();
    ghost.classList?.toggle?.('faded', false);
    guideShowing = mode() === 'guided';
    showState('start', {hint: guideShowing ? guideHint(step) : ''});
    // Guided: show the size for a moment, then get out of the way so the item is visible.
    if (guideShowing) guideTimer = setTimeout(() => {
      guideShowing = false; guideTimer = null;
      ghost.classList?.toggle?.('faded', true);
      if (!focusWait) showState(lastGrade ? stateFor(lastGrade, currentStep()) : 'start', {hint: lastGrade ? hintFor(lastGrade, currentStep()) : ''});
    }, GUIDE_SHOW_MS);
  }
  function clearGuideTimer() { if (guideTimer) clearTimeout(guideTimer); guideTimer = null; }
  function guideHint(step) {
    if (step.hint) return step.hint;
    if (step.kind === 'label') return CAMERA_LABEL_HINTS[step.ghost] || 'Label, in focus';
    if (extraStep) return 'Get close to the flaw';
    return `Photograph the ${CAMERA_NOUNS[shape] || 'item'} about this size`;
  }
  // Labels must be sharp; for garments only bad light is worth interrupting for.
  function matters(g, step) { return step.kind === 'label' ? g.ok : g.light !== 'bad'; }
  function stateFor(g, step) { return matters(g, step) ? 'ok' : 'fix'; }
  function hintFor(g, step) { return matters(g, step) ? '' : g.hint; }
  // state: 'start' (white), 'ok' (green), 'fix' (amber)
  function showState(state, {hint = '', checks = null} = {}) {
    const colour = state === 'ok' ? '#22C55E' : state === 'fix' ? '#F59E0B' : '#FFFFFF';
    ['cameraGhostStitch', 'cameraGhostExtra'].forEach(id => el(id)?.setAttribute('stroke', colour));
    const hintEl = el('cameraHint');
    if (hintEl) {
      hintEl.hidden = !hint;
      hintEl.textContent = hint;
      hintEl.className = 'camera-hint' + (state === 'ok' ? ' ok' : '');
    }
    const shutter = el('cameraShutter');
    shutter.classList?.toggle?.('ok', state === 'ok');
    shutter.classList?.toggle?.('fix', state === 'fix');
    if (checks && el('cameraQuality')) {
      el('cameraQuality').innerHTML = ['focus', 'light', 'glare'].map(key => `<i class="${checks[key]}"></i>`).join('');
      el('cameraQuality').setAttribute('aria-label', checks.ok ? 'Sharp, good light' : checks.hint);
    }
  }

  /* ── Live quality loop ── */
  function stopQuality() {
    if (qualityTimer) clearInterval(qualityTimer); qualityTimer = null; previousGrey = null; ticks = 0; lastGrade = null;
    if (focusWait) focusWait.done();
  }
  function startQuality() {
    stopQuality();
    if (mode() === 'free' || !quality()) return;
    qualityTimer = setInterval(tick, 250);
  }
  function tick() {
    if (!stream || !video.videoWidth || busy || review || !dialog.open) return;
    const step = currentStep(), q = quality();
    let m;
    try {
      qualityCanvas = qualityCanvas || document.createElement('canvas');
      m = q.measureSource(video, video.videoWidth, video.videoHeight, step.kind, previousGrey, qualityCanvas);
    } catch (_) { return; }
    previousGrey = m.grey; ticks++;
    const g = q.grade(m, step.kind);
    if (debug) message(`sharp ${m.sharpness.toFixed(0)} · light ${m.brightness.toFixed(0)} · glare ${(m.glare * 100).toFixed(1)}% · move ${m.motion == null ? '-' : m.motion.toFixed(1)}`);
    // A short settling time after each step before judging.
    if (ticks < 4) return;
    lastGrade = g;
    if (focusWait && g.ok) return focusWait.done();
    if (mode() === 'pro') return showState(g.ok ? 'ok' : 'fix', {hint: g.ok ? '' : g.hint, checks: g});
    if (guideShowing || focusWait) return;
    showState(stateFor(g, step), {hint: hintFor(g, step), checks: g});
  }
  // Guided label shots: wait (briefly) for a sharp frame before taking the photo.
  function waitForFocus() {
    if (mode() !== 'guided' || currentStep().kind !== 'label' || !qualityTimer || (lastGrade && lastGrade.ok)) return null;
    return new Promise(resolve => {
      const timer = setTimeout(() => focusWait && focusWait.done(), FOCUS_WAIT_MS);
      focusWait = {done() { clearTimeout(timer); focusWait = null; el('cameraShutter').classList?.toggle?.('arming', false); resolve(); }};
      el('cameraShutter').classList?.toggle?.('arming', true);
      showState('start', {hint: 'Focusing…'});
    });
  }
  async function shoot() {
    if (!stream || busy || focusWait || review) return;
    const request = generation, wait = waitForFocus();
    if (!wait) return capture();
    await wait;
    if (dialog.open && request === generation) await capture();
  }

  async function start() {
    stop();
    const request = generation;
    message('Opening camera…'); el('cameraNative').hidden = true; if (el('cameraRetry')) el('cameraRetry').hidden = true;
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('unsupported');
      const next = await navigator.mediaDevices.getUserMedia({audio:false, video:{
        facingMode:{ideal:facing}, width:{ideal:2048}, height:{ideal:1536}
      }});
      if (!dialog.open || request !== generation) { next.getTracks().forEach(track => track.stop()); return; }
      stream = next; video.srcObject = next;
      const actualFacing = next.getVideoTracks()[0].getSettings?.().facingMode;
      video.classList.toggle('camera-mirrored', actualFacing === 'user');
      await video.play();
      if (!dialog.open || request !== generation) return;
      const capabilities = next.getVideoTracks()[0].getCapabilities?.() || {};
      el('cameraTorch').hidden = !capabilities.torch;
      if ((capabilities.focusMode || []).includes('continuous')) {
        next.getVideoTracks()[0].applyConstraints?.({advanced: [{focusMode: 'continuous'}]})?.catch?.(() => {});
      }
      message(''); refresh(); startQuality();
    } catch (error) {
      if (!dialog.open || request !== generation) return;
      stop();
      message(error.name === 'NotAllowedError'
        ? 'Camera is blocked for this site. Tap the icon left of the web address → Permissions → Camera → Allow, then Try again. Or use your phone camera.'
        : 'Live camera is unavailable here. You can still use your phone camera or choose photos.');
      el('cameraNative').hidden = false;
      if (el('cameraRetry')) el('cameraRetry').hidden = false;
    }
  }
  function close() {
    resumeOnVisible = false; stop(); clearGuideTimer(); hidePanels();
    thumbnailUrls.forEach(url => URL.revokeObjectURL(url)); thumbnailUrls = [];
    document.body.style.overflow = previousOverflow;
    if (dialog.open) dialog.close();
  }
  let previousOverflow = '';
  function open() {
    if (dialog.open) return;
    previousOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
    dialog.showModal(); refresh();
    const intro = el('cameraIntro');
    if (intro && !['guided', 'pro', 'free'].includes(getMode())) return showPanel('mode');
    if (intro && mode() === 'guided') return showPanel('pick');
    setGuide(); start();
  }

  /* ── Capture ── */
  async function capture() {
    if (!stream || busy || !video.videoWidth || getPhotos().length >= 20) return;
    busy = true; refresh();
    const request = generation, step = currentStep();
    try {
      const canvas = document.createElement('canvas');
      const ratio = Math.min(1, 2048 / Math.max(video.videoWidth, video.videoHeight));
      canvas.width = Math.round(video.videoWidth * ratio); canvas.height = Math.round(video.videoHeight * ratio);
      canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
      let result = null;
      if (mode() !== 'free' && quality()) {
        try {
          const m = quality().measureSource(canvas, canvas.width, canvas.height, step.kind);
          result = Object.assign(quality().grade(m, step.kind), {sharpness: m.sharpness});
        } catch (_) { result = null; }
      }
      const blob = await new Promise((resolve, reject) => canvas.toBlob(b => b ? resolve(b) : reject(new Error('encode')), 'image/jpeg', .92));
      if (!dialog.open || request !== generation) return;
      const file = new File([blob], `camera-${Date.now()}.jpg`, {type:'image/jpeg'});
      // Guided: a blurry label is worth a retake; garments are kept (flagged) to stay fast.
      if (mode() === 'guided' && result && !result.ok && step.kind === 'label') { showReview(file, result, step); return; }
      accept(file, result, step);
    } catch (_) { if (dialog.open && request === generation) message('Photo could not be taken. Please try again.'); }
    finally { busy = false; if (dialog.open) refresh(); }
  }
  function accept(file, result, step) {
    if (mode() === 'guided') {
      addPhotos([file], step.role);
      noteQuality(file, result);
      refresh();
      const last = el('cameraLast');
      if (last) { last.classList?.remove?.('pop'); void last.offsetWidth; last.classList?.add?.('pop'); }
      advance();
    } else {
      addPhotos([file]);
      if (result) noteQuality(file, result);
      message(mode() === 'pro' && result && !result.ok ? `Added · ${result.hint.toLowerCase()}` : 'Photo added');
    }
  }
  function nextMissingStep(from) {
    const roles = getPhotos().map(getRole), used = new Set(roles);
    const extras = roles.filter(role => role === 'extra').length;
    // Extra-slot steps (sole, brim, side) count as done in order, one extra photo each.
    for (let i = from; i < steps.length; i++) {
      if (steps[i].role !== 'extra') { if (!used.has(steps[i].role)) return i; continue; }
      if (steps.slice(0, i + 1).filter(step => step.role === 'extra').length > extras) return i;
    }
    return steps.length;
  }
  // Next shot still needed; when started part-way through (tapped a shot), loop back once for the
  // shots before it. Skipped shots stay skipped.
  let firstStep = 0, stopAt = Infinity;
  function nextStep() {
    const ahead = nextMissingStep(stepIndex + 1);
    if (ahead < Math.min(steps.length, stopAt)) return ahead;
    const earlier = nextMissingStep(0);
    if (stopAt === Infinity && earlier < firstStep) { stopAt = firstStep; return earlier; }
    return steps.length;
  }
  function advance() {
    if (extraStep) { extraStep = false; return showPanel('done'); }
    stepIndex = nextStep();
    if (stepIndex >= steps.length) return showPanel('done');
    setGuide(); startQuality();
  }
  function skip() {
    if (extraStep) { extraStep = false; return showPanel('done'); }
    stepIndex = nextStep();
    if (stepIndex >= steps.length) return showPanel('done');
    setGuide(); startQuality();
  }

  /* ── Panels: mode, pick, shots, review, done ── */
  function hidePanels() {
    panelUrls.forEach(url => URL.revokeObjectURL(url)); panelUrls = [];
    review = null;
    if (el('cameraIntro')) { el('cameraIntro').hidden = true; el('cameraIntro').innerHTML = ''; }
    if (el('cameraReview')) el('cameraReview').hidden = true;
  }
  const back = target => `<button type="button" class="ci-back" data-go="${target}" aria-label="Back"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg></button>`;
  function showPanel(name) {
    const intro = el('cameraIntro');
    if (!intro) { setGuide(); return start(); }
    stop(); hidePanels();
    let html = '';
    if (name === 'mode') {
      const current = getMode();
      html = `<button type="button" class="ci-back" data-go="close" aria-label="Close"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button>
        <div class="ci-kicker">Photos</div><h2>How do you list?</h2>
        <button type="button" class="ci-mode${current !== 'pro' ? ' on' : ''}" data-mode="guided">
          <span class="ci-mode-art">${cameraIcon('top', {size: 42})}</span>
          <span class="ci-mode-text"><b>Guided</b><small>Step by step</small><span class="ci-bars">${'<i></i>'.repeat(5)}</span></span>
        </button>
        <button type="button" class="ci-mode${current === 'pro' ? ' on' : ''}" data-mode="pro">
          <span class="ci-mode-art pro">${cameraIcon('frame', {size: 42, stroke: '#0F172A'})}</span>
          <span class="ci-mode-text"><b>Pro</b><small>Fast, many items</small><span class="ci-chips"><em>Bulk</em><em>Sharpness check</em></span></span>
        </button>
        <div class="ci-grow"></div>
        <button type="button" class="ci-primary" data-go="after-mode">Continue</button>
        <div class="ci-note">Change any time</div>`;
    } else if (name === 'pick') {
      html = `${back('mode')}<h2>What is it?</h2><div class="ci-grid">
        ${CAMERA_GARMENTS.map(key => `<button type="button" class="ci-tile${key === shape ? ' on' : ''}" data-shape="${key}">
          ${cameraIcon(key, {stroke: key === shape ? '#1D1D1F' : '#86868B'})}<span>${CAMERA_GROUPS[key].label}</span><small class="ci-sub">${CAMERA_GROUPS[key].sub}</small></button>`).join('')}
        </div>`;
    } else if (name === 'shots') {
      html = `${back('pick')}<h2>${steps.length} photos <span class="ci-soft">+ flaws</span></h2><div class="ci-grid">
        ${steps.map((step, i) => `<button type="button" class="ci-tile static" data-step="${i}" aria-label="Take ${step.label} photo"><b class="ci-num">${i + 1}</b>${cameraIcon(step.ghost, {back: step.back})}<span>${step.label}</span></button>`).join('')}
        <button type="button" class="ci-tile dashed" data-go="flaws" aria-label="Take flaw photos">${'<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#64748B" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>'}<span>Flaws</span></button>
        </div><div class="ci-grow"></div><button type="button" class="ci-primary" data-go="camera">Start</button>`;
    } else if (name === 'done') {
      const files = getPhotos();
      html = `<div class="ci-badge-ok"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg></div><h2>All set</h2><div class="ci-grid">
        ${files.map((file, i) => {
          const url = URL.createObjectURL(file); panelUrls.push(url);
          const q = getQuality(file), role = getRole(file);
          const label = (steps.find(step => step.role === role) || {label: 'Extra'}).label;
          return `<div class="ci-photo"><img src="${url}" alt="${label}"><span class="ci-photo-label">${label}</span>
            <i class="ci-photo-flag ${q && !q.ok ? 'warn' : 'ok'}" aria-label="${q && !q.ok ? q.hint : 'Sharp'}">${q && !q.ok ? '!' : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>'}</i></div>`;
        }).join('')}
        ${files.length < 20 ? `<button type="button" class="ci-tile dashed" data-go="flaws"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#64748B" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg><span>Flaws</span></button>` : ''}
        </div><div class="ci-grow"></div><button type="button" class="ci-primary" data-go="analyse">Analyse</button>`;
    }
    intro.innerHTML = `<div class="ci-page">${html}</div>`;
    intro.hidden = false;
  }
  function showReview(file, result, step) {
    stopQuality();
    const url = URL.createObjectURL(file); panelUrls.push(url);
    review = {file, result, step};
    const box = el('cameraReview');
    if (!box) { review = null; return accept(file, result, step); }
    el('cameraReviewImage').src = url;
    const title = result.hint === 'More light' ? 'Too dark' : result.hint === 'Avoid glare' ? 'Glare' : 'Blurry';
    el('cameraReviewTitle').textContent = title;
    el('cameraReviewText').textContent = step.kind === 'label' ? "Can't read the label" : 'Photo is not sharp';
    box.hidden = false;
  }
  function onIntroClick(event) {
    const target = event.target.closest?.('button');
    if (!target) return;
    if (target.dataset.mode) {
      setMode(target.dataset.mode);
      return showPanel('mode');
    }
    if (target.dataset.shape) { shape = target.dataset.shape; steps = cameraSteps(shape); return showPanel('shots'); }  // one tap picks
    if (target.dataset.step) {   // one tap on a shot opens the camera at that shot
      hidePanels(); extraStep = false;
      stopAt = Infinity; stepIndex = firstStep = Math.min(Number(target.dataset.step) || 0, steps.length - 1);
      setGuide(); return start();
    }
    const go = target.dataset.go;
    if (go === 'close') return close();
    if (go === 'mode') return showPanel('mode');
    if (go === 'pick') return showPanel('pick');
    if (go === 'shots') return showPanel('shots');
    if (go === 'after-mode') {
      if (!['guided', 'pro'].includes(getMode())) setMode('guided');
      if (mode() === 'guided') return showPanel('pick');
      hidePanels(); setGuide(); return start();
    }
    if (go === 'camera') {
      hidePanels(); extraStep = false;
      stopAt = Infinity; stepIndex = firstStep = nextMissingStep(0);
      if (stepIndex >= steps.length) return showPanel('done');
      setGuide(); return start();
    }
    if (go === 'flaws') { hidePanels(); extraStep = true; setGuide(); return start(); }
    if (go === 'analyse') { close(); return onAnalyse(); }
  }

  el('cameraClose').onclick = close; el('cameraDone').onclick = close;
  if (el('cameraModeBtn')) el('cameraModeBtn').onclick = () => { if (!busy) showPanel('mode'); };
  el('cameraShutter').onclick = shoot;
  el('cameraFlip').onclick = () => { if (!busy) { facing = facing === 'environment' ? 'user' : 'environment'; start(); } };
  el('cameraGallery').onclick = pickGallery;
  el('cameraNative').onclick = pickNativeCamera;
  if (el('cameraRetry')) el('cameraRetry').onclick = () => start();
  el('cameraTorch').onclick = async () => {
    const track = stream?.getVideoTracks()[0]; if (!track) return;
    try {
      await track.applyConstraints({advanced:[{torch:!torchOn}]}); torchOn = !torchOn;
      el('cameraTorch').setAttribute('aria-pressed', String(torchOn));
    } catch (_) { message('Light is unavailable on this camera.'); }
  };
  if (el('cameraIntro')) el('cameraIntro').addEventListener('click', onIntroClick);
  if (el('cameraSkip')) el('cameraSkip').onclick = skip;
  if (el('cameraReviewRetake')) el('cameraReviewRetake').onclick = () => { el('cameraReview').hidden = true; review = null; startQuality(); };
  if (el('cameraReviewKeep')) el('cameraReviewKeep').onclick = () => {
    const pending = review; el('cameraReview').hidden = true; review = null;
    if (pending) accept(pending.file, pending.result, pending.step);
  };
  video.addEventListener('loadeddata', refresh);
  dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
  dialog.addEventListener('close', () => { if (stream) close(); });
  window.addEventListener('pagehide', close);
  document.addEventListener('visibilitychange', () => {
    if (!dialog.open) return;
    if (document.hidden) { resumeOnVisible = !!stream; stop(); }
    else if (resumeOnVisible) { resumeOnVisible = false; start(); }
  });
  // A photo from the phone's own camera app (live camera blocked or unavailable): in Guided it fills the
  // current shot and moves to the next one, exactly like the shutter; otherwise it is just added.
  function acceptNative(files) {
    const list = Array.from(files || []);
    if (!list.length) return;
    if (mode() === 'guided') {
      const step = currentStep();
      addPhotos(list.slice(0, 1), step.role);
      refresh(); advance();
      if (dialog.open && !el('cameraIntro')?.innerHTML) message('Photo added · next: ' + currentStep().label);
    } else {
      addPhotos(list);
      message('Photo added');
    }
  }
  return {open, close, refresh, showPanel, acceptNative};
}
