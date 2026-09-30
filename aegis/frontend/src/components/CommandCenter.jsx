import { useMemo } from 'react'
import WorldMap from './WorldMap'
import { Icon, LevelBadge, DecisionBadge, Empty } from './ui'
import { money, compactMoney, num, ago, flag, pretty, DECISION_LABEL } from '../lib/format'

function Kpi({ label, value, sub, tone, icon }) {
  return (
    <div className={`kpi ${tone || ''}`}>
      <div className="kpi-top"><Icon name={icon} size={14} /> {label}</div>
      <div className="kpi-val mono">{value}</div>
      <div className="kpi-sub">{sub}</div>
    </div>
  )
}

export function Kpis({ stats }) {
  const s = stats || {}
  const a = s.attacks || {}
  return (
    <div className="kpis">
      <Kpi icon="radar" label="Transactions scored" value={num(s.total)} sub={<><b className="mono">{s.tpm ?? 0}</b> in the last minute</>} />
      <Kpi icon="inbox" tone="warn" label="Awaiting review" value={num(s.pending)} sub={<>{compactMoney(s.exposure)} exposure on hold</>} />
      <Kpi icon="bell" tone="crit" label="High-risk alerts" value={num(s.alerts?.sent)} sub={<>{num(s.alerts?.suppressed)} de-duplicated · {s.alerts?.mode === 'live' ? 'AWS live' : 'dry-run'}</>} />
      <Kpi icon="shield" tone="good" label="Fraud confirmed" value={compactMoney(s.prevented)} sub={<>{num(s.by_status?.fraud || 0)} txns · {num(s.by_status?.cleared || 0)} cleared</>} />
      <Kpi icon="zap" label="Attacks caught" value={a.runs ? `${a.caught}/${a.runs}` : '—'}
        sub={a.avg_txns_to_detect ? <>detected by txn #{a.avg_txns_to_detect} on avg</> : 'launch one in Attack Lab'} />
      <Kpi icon="cpu" label="Decision latency" value={<>{s.avg_latency_ms ?? '—'}<small>ms</small></>} sub="validate → rules → decide → persist" />
    </div>
  )
}

function Throughput({ series = [], thresholds }) {
  const max = Math.max(4, ...series.map((d) => d.total))
  return (
    <div className="card">
      <div className="card-h"><h3>Throughput</h3><span className="muted">last 30 min · per minute</span></div>
      <div className="bars">
        {series.map((d) => (
          <div key={d.minute} className="bar" title={`${d.total} txns · ${d.flagged} flagged · ${d.critical} critical`}>
            <div className="bar-total" style={{ height: `${(d.total / max) * 100}%` }}>
              <div className="bar-flag" style={{ height: d.total ? `${(d.flagged / d.total) * 100}%` : 0 }} />
            </div>
          </div>
        ))}
      </div>
      <div className="legend"><span><i className="sw sw-total" />scored</span><span><i className="sw sw-flag" />flagged (≥ {thresholds?.flag})</span><span className="muted">−30m</span><span className="muted" style={{ marginLeft: 'auto' }}>now</span></div>
    </div>
  )
}

function RuleBreakdown({ rules = {} }) {
  const rows = Object.entries(rules).sort((a, b) => b[1].flags - a[1].flags)
  const max = Math.max(1, ...rows.map(([, r]) => r.flags))
  return (
    <div className="card">
      <div className="card-h"><h3>What's firing</h3><span className="muted">flags per rule · precision from reviewer verdicts</span></div>
      {rows.length === 0 && <Empty icon="radar" title="No flags yet">Launch an attack to see rules fire.</Empty>}
      <div className="rb">
        {rows.map(([id, r]) => (
          <div key={id} className="rb-row">
            <span className="rb-name">{pretty(id)}</span>
            <div className="rb-track"><div className="rb-fill" style={{ width: `${(r.flags / max) * 100}%` }} /></div>
            <span className="mono rb-n">{r.flags}</span>
            <span className={`mono rb-p ${r.precision == null ? 'muted' : r.precision >= 0.7 ? 'good' : 'warn'}`}>
              {r.precision == null ? 'unlabeled' : `${Math.round(r.precision * 100)}% precise`}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function LiveFeed({ feed, onSelect, now }) {
  return (
    <div className="card feed">
      <div className="card-h"><h3><span className="live-dot" />Live stream</h3><span className="muted">every transaction, scored in real time</span></div>
      <div className="feed-list">
        {feed.length === 0 && <Empty icon="radar" title="Waiting for traffic">Start the simulator or POST to /api/transactions.</Empty>}
        {feed.slice(0, 60).map((t) => (
          <button key={t.id} className={`feed-row lv-${t.risk_level} ${t.risk_score >= 35 ? 'hot' : ''}`} onClick={() => onSelect(t.id)}>
            <span className="feed-flag">{flag(t.country)}</span>
            <span className="feed-main">
              <b>{t.merchant}</b>
              <span className="muted">{t.user_name} · {t.city}{t.flags?.length ? ` · ${t.flags.map((f) => pretty(f.rule_id)).join(', ')}` : ''}</span>
            </span>
            <span className="feed-amt mono">{money(t.amount)}</span>
            <span className="feed-score"><LevelBadge level={t.risk_level} score={t.risk_score} />{t.decision && t.decision !== 'approve' && <DecisionBadge decision={t.decision} />}</span>
            <span className="feed-ago muted mono">{ago(t.ts, now)}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

const STAGES = [['validate', 'Validate'], ['history', 'Load history'], ['rules', 'Rules + decide'], ['persist', 'Persist']]

function Pipeline({ feed, stats }) {
  const recent = feed.filter((t) => t.stages).slice(0, 50)
  const avg = STAGES.map(([k]) => (recent.length ? recent.reduce((a, t) => a + (t.stages[k] || 0), 0) / recent.length : 0))
  const total = avg.reduce((a, b) => a + b, 0)
  const last = recent[0]
  const dec = stats?.by_decision || {}
  const decMax = Math.max(1, ...Object.values(dec))
  return (
    <div className="card">
      <div className="card-h"><h3><Icon name="cpu" size={15} /> Real-time pipeline</h3>
        <span className="muted">avg of the last {recent.length} transactions · the decision is returned to the payment switch synchronously</span></div>
      <div className="pipe">
        <div>
          <div className="pipe-bar">
            {STAGES.map(([k], i) => <div key={k} className={`pipe-seg pl-${k}`} style={{ flexGrow: avg[i] || 0.001 }} title={`${k}: ${avg[i].toFixed(2)} ms`} />)}
          </div>
          <div className="pipe-legend">
            {STAGES.map(([k, label], i) => <span key={k}><i className={`pl-${k}`} />{label} <b className="mono">{avg[i].toFixed(2)} ms</b></span>)}
            <span>Total <b className="mono">{total.toFixed(2)} ms</b></span>
          </div>
          {last && (
            <div className="pipe-last">
              <span className="muted">Latest:</span> <b>{money(last.amount)}</b> at {last.merchant}
              <span className="muted">→</span> <DecisionBadge decision={last.decision} />
              <span className="mono muted">in {last.latency_ms} ms</span>
            </div>
          )}
          <div className="pipe-flow">Then, off the hot path: WebSocket push to every open console, and an SES / SNS alert when risk crosses the alert threshold.</div>
        </div>
        <div className="mix">
          {Object.keys(DECISION_LABEL).map((k) => (
            <div key={k} className="mix-row">
              <DecisionBadge decision={k} />
              <div className="mix-track"><div className={`mix-fill mix-${k}`} style={{ width: `${((dec[k] || 0) / decMax) * 100}%` }} /></div>
              <span className="mono muted">{num(dec[k] || 0)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function CommandCenter({ stats, feed, onSelect, now }) {
  const arcs = useMemo(() => {
    const out = []
    for (const t of feed) {
      const f = t.flags?.find((x) => x.rule_id === 'impossible_travel')
      if (f && out.length < 8) out.push({ id: t.id, from: f.evidence.from, to: f.evidence.to, speed: f.evidence.speed_kmh })
    }
    return out
  }, [feed])
  const hot = feed.filter((t) => t.risk_level !== 'low').length

  return (
    <div className="page">
      <Kpis stats={stats} />
      <div className="cc-grid">
        <div className="card map-card">
          <div className="card-h">
            <h3>Global activity</h3>
            <span className="muted">{feed.length} recent · {hot} elevated · {arcs.length} impossible-travel arcs</span>
          </div>
          <WorldMap points={feed.slice(0, 220)} arcs={arcs} onSelect={onSelect} />
          <div className="legend map-legend">
            <span><i className="sw lv-low" />low</span><span><i className="sw lv-medium" />medium</span>
            <span><i className="sw lv-high" />high</span><span><i className="sw lv-critical" />critical</span>
            <span><i className="sw sw-arc" />impossible travel</span>
          </div>
        </div>
        <LiveFeed feed={feed} onSelect={onSelect} now={now} />
      </div>
      <Pipeline feed={feed} stats={stats} />
      <div className="cc-bottom">
        <Throughput series={stats?.series} thresholds={stats?.thresholds} />
        <RuleBreakdown rules={stats?.rules} />
      </div>
    </div>
  )
}
