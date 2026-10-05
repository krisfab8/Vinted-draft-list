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
  async function saveSales() {
    const response = await nativeFetch('/api/sales/backup', {cache:'no-store'});
    if (!response.ok) throw new Error('Sales backup failed');
    const rows = await response.json();
    await transaction('readwrite', store => store.put({folder:'__sales_history__',rows,savedAt:Date.now()}));
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
      const history = saved.find(item => item.folder === '__sales_history__');
      if (history?.rows?.length) {
        const restoredSales = await nativeFetch('/api/sales/restore', {
          method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(history.rows)
        });
        if (!restoredSales.ok) throw new Error('Sales history restoration failed');
      }
      let restored = 0;
      for (const item of saved) {
        if (item.folder === '__sales_history__' || item.deleted || current.has(item.folder)) continue;
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
      await saveSales();
      if (saved.length || listings.length) notice('Backed up on this device');
      if (restored && ['/drafts','/sold'].includes(location.pathname)) location.reload();
    } catch (_) {
      notice('Device backup unavailable — download a backup to keep your drafts');
    }
  }
  // Return successful edits immediately; back up in the background. In-app
  // navigation waits for the queue so switching to Drafts cannot interrupt saves.
  window.fetch = async (...args) => {
    const url = new URL(typeof args[0] === 'string' ? args[0] : args[0].url, location.origin);
    const method = String(args[1]?.method || args[0]?.method || 'GET').toUpperCase();
    const deleting = url.origin === location.origin && method === 'DELETE'
      && url.pathname.match(/^\/listing\/(upload_[a-f0-9]{8})$/);
    if (deleting) {
      // Record deletion before touching the server. If local storage fails,
      // leave the server item intact instead of later resurrecting an old copy.
      try {
        await pending;
        await transaction('readwrite', store => store.put({folder:deleting[1],deleted:true,savedAt:Date.now()}));
      } catch (error) {
        notice('Could not update device backup — listing was not deleted');
        throw error;
      }
    }
    const response = await nativeFetch(...args);
    if (deleting && !response.ok) queue(() => save(deleting[1]));
    if (response.ok && url.origin === location.origin && method !== 'GET') {
      const match = url.pathname.match(/^(?:\/listing\/|\/api\/listing\/|\/reprice\/|\/regen\/)(upload_[a-f0-9]{8})(?:\/[^/]+)?$/);
      if (match) {
        if (method === 'DELETE') notice('Listing deleted');
        else queue(async () => { await save(match[1]); if (url.pathname.endsWith('/outcome')) await saveSales(); });
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
    if (url.origin !== location.origin || !['/', '/drafts', '/sold', '/stats'].includes(url.pathname)) return;
    event.preventDefault();
    pending.then(() => { location.href = anchor.href; });
  });
  window.addEventListener('pageshow', event => {
    if (event.persisted && ['/drafts','/sold'].includes(location.pathname)) location.reload();
  });
  window.DraftArchive = {ready: queue(recover), flush: () => pending, save: folder => queue(() => save(folder))};
})();
