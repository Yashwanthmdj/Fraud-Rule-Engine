import { useEffect, useState } from 'react'
import WorldMap from './WorldMap'
import { Icon, LevelBadge, RiskRing, StatusPill, Empty } from './ui'
import { api } from '../lib/api'
import { money, dateTime, clock, flag, pretty, ago } from '../lib/format'

function TravelEvidence({ ev, id }) {
  return (
    <div className="evi">
      <WorldMap compact arcs={[{ id, from: ev.from, to: ev.to, speed: ev.speed_kmh }]} />
      <div className="evi-stats">
        <div><span>From</span><b>{flag(ev.from.country)} {ev.from.city}</b><small className="mono">{clock(ev.from.ts + 'Z')}</small></div>
        <div><span>To</span><b>{flag(ev.to.country)} {ev.to.city}</b><small className="mono">{clock(ev.to.ts + 'Z')}</small></div>
        <div><span>Distance</span><b className="mono">{Math.round(ev.distance_km).toLocaleString()} km</b><small>in {ev.minutes >= 1 ? `${Math.round(ev.minutes)} min` : `${Math.round(ev.minutes * 60)}s`}</small></div>
        <div className="crit"><span>Implied speed</span><b className="mono">{Math.round(ev.speed_kmh).toLocaleString()} km/h</b><small>{(ev.speed_kmh / 900).toFixed(0)}× a jet airliner</small></div>
      </div>
    </div>
  )
}

function VelocityEvidence({ ev }) {
  const tl = [...ev.timeline].sort((a, b) => new Date(a.ts) - new Date(b.ts))
  const t0 = new Date(tl[0].ts).getTime(), t1 = new Date(tl[tl.length - 1].ts).getTime()
  const span = Math.max(1, t1 - t0)
  const maxAmt = Math.max(...tl.map((t) => t.amount))
  return (
    <div className="evi">
      <div className="vel">
        <div className="vel-axis" />
        {tl.map((t, i) => (
          <div key={t.id} className={`vel-dot ${i === tl.length - 1 ? 'last' : ''}`}
            style={{ left: `${((new Date(t.ts).getTime() - t0) / span) * 100}%`, width: 8 + 18 * Math.sqrt(t.amount / maxAmt), height: 8 + 18 * Math.sqrt(t.amount / maxAmt) }}
            title={`${money(t.amount)} · ${t.merchant}`} />
        ))}
      </div>
      <div className="evi-stats">
        <div><span>Transactions</span><b className="mono">{ev.count}</b><small>in {ev.span_seconds}s</small></div>
        <div><span>Window limit</span><b className="mono">{ev.window_seconds}s</b><small>sliding</small></div>
        <div><span>Micro-charges</span><b className="mono">{ev.micro_charges}</b><small>card-testing probes</small></div>
        <div><span>Total</span><b className="mono">{money(ev.total_amount)}</b><small>in the burst</small></div>
      </div>
    </div>
  )
}

function AmountEvidence({ ev, timeline, amount }) {
  if (ev.mode !== 'baseline') return null
  const vals = timeline.map((t) => t.amount).filter((a) => a > 0)
  const lo = Math.log10(Math.max(1, Math.min(...vals, ev.median) * 0.7)), hi = Math.log10(Math.max(...vals, amount) * 1.3)
  const x = (a) => `${((Math.log10(Math.max(1, a)) - lo) / (hi - lo)) * 100}%`
  return (
    <div className="evi">
      <div className="strip">
        {vals.map((a, i) => <i key={i} className="strip-dot" style={{ left: x(a) }} />)}
        <div className="strip-med" style={{ left: x(ev.median) }}><span>median {money(ev.median)}</span></div>
        <div className="strip-this" style={{ left: x(amount) }}><span>this {money(amount)}</span></div>
      </div>
      <div className="evi-stats">
        <div><span>Typical ticket</span><b className="mono">{money(ev.median)}</b><small>median of {ev.history_size}</small></div>
        <div className="crit"><span>This one</span><b className="mono">{ev.ratio}×</b><small>the usual</small></div>
        <div><span>Robust z-score</span><b className="mono">{ev.z}</b><small>median + MAD</small></div>
        <div><span>Largest before</span><b className="mono">{money(ev.max_seen)}</b><small>in 90 days</small></div>
      </div>
    </div>
  )
}

