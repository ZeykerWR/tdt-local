// Credits page: show the running version.
fetch('/api/version', { cache: 'no-store' })
  .then((r) => r.json())
  .then((d) => { document.getElementById('version').textContent = 'v' + d.version; })
  .catch(() => { /* the page is useful without it */ });
