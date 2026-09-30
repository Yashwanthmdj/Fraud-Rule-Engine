import { useCallback, useEffect, useRef, useState } from 'react'
import CommandCenter from './components/CommandCenter'
import ReviewQueue from './components/ReviewQueue'
import RulesLab from './components/RulesLab'
import AttackLab from './components/AttackLab'
import Alerts from './components/Alerts'
import { Icon } from './components/ui'
import { api } from './lib/api'
import { useLive } from './lib/useLive'
import { money, flag, pretty } from './lib/format'

const TABS = [
  { key: 'command', label: 'Command Center', icon: 'radar' },
  { key: 'queue', label: 'Review Queue', icon: 'inbox' },
  { key: 'rules', label: 'Rules Lab', icon: 'sliders' },
  { key: 'attack', label: 'Attack Lab', icon: 'zap' },
  { key: 'alerts', label: 'Alerts', icon: 'bell' },
]

const store = {
  get: (k, d) => { try { return localStorage.getItem(k) ?? d } catch { return d } },
  set: (k, v) => { try { localStorage.setItem(k, v) } catch { /* private mode */ } },
}

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const o = ctx.createOscillator(), g = ctx.createGain()
    o.type = 'triangle'; o.frequency.setValueAtTime(880, ctx.currentTime); o.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.25)
    g.gain.setValueAtTime(0.08, ctx.currentTime); g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.3)
    o.connect(g).connect(ctx.destination); o.start(); o.stop(ctx.currentTime + 0.3)
  } catch { /* audio unavailable */ }
}

