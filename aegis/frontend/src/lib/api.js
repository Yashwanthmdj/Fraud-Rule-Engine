// Empty when the console is served by the backend itself (Render / Docker / run.sh).
// Set VITE_API_BASE=https://<your-service>.onrender.com when the console is hosted elsewhere (e.g. Vercel).
export const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')
export const apiUrl = (path) => API_BASE + path

async function req(method, path, body) {
  const res = await fetch(apiUrl(path), {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : res.statusText)
  return data
}

export const api = {
  stats: () => req('GET', '/api/stats'),
  txns: (params = {}) => req('GET', '/api/transactions?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== ''))),
  txn: (id) => req('GET', `/api/transactions/${id}`),
  ingest: (t) => req('POST', '/api/transactions', t),
  review: (id, action, reviewer, note) => req('POST', `/api/transactions/${id}/review`, { action, reviewer, note }),
  rules: () => req('GET', '/api/rules'),
  patchRule: (id, patch) => req('PATCH', `/api/rules/${id}`, patch),
  reloadRules: () => req('POST', '/api/rules/reload'),
  backtest: (body) => req('POST', '/api/backtest', body),
  settings: () => req('GET', '/api/settings'),
  thresholds: (t) => req('PATCH', '/api/settings/thresholds', t),
  notifications: () => req('GET', '/api/notifications?limit=200'),
  resendAlert: (id) => req('POST', `/api/notifications/test/${id}`),
  testAlert: () => req('POST', '/api/notifications/test'),
  recheckAlerts: () => req('POST', '/api/notifications/recheck'),
  simulator: () => req('GET', '/api/simulator'),
  patchSim: (p) => req('PATCH', '/api/simulator', p),
  launch: (name, userId) => req('POST', `/api/scenarios/${name}${userId ? `?user_id=${encodeURIComponent(userId)}` : ''}`),
}
