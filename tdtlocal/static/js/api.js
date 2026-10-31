// Calls to the local server.

/** GET/POST returning `{ok, data}`; `data` is null if the body is not JSON. Rejects if the server is unreachable. */
export async function api(path, method = 'GET') {
  const r = await fetch(path, { method, cache: 'no-store' });
  let data = null;
  try { data = await r.json(); } catch { /* no body */ }
  return { ok: r.ok, data };
}

/** Any method with an optional JSON body: `{ok, status, data}`. Rejects if the server is unreachable. */
export async function requestJson(path, method = 'GET', body = undefined) {
  const options = { method, cache: 'no-store' };
  if (body !== undefined) {
    options.headers = { 'Content-Type': 'application/json' };
    options.body = JSON.stringify(body);
  }
  const r = await fetch(path, options);
  let data = null;
  try { data = await r.json(); } catch { /* no body */ }
  return { ok: r.ok, status: r.status, data };
}

/** POST a JSON body; rejects if the server is unreachable. */
export function postJson(path, body, options = {}) {
  return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), ...options });
}

/** Turn live transcription on or off for a playback session. Resolves to whether the server accepted it. */
export function postStt(tag, on) {
  return postJson('/api/stt', { s: tag, on }).then((r) => r.ok).catch(() => false);
}
