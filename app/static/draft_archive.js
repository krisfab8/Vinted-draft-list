/* Device backup for the private test app. No AI calls; existing server edits win. */
(() => {
  const nativeFetch = window.fetch.bind(window);
  let database, pending = Promise.resolve();
  const notice = message => {
    const element = document.getElementById('draft-backup-status');
    if (element) element.textContent = message;
  };
  function db() {
    if (!database) database = new Promise((resolve, reject) => {
      const request = indexedDB.open('vinted-draft-backups', 1);
      request.onupgradeneeded = () => request.result.createObjectStore('items', {keyPath:'folder'});
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(new Error('Browser storage blocked'));
    });
    return database;
  }
  async function transaction(mode, action) {
    const connection = await db();
    return new Promise((resolve, reject) => {
      const tx = connection.transaction('items', mode);
      const request = action(tx.objectStore('items'));
      tx.oncomplete = () => resolve(request.result);
      tx.onerror = tx.onabort = () => reject(tx.error || new Error('Backup failed'));
    });
  }
  async function save(folder) {
    const response = await nativeFetch('/api/private/backup?folder=' + encodeURIComponent(folder));
    if (!response.ok) throw new Error('Backup download failed');
    const blob = await response.blob();
    await transaction('readwrite', store => store.put({folder, blob, savedAt:Date.now()}));
    notice('Backed up on this device');
  }
  function queue(action) {
    notice('Saving device backup…');
    pending = pending.then(action).catch(() => {
      notice('Device backup failed — download a backup before leaving');
    });
    return pending;
  }
  async function recover() {
    try {
      const response = await nativeFetch('/api/listings');
      if (!response.ok) throw new Error('Cannot load drafts');
      const listings = await response.json();
      const current = new Set(listings.map(item => item.folder));
      const saved = await transaction('readonly', store => store.getAll());
      let restored = 0;
      for (const item of saved) {
        if (item.deleted || current.has(item.folder)) continue;
        const result = await nativeFetch('/api/private/restore-backup', {
          method:'POST', headers:{'Content-Type':'application/zip'}, body:item.blob
        });
        if (!result.ok) {
          // Another tab may have restored it. Never overwrite the server copy.
          const exists = await nativeFetch('/listing/' + encodeURIComponent(item.folder));
          if (!exists.ok) throw new Error('Draft restoration failed');
        } else restored++;
      }
      for (const item of listings) await save(item.folder);
      if (saved.length || listings.length) notice('Backed up on this device');
      if (restored && location.pathname === '/drafts') location.reload();
    } catch (_) {
      notice('Device backup unavailable — download a backup to keep your drafts');
    }
  }
  // Return successful edits immediately; back up in the background. In-app
  // navigation waits for the queue so switching to Drafts cannot interrupt saves.
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    const url = new URL(typeof args[0] === 'string' ? args[0] : args[0].url, location.origin);
    const method = String(args[1]?.method || args[0]?.method || 'GET').toUpperCase();
    if (response.ok && url.origin === location.origin && method !== 'GET') {
      const match = url.pathname.match(/^(?:\/listing\/|\/api\/listing\/|\/reprice\/|\/regen\/)(upload_[a-f0-9]{8})(?:\/[^/]+)?$/);
      if (match) {
        if (method === 'DELETE') queue(() => transaction('readwrite', store => store.put({folder:match[1],deleted:true,savedAt:Date.now()})));
        else queue(() => save(match[1]));
      } else if (url.pathname === '/upload') {
        const result = await response.clone().json();
        if (result.folder) queue(() => save(result.folder));
      }
    }
    return response;
  };
  document.addEventListener('click', event => {
    const anchor = event.target.closest('a[href]');
    if (!anchor || anchor.target || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const url = new URL(anchor.href, location.origin);
    if (url.origin !== location.origin || !['/', '/drafts', '/stats'].includes(url.pathname)) return;
    event.preventDefault();
    pending.then(() => { location.href = anchor.href; });
  });
  window.addEventListener('pageshow', event => {
    if (event.persisted && location.pathname === '/drafts') location.reload();
  });
  window.DraftArchive = {ready: queue(recover), flush: () => pending};
})();
