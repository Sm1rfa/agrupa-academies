import { useEffect, useState } from 'react';

const API = './api/index.php';

const cache = new Map();

export function apiUrl(route, params = {}) {
  const qs = new URLSearchParams({ r: route });
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '' && v !== false) qs.set(k, v === true ? '1' : v);
  }
  return `${API}?${qs}`;
}

/** Fetch an API route; re-runs when route/params change. Responses are memoized per URL. */
export function useApi(route, params = {}) {
  const url = apiUrl(route, params);
  const [state, setState] = useState(() =>
    cache.has(url) ? { data: cache.get(url), loading: false, error: null } : { data: null, loading: true, error: null });

  useEffect(() => {
    if (cache.has(url)) {
      setState({ data: cache.get(url), loading: false, error: null });
      return;
    }
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    fetch(url)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data) => {
        cache.set(url, data);
        if (alive) setState({ data, loading: false, error: null });
      })
      .catch((error) => alive && setState({ data: null, loading: false, error }));
    return () => {
      alive = false;
    };
  }, [url]);

  return state;
}
