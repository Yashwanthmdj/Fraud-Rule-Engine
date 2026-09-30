async function req(method, path, body) {
  const res = await fetch(path, {
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
  simulator: () => req('GET', '/api/simulator'),
  patchSim: (p) => req('PATCH', '/api/simulator', p),
  launch: (name) => req('POST', `/api/scenarios/${name}`),
}
