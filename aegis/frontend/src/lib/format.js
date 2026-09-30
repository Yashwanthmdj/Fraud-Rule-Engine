export const money = (n, digits) => {
  if (n == null || Number.isNaN(n)) return '—'
  const d = digits ?? (Math.abs(n) >= 1000 ? 0 : 2)
  return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })
}

export const compactMoney = (n) => {
  if (!n) return '$0'
  if (n >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M'
  if (n >= 1e3) return '$' + (n / 1e3).toFixed(1) + 'k'
  return '$' + n.toFixed(0)
}

export const num = (n) => (n == null ? '—' : Number(n).toLocaleString('en-US'))

export function ago(iso, now = Date.now()) {
  const s = Math.max(0, (now - new Date(iso).getTime()) / 1000)
  if (s < 5) return 'now'
  if (s < 60) return `${Math.floor(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86400)}d`
}

export const clock = (iso) =>
  new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export const dateTime = (iso) =>
  new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })

export const flag = (cc) =>
  cc && cc.length === 2 ? String.fromCodePoint(...[...cc.toUpperCase()].map((c) => 0x1f1a5 + c.charCodeAt(0))) : '🌐'

export const LEVEL_LABEL = { low: 'Low', medium: 'Medium', high: 'High', critical: 'Critical' }

export const STATUS_LABEL = {
  clean: 'Clean', flagged: 'Pending review', reviewed: 'Reviewed', cleared: 'Cleared', fraud: 'Confirmed fraud',
}

export const levelOf = (score, t) => {
  if (score >= t.alert) return 'critical'
  if (score >= t.flag + (t.alert - t.flag) / 2) return 'high'
  if (score >= t.flag) return 'medium'
  return 'low'
}

export const pretty = (s) => (s || '').replace(/_/g, ' ')