export default function App() {
  const initialTxn = new URLSearchParams(location.search).get('txn')
  const [tab, setTab] = useState(initialTxn ? 'queue' : (location.hash.slice(1) || 'command'))
  const [selected, setSelected] = useState(initialTxn)
  const [feed, setFeed] = useState([])
  const [stats, setStats] = useState(null)
  const [toasts, setToasts] = useState([])
  const [tick, setTick] = useState({ txn: 0, review: 0, alert: 0, rules: 0 })
  const [now, setNow] = useState(Date.now())
  const [sound, setSound] = useState(store.get('aegis.sound', '0') === '1')
  const [reviewer, setReviewer] = useState(store.get('aegis.reviewer', 'analyst'))
  const [threat, setThreat] = useState(0)
  const soundRef = useRef(sound)
  soundRef.current = sound

  useEffect(() => { const h = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(h) }, [])
  useEffect(() => { history.replaceState(null, '', `${location.pathname}${location.search}#${tab}`) }, [tab])
  useEffect(() => {
    api.txns({ limit: 200 }).then(setFeed).catch(() => {})
    api.stats().then(setStats).catch(() => {})
  }, [])

  const toast = useCallback((t) => {
    const id = Math.random().toString(36).slice(2)
    setToasts((xs) => [{ id, ...t }, ...xs].slice(0, 4))
    setTimeout(() => setToasts((xs) => xs.filter((x) => x.id !== id)), t.ttl || 5000)
  }, [])

  const select = useCallback((id) => { setSelected(id); setTab('queue') }, [])
  const bump = (k) => setTick((t) => ({ ...t, [k]: t[k] + 1 }))

  const status = useLive((m) => {
    switch (m.type) {
      case 'hello':
      case 'stats':
        setStats(m.data); break
      case 'txn': {
        const t = m.data
        setFeed((f) => [t, ...f.filter((x) => x.id !== t.id)].slice(0, 400))
        if (t.risk_score >= (stats?.thresholds?.flag ?? 35)) bump('txn')
        if (t.risk_level === 'critical') {
          setThreat((n) => n + 1)
          if (soundRef.current) beep()
          toast({ tone: 'crit', title: `${t.decision === 'decline' ? 'Declined' : t.decision === 'hold' ? 'Held' : 'Critical'} · ${money(t.amount)} at ${t.merchant}`,
            body: `${flag(t.country)} ${t.user_name} · ${t.flags.map((f) => f.rule_name).join(' + ')}`, onClick: () => select(t.id), ttl: 7000 })
        }
        break
      }
      case 'review':
        setFeed((f) => f.map((x) => (x.id === m.data.id ? m.data : x))); bump('review'); break
      case 'alert':
        bump('alert')
        if (m.data.status === 'sent' || m.data.status === 'simulated')
          toast({ tone: 'info', title: `${m.data.channel.toUpperCase()} alert ${m.data.status === 'sent' ? 'sent' : 'dispatched (dry-run)'}`, body: m.data.subject, onClick: () => select(m.data.txn_id) })
        break
      case 'rules':
        bump('rules')
        if (m.data.event === 'reloaded') {
          m.data.added?.forEach((r) => toast({ tone: 'good', title: `Rule hot-loaded: ${pretty(r)}`, body: 'Live on the next transaction. No restart needed.' }))
          m.data.removed?.forEach((r) => toast({ tone: 'info', title: `Rule unloaded: ${pretty(r)}` }))
          Object.entries(m.data.errors || {}).forEach(([f, e]) => toast({ tone: 'crit', title: `Quarantined ${f}`, body: e }))
        }
        break
      default:
    }
  })

  const pending = stats?.pending ?? 0

  return (
    <div className={`app ${threat % 2 ? 'threat-a' : threat ? 'threat-b' : ''}`}>
      <header className="top">
        <div className="brand">
          <svg width="26" height="26" viewBox="0 0 32 32"><path d="M16 2 4 7v8c0 7.5 5.1 13.3 12 15 6.9-1.7 12-7.5 12-15V7z" fill="url(#g)" /><path d="M11 16.5l3.5 3.5L21.5 12" stroke="#fff" strokeWidth="2.6" fill="none" strokeLinecap="round" /><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#9b7bff" /><stop offset="1" stopColor="#4c6fff" /></linearGradient></defs></svg>
          <div><b>AEGIS</b><span>Fraud Rule Engine</span></div>
        </div>
        <nav>
          {TABS.map((t) => (
            <button key={t.key} className={tab === t.key ? 'on' : ''} onClick={() => setTab(t.key)}>
              <Icon name={t.icon} size={15} /><span>{t.label}</span>
              {t.key === 'queue' && pending > 0 && <em className="mono">{pending}</em>}
            </button>
          ))}
        </nav>
        <div className="top-r">
          <span className={`conn ${status}`} title={`WebSocket ${status}`}><i />{status === 'live' ? `LIVE · ${stats?.tpm ?? 0}/min` : status}</span>
          <span className={`pill ${stats?.alerts?.mode === 'live' ? 'st-cleared' : 'st-flagged'}`} title="AWS notifier mode">
            {stats?.alerts?.mode === 'live' ? 'AWS LIVE' : 'AWS DRY-RUN'}
          </span>
          <button className="icon-btn" title={sound ? 'Mute critical chime' : 'Chime on critical'} onClick={() => { setSound(!sound); store.set('aegis.sound', sound ? '0' : '1') }}>
            <Icon name={sound ? 'volume' : 'mute'} size={15} />
          </button>
          <label className="who" title="Reviewer name recorded in the audit trail">
            <span>{reviewer.slice(0, 1).toUpperCase()}</span>
            <input value={reviewer} onChange={(e) => { setReviewer(e.target.value); store.set('aegis.reviewer', e.target.value) }} />
          </label>
        </div>
      </header>

      <main>
        {tab === 'command' && <CommandCenter stats={stats} feed={feed} onSelect={select} now={now} />}
        {tab === 'queue' && <ReviewQueue selected={selected} setSelected={setSelected} tick={tick} stats={stats} reviewer={reviewer} toast={toast} now={now} />}
        {tab === 'rules' && <RulesLab tick={tick} stats={stats} toast={toast} />}
        {tab === 'attack' && <AttackLab stats={stats} feed={feed} toast={toast} onSelect={select} tick={tick} />}
        {tab === 'alerts' && <Alerts tick={tick} onSelect={select} toast={toast} />}
      </main>

      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast t-${t.tone}`} onClick={() => { t.onClick?.(); setToasts((xs) => xs.filter((x) => x.id !== t.id)) }}>
            <b>{t.title}</b>{t.body && <span>{t.body}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}