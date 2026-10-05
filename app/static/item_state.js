/* Serialize saves and reject edits from a stale tab without discarding its text. */
(() => {
  const nativeFetch = window.fetch.bind(window);
  const revisions = new Map(), pending = new Map();
  function folderFor(url, options) {
    const match = url.pathname.match(/^\/(?:listing|api\/listing|regen|reprice)\/([A-Za-z0-9_.-]+)/);
    if (match) return match[1];
    if (['/create-draft', '/edit-draft', '/create-listing'].includes(url.pathname)) {
      try { return JSON.parse(options.body).folder; } catch (_) { return null; }
    }
    return null;
  }
  window.ItemState = {remember: (folder, revision) => {if (revision) revisions.set(folder, revision);}};
  window.fetch = async (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.origin);
    if (url.origin !== location.origin) return nativeFetch(input, options);
    const method = String(options.method || input.method || 'GET').toUpperCase();
    const folder = folderFor(url, options);
    const mutation = !['GET', 'HEAD', 'OPTIONS'].includes(method);
    async function send() {
      const headers = new Headers(options.headers || input.headers);
      if (mutation && folder && revisions.has(folder)) headers.set('If-Match', revisions.get(folder));
      const response = await nativeFetch(input, {...options, headers, cache:'no-store'});
      if (response.status === 409) {
        const message = 'This item changed in another tab. Copy any unsaved text, then reload the item before saving.';
        window.alert(message);
        throw new Error(message);
      }
      const revision = response.headers.get('X-Item-Revision');
      if (response.ok && revision) {
        let target = folder;
        if (!target && url.pathname === '/upload') target = (await response.clone().json()).folder;
        if (target) revisions.set(target, revision);
      }
      return response;
    }
    if (!folder || !mutation) return send();
    const previous = pending.get(folder) || Promise.resolve();
    const result = previous.catch(() => {}).then(send);
    pending.set(folder, result);
    try { return await result; }
    finally { if (pending.get(folder) === result) pending.delete(folder); }
  };
})();