const ACTIONS = [
  { key: 'reviewed', label: 'Mark reviewed', hint: 'R', icon: 'eye', cls: '' },
  { key: 'cleared', label: 'Clear', hint: 'C', icon: 'check', cls: 'good' },
  { key: 'fraud', label: 'Confirm fraud', hint: 'F', icon: 'alert', cls: 'crit' },
]

export default function TxnDetail({ id, onAct, tick, toast }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!id) return
    let live = true
    api.txn(id).then((x) => live && (setD(x), setErr(null))).catch((e) => live && setErr(e.message))
    return () => { live = false }
  }, [id, tick])
  useEffect(() => setNote(''), [id])

  if (!id) return <div className="detail"><Empty icon="inbox" title="Select a transaction">Use <kbd>J</kbd>/<kbd>K</kbd> to move through the queue.</Empty></div>
  if (err) return <div className="detail"><Empty icon="alert" title="Could not load">{err}</Empty></div>
  if (!d || d.id !== id) return <div className="detail"><div className="skeleton" /></div>

  const act = async (a) => {
    setBusy(true)
    try { await onAct(d.id, a, note); setNote('') } finally { setBusy(false) }
  }
  const safe = d.flags.reduce((p, f) => p * (1 - f.contribution), 1)
  const hits = d.flags

  return (
    <div className="detail">
      <div className="dt-head">
        <RiskRing score={d.risk_score} level={d.risk_level} />
        <div className="dt-title">
          <div className="dt-amt mono">{money(d.amount, 2)} <small>{d.currency}</small></div>
          <div className="dt-merch">{d.merchant} <span className="muted">· {pretty(d.category)}</span></div>
          <div className="dt-meta">
            <LevelBadge level={d.risk_level} /> <StatusPill status={d.status} />
            {d.scenario && <span className="pill st-scenario" title="Injected by the Attack Lab (ground truth)">⚑ {pretty(d.scenario.split(':')[0])}</span>}
          </div>
        </div>
      </div>

      <div className="facts">
        <div><span>Cardholder</span><b>{d.user_name}</b><small className="mono">{d.user_id}</small></div>
        <div><span>Where</span><b>{flag(d.country)} {d.city || '—'}</b><small>{d.channel === 'online' ? 'online / IP geo' : 'card present'}</small></div>
        <div><span>When</span><b>{dateTime(d.ts)}</b><small>{ago(d.ts)} ago</small></div>
        <div><span>Device</span><b className="mono">{d.device_id || '—'}</b><small className="mono">{d.ip}</small></div>
        <div><span>Decision time</span><b className="mono">{d.latency_ms} ms</b><small className="mono">{d.id}</small></div>
      </div>

      <div className="decide">
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add an investigation note (optional)…" />
        {d.status === 'clean' || d.status === 'flagged'
          ? ACTIONS.map((a) => (
            <button key={a.key} disabled={busy} className={`btn ${a.cls}`} onClick={() => act(a.key)}>
              <Icon name={a.icon} size={14} />{a.label}<kbd>{a.hint}</kbd>
            </button>))
          : <button className="btn" disabled={busy} onClick={() => act('reopen')}><Icon name="undo" size={14} />Reopen<kbd>U</kbd></button>}
      </div>

      <section>
        <h4>Why AEGIS scored it {Math.round(d.risk_score)}</h4>
        {hits.length === 0 && <p className="muted">No rule fired. This transaction matches the cardholder's normal behaviour.</p>}
        <div className="why">
          {hits.map((h) => (
            <div key={h.rule_id} className="why-row">
              <div className="why-top">
                <b>{h.rule_name}</b>
                <span className="mono muted">confidence {Math.round(h.score * 100)}% × weight {h.weight}</span>
                <span className="mono why-pts">+{Math.round(h.contribution * 100)}</span>
              </div>
              <div className="why-track"><div className="why-fill" style={{ width: `${h.contribution * 100}%` }} /></div>
              <p>{h.reason}</p>
              {h.rule_id === 'impossible_travel' && <TravelEvidence ev={h.evidence} id={d.id} />}
              {h.rule_id === 'velocity' && <VelocityEvidence ev={h.evidence} />}
              {h.rule_id === 'amount_anomaly' && <AmountEvidence ev={h.evidence} timeline={d.timeline} amount={d.amount} />}
            </div>
          ))}
        </div>
        {hits.length > 1 && (
          <div className="formula mono">
            risk = 1 − {hits.map((h) => `(1 − ${h.contribution.toFixed(2)})`).join(' · ')} = 1 − {safe.toFixed(3)} = <b>{((1 - safe) * 100).toFixed(1)}</b>
            <span className="muted"> · noisy-OR fusion: independent evidence compounds</span>
          </div>
        )}
      </section>

      <div className="two">
        <section>
          <h4>Cardholder baseline</h4>
          <div className="profile">
            <div><span>Home</span><b>{d.cardholder.home}</b></div>
            <div><span>Typical ticket</span><b className="mono">{money(d.cardholder.median_amount)}</b></div>
            <div><span>History</span><b className="mono">{d.cardholder.txn_count} txns</b></div>
            <div><span>Countries</span><b>{d.cardholder.countries.map(flag).join(' ')}</b></div>
            <div><span>Devices</span><b className="mono">{d.cardholder.devices.length}</b></div>
            <div><span>Prior fraud</span><b className="mono">{d.cardholder.fraud_count}</b></div>
          </div>
          <div className="mini-tl">
            {d.timeline.slice(0, 12).map((t) => (
              <div key={t.id} className={`mini-row ${t.id === d.id ? 'me' : ''}`}>
                <span className="mono muted">{ago(t.ts)}</span>
                <span>{flag(t.country)} {t.merchant}</span>
                <span className="mono">{money(t.amount)}</span>
                <i className={`lvl-dot lv-${t.risk_level}`} />
              </div>
            ))}
          </div>
        </section>
        <section>
          <h4>Alerts &amp; audit trail</h4>
          {d.notifications.length === 0 && <p className="muted">No alert: risk stayed below the alert threshold.</p>}
          {d.notifications.map((n, i) => (
            <div key={i} className="audit">
              <Icon name={n.channel === 'sns' ? 'bell' : 'mail'} size={14} />
              <span><b>{n.channel.toUpperCase()}</b> {n.status}{n.mode === 'dry-run' && n.status === 'simulated' ? ' (dry-run)' : ''}{n.error && <em className="muted"> · {n.error}</em>}</span>
              <span className="mono muted">{clock(n.ts)}</span>
            </div>
          ))}
          <div className="row gap">
            <a className="btn sm" href={`/api/notifications/preview/${d.id}`} target="_blank" rel="noreferrer"><Icon name="mail" size={13} />Preview email</a>
            <button className="btn sm" onClick={async () => { const r = await api.resendAlert(d.id); toast({ tone: 'info', title: `Alert ${r[0]?.status}`, body: r[0]?.subject }) }}><Icon name="send" size={13} />Send alert now</button>
          </div>
          {d.reviews.map((r, i) => (
            <div key={i} className="audit">
              <Icon name={r.action === 'fraud' ? 'alert' : r.action === 'cleared' ? 'check' : r.action === 'reopen' ? 'undo' : 'eye'} size={14} />
              <span><b>{r.reviewer}</b> {r.action === 'reopen' ? 'reopened' : `marked ${r.action}`}{r.note && <em className="muted"> · “{r.note}”</em>}</span>
              <span className="mono muted">{clock(r.ts)}</span>
            </div>
          ))}
        </section>
      </div>
    </div>
  )
}
