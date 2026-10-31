// Per-browser preferences in localStorage (it may be unavailable or full: never throw).

export const store = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem('tdt.' + key);
      return v === null ? fallback : JSON.parse(v);
    } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem('tdt.' + key, JSON.stringify(value)); } catch { /* no storage */ }
  },
};
