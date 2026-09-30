import { useCallback, useEffect, useRef, useState } from 'react'
import TxnDetail from './TxnDetail'
import { Icon, LevelBadge, Empty } from './ui'
import { api } from '../lib/api'
import { money, ago, flag, pretty } from '../lib/format'

const FILTERS = [
  { key: 'flagged', label: 'Pending' },
  { key: 'reviewed', label: 'Reviewed' },
  { key: 'cleared', label: 'Cleared' },
  { key: 'fraud', label: 'Fraud' },
  { key: 'flagged,reviewed,cleared,fraud', label: 'All flagged' },
]

export default function ReviewQueue({ selected, setSelected, tick, stats, reviewer, toast, now }) {
  const [filter, setFilter] = useState('flagged')
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  const [loaded, setLoaded] = useState(false)
  const listRef = useRef(null)

  const load = useCallback(() => {
    api.txns({ status: filter, q, sort: filter === 'flagged' ? 'risk' : 'time', limit: 300 })
      .then((r) => { setRows(r); setLoaded(true) }).catch(() => {})
  }, [filter, q])

  useEffect(() => { const h = setTimeout(load, 150); return () => clearTimeout(h) }, [load, tick.txn, tick.review])

  const idx = rows.findIndex((r) => r.id === selected)
  useEffect(() => { if (!selected && rows.length) setSelected(rows[0].id) }, [rows, selected, setSelected])

  const act = useCallback(async (id, action, note) => {
    const next = rows[idx + 1]?.id || rows[idx - 1]?.id
    try {
      const t = await api.review(id, action, reviewer, note)
      toast({ tone: action === 'fraud' ? 'crit' : action === 'cleared' ? 'good' : 'info',
        title: action === 'reopen' ? 'Reopened' : `Marked ${action === 'fraud' ? 'as fraud' : action}`,
        body: `${money(t.amount)} · ${t.merchant} · ${t.user_name}` })
      if (filter === 'flagged' && action !== 'reopen' && next) setSelected(next)
      load()
    } catch (e) { toast({ tone: 'crit', title: 'Action failed', body: e.message }) }
  }, [rows, idx, reviewer, toast, filter, load, setSelected])

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.metaKey || e.ctrlKey) return
      const k = e.key.toLowerCase()
      if (k === 'j' || k === 'arrowdown') { e.preventDefault(); rows[idx + 1] && setSelected(rows[idx + 1].id) }
      else if (k === 'k' || k === 'arrowup') { e.preventDefault(); rows[idx - 1] && setSelected(rows[idx - 1].id) }
      else if (selected && k === 'r') act(selected, 'reviewed', '')
      else if (selected && k === 'c') act(selected, 'cleared', '')
      else if (selected && k === 'f') act(selected, 'fraud', '')
      else if (selected && k === 'u') act(selected, 'reopen', '')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [rows, idx, selected, act, setSelected])

  useEffect(() => {
    listRef.current?.querySelector('.q-row.sel')?.scrollIntoView({ block: 'nearest' })
  }, [selected])

  const count = (k) => k.includes(',') ? (stats?.flagged_total ?? '') : (stats?.by_status?.[k] ?? 0)

  return (
    <div className="page queue">
      <div className="q-side card">
        <div className="q-filters">
          {FILTERS.map((f) => (
            <button key={f.key} className={`chip ${filter === f.key ? 'on' : ''}`} onClick={() => { setFilter(f.key); setSelected(null) }}>
              {f.label} <b className="mono">{count(f.key)}</b>
            </button>
          ))}
        </div>
        <label className="search"><Icon name="search" size={14} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search cardholder, merchant, city, TX id…" />
        </label>
        <div className="q-list" ref={listRef}>
          {loaded && rows.length === 0 && (
            <Empty title={filter === 'flagged' ? 'Queue is clear' : 'Nothing here'}>
              {filter === 'flagged' ? 'Every flagged transaction has a verdict. Launch an attack to see new flags arrive.' : 'Try another filter.'}
            </Empty>
          )}
          {rows.map((t) => (
            <button key={t.id} className={`q-row lv-${t.risk_level} ${t.id === selected ? 'sel' : ''}`} onClick={() => setSelected(t.id)}>
              <div className="q-r1">
                <b className="mono">{money(t.amount)}</b>
                <span className="q-merch">{t.merchant}</span>
                <LevelBadge level={t.risk_level} score={t.risk_score} />
              </div>
              <div className="q-r2 muted">
                <span>{flag(t.country)} {t.user_name}</span>
                <span className="q-rules">{t.flags.slice(0, 3).map((f) => pretty(f.rule_id)).join(' · ')}</span>
                <span className="mono">{ago(t.ts, now)}</span>
              </div>
            </button>
          ))}
        </div>
        <div className="kbd-help"><Icon name="keyboard" size={13} /><kbd>J</kbd><kbd>K</kbd> move <kbd>R</kbd> reviewed <kbd>C</kbd> clear <kbd>F</kbd> fraud <kbd>U</kbd> reopen</div>
      </div>
      <TxnDetail id={selected} onAct={act} tick={`${tick.review}-${tick.alert}`} toast={toast} />
    </div>
  )
}
