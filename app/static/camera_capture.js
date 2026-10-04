/* Browser camera: no photos leave the device until the listing is submitted. */
function createPhotoCamera({getPhotos, addPhotos, removePhoto, pickGallery, pickNativeCamera}) {
  const el = id => document.getElementById(id);
  const dialog = el('photoCamera'), video = el('cameraPreview');
  let stream = null, generation = 0, facing = 'environment', busy = false;
  let thumbnailUrls = [], resumeOnVisible = false, torchOn = false;
  function message(text) { el('cameraMessage').textContent = text; }
  function stop() {
    generation++;
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null; video.srcObject = null; torchOn = false;
    el('cameraTorch').hidden = true;
    el('cameraTorch').setAttribute('aria-pressed', 'false');
    el('cameraShutter').disabled = true;
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
      strip.appendChild(thumb);
    });
    strip.scrollLeft = strip.scrollWidth;
    el('cameraDone').textContent = files.length ? `Done · ${files.length}` : 'Done';
    el('cameraShutter').disabled = busy || !stream || !video.videoWidth || files.length >= 20;
    if (files.length >= 20) message('20 photos added. Remove a photo to take another.');
  }
  async function start() {
    stop();
    const request = generation;
    message('Opening camera…'); el('cameraNative').hidden = true;
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
      message(''); refresh();
    } catch (error) {
      if (!dialog.open || request !== generation) return;
      stop();
      message(error.name === 'NotAllowedError'
        ? 'Camera permission is off. Allow camera access in your browser, or use your phone camera below.'
        : 'Live camera is unavailable here. You can still use your phone camera or choose photos.');
      el('cameraNative').hidden = false;
    }
  }
  function close() {
    resumeOnVisible = false; stop();
    thumbnailUrls.forEach(url => URL.revokeObjectURL(url)); thumbnailUrls = [];
    document.body.style.overflow = previousOverflow;
    if (dialog.open) dialog.close();
  }
  let previousOverflow = '';
  function open() {
    if (dialog.open) return;
    previousOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
    dialog.showModal(); refresh(); start();
  }
  async function capture() {
    if (!stream || busy || !video.videoWidth || getPhotos().length >= 20) return;
    busy = true; refresh();
    const request = generation;
    try {
      const canvas = document.createElement('canvas');
      const ratio = Math.min(1, 2048 / Math.max(video.videoWidth, video.videoHeight));
      canvas.width = Math.round(video.videoWidth * ratio); canvas.height = Math.round(video.videoHeight * ratio);
      canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise((resolve, reject) => canvas.toBlob(b => b ? resolve(b) : reject(new Error('encode')), 'image/jpeg', .92));
      if (!dialog.open || request !== generation) return;
      addPhotos([new File([blob], `camera-${Date.now()}.jpg`, {type:'image/jpeg'})]);
      message('Photo added');
    } catch (_) { if (dialog.open && request === generation) message('Photo could not be taken. Please try again.'); }
    finally { busy = false; if (dialog.open) refresh(); }
  }
  el('cameraClose').onclick = close; el('cameraDone').onclick = close;
  el('cameraShutter').onclick = capture;
  el('cameraFlip').onclick = () => { if (!busy) { facing = facing === 'environment' ? 'user' : 'environment'; start(); } };
  el('cameraGallery').onclick = pickGallery;
  el('cameraNative').onclick = pickNativeCamera;
  el('cameraTorch').onclick = async () => {
    const track = stream?.getVideoTracks()[0]; if (!track) return;
    try {
      await track.applyConstraints({advanced:[{torch:!torchOn}]}); torchOn = !torchOn;
      el('cameraTorch').setAttribute('aria-pressed', String(torchOn));
    } catch (_) { message('Light is unavailable on this camera.'); }
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
  return {open, close, refresh};
}
