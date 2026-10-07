/* Photo quality on the phone: sharpness, light and glare. No network, no AI cost.
   Sharpness is the variance of the Laplacian (edge strength) on a small greyscale
   copy of the area that matters; labels need a higher bar than whole garments.
   Thresholds are first guesses to tune on real phones (?camdebug=1 shows values). */
(function (root) {
  const LIMITS = {
    label:   {sharp: 120, soft: 60, glare: 0.05},
    garment: {sharp: 35,  soft: 18, glare: 0.10},
  };
  const DARK = 55, BRIGHT = 235, MOVING = 7, SIDE = 360;

  function greyscale(rgba, count) {
    const grey = new Float32Array(count);
    for (let i = 0, p = 0; i < count; i++, p += 4) grey[i] = 0.299 * rgba[p] + 0.587 * rgba[p + 1] + 0.114 * rgba[p + 2];
    return grey;
  }

  // rgba: Uint8ClampedArray (ImageData.data) of width x height.
  function measure(rgba, width, height, previousGrey) {
    const grey = greyscale(rgba, width * height);
    let sum = 0, bright = 0;
    for (let i = 0; i < grey.length; i++) { sum += grey[i]; if (grey[i] > 250) bright++; }
    let lapSum = 0, lapSq = 0, n = 0;
    for (let y = 1; y < height - 1; y++) {
      for (let x = 1; x < width - 1; x++) {
        const i = y * width + x;
        const v = grey[i - width] + grey[i + width] + grey[i - 1] + grey[i + 1] - 4 * grey[i];
        lapSum += v; lapSq += v * v; n++;
      }
    }
    const mean = n ? lapSum / n : 0;
    let motion = null;
    if (previousGrey && previousGrey.length === grey.length) {
      let diff = 0;
      for (let i = 0; i < grey.length; i++) diff += Math.abs(grey[i] - previousGrey[i]);
      motion = diff / grey.length;
    }
    return {sharpness: n ? lapSq / n - mean * mean : 0, brightness: grey.length ? sum / grey.length : 0,
            glare: grey.length ? bright / grey.length : 0, motion, grey};
  }

  // kind: 'label' | 'garment'. Returns per-check states and one short hint.
  function grade(m, kind) {
    const lim = LIMITS[kind] || LIMITS.garment;
    const light = m.brightness < DARK ? 'bad' : m.brightness > BRIGHT ? 'warn' : 'ok';
    const glare = m.glare > lim.glare ? 'bad' : 'ok';
    const moving = m.motion != null && m.motion > MOVING;
    const focus = moving ? 'warn' : m.sharpness >= lim.sharp ? 'ok' : m.sharpness >= lim.soft ? 'warn' : 'bad';
    const ok = focus === 'ok' && light !== 'bad' && glare === 'ok';
    const hint = ok ? 'Sharp'
      : light === 'bad' ? 'More light'
      : glare === 'bad' ? 'Avoid glare'
      : moving ? 'Hold still'
      : kind === 'label' ? 'Move closer' : 'Hold still';
    return {focus, light, glare, ok, hint};
  }

  // Area to judge, as fractions of the frame: labels sit in the middle.
  function region(kind, width, height) {
    const fx = kind === 'label' ? 0.5 : 0.75, fy = kind === 'label' ? 0.6 : 0.75;
    const w = Math.round(width * fx), h = Math.round(height * fy);
    return {x: Math.round((width - w) / 2), y: Math.round((height - h) / 2), w, h};
  }

  // Draw a source (video, image, bitmap) region into a small canvas and measure it.
  function measureSource(source, srcWidth, srcHeight, kind, previousGrey, canvas) {
    const r = region(kind, srcWidth, srcHeight);
    const scale = Math.min(1, SIDE / Math.max(r.w, r.h));
    const w = Math.max(8, Math.round(r.w * scale)), h = Math.max(8, Math.round(r.h * scale));
    const c = canvas || document.createElement('canvas');
    c.width = w; c.height = h;
    const ctx = c.getContext('2d', {willReadFrequently: true});
    ctx.drawImage(source, r.x, r.y, r.w, r.h, 0, 0, w, h);
    return measure(ctx.getImageData(0, 0, w, h).data, w, h, previousGrey);
  }

  async function checkFile(file, kind) {
    const url = URL.createObjectURL(file);
    try {
      const img = new Image(); img.src = url; await img.decode();
      const m = measureSource(img, img.naturalWidth, img.naturalHeight, kind);
      return Object.assign(grade(m, kind), {sharpness: m.sharpness, brightness: m.brightness, glareShare: m.glare});
    } finally { URL.revokeObjectURL(url); }
  }

  const kindForRole = role => ['brand', 'model_size', 'material'].includes(role) ? 'label' : 'garment';

  root.PhotoQuality = {LIMITS, measure, grade, region, measureSource, checkFile, kindForRole};
})(typeof window !== 'undefined' ? window : globalThis);
