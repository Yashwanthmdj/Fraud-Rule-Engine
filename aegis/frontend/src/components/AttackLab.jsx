import { useEffect, useState } from 'react'
import { Icon, LevelBadge } from './ui'
import { api } from '../lib/api'
import { money, clock, pretty } from '../lib/format'

const CITIES = {
  'New York': ['US', 40.71, -74.01], London: ['GB', 51.51, -0.13], Hyderabad: ['IN', 17.39, 78.49],
  Tokyo: ['JP', 35.68, 139.69], Lagos: ['NG', 6.52, 3.38], 'Sao Paulo': ['BR', -23.55, -46.63],
  Sydney: ['AU', -33.87, 151.21], Dubai: ['AE', 25.2, 55.27], Moscow: ['RU', 55.76, 37.62],
}
const CATS = ['grocery', 'restaurants', 'electronics', 'travel', 'online_retail', 'jewelry', 'gift_cards', 'crypto', 'wire_transfer', 'gambling']

function ManualTxn({ toast, defaultUser }) {
  const [f, setF] = useState({ user_id: '', amount: 2500, merchant: 'Manual Test Merchant', category: 'electronics', city: 'Tokyo', device_id: 'dev_manual01', channel: 'card_present' })
  const [res, setRes] = useState(null)
  useEffect(() => { if (defaultUser && !f.user_id) setF((x) => ({ ...x, user_id: defaultUser })) }, [defaultUser])
  const [cc, lat, lon] = CITIES[f.city]
  const body = { ...f, amount: +f.amount, country: cc, lat, lon }
  const send = async () => {
    try { setRes(await api.ingest(body)) } catch (e) { toast({ tone: 'crit', title: 'Rejected', body: e.message }) }
  }
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  return (
    <div className="card manual">
      <div className="card-h"><h3><Icon name="send" size={15} /> Ingest API console</h3><span className="muted">POST /api/transactions: exactly what a payment switch would call</span></div>
      <div className="form">
        <label><span>Cardholder id</span><input value={f.user_id} onChange={set('user_id')} className="mono" /></label>
        <label><span>Amount (USD)</span><input type="number" value={f.amount} onChange={set('amount')} className="mono" /></label>
        <label><span>Merchant</span><input value={f.merchant} onChange={set('merchant')} /></label>
        <label><span>Category</span><select value={f.category} onChange={set('category')}>{CATS.map((c) => <option key={c} value={c}>{pretty(c)}</option>)}</select></label>
        <label><span>City</span><select value={f.city} onChange={set('city')}>{Object.keys(CITIES).map((c) => <option key={c}>{c}</option>)}</select></label>
        <label><span>Device id</span><input value={f.device_id} onChange={set('device_id')} className="mono" /></label>
        <label><span>Channel</span><select value={f.channel} onChange={set('channel')}><option value="card_present">card present</option><option value="online">online</option></select></label>
        <button className="btn primary" onClick={send}><Icon name="send" size={14} />Score it</button>
      </div>
      <pre className="src tiny">{`curl -X POST ${location.origin}/api/transactions \\
  -H 'Content-Type: application/json' \\
  -d '${JSON.stringify(body)}'`}</pre>
      {res && (
        <div className="manual-res">
          <LevelBadge level={res.evaluation.level} score={res.evaluation.score} />
          <span className="mono muted">{res.evaluation.latency_ms} ms · {res.evaluation.rules_run} rules</span>
          {res.evaluation.alert && <span className="pill st-fraud">alert dispatched</span>}
          <ul>{res.evaluation.hits.map((h) => <li key={h.rule_id}><b>{h.rule_name}</b> +{Math.round(h.contribution * 100)}: {h.reason}</li>)}
            {!res.evaluation.hits.length && <li className="muted">No rule fired.</li>}</ul>
        </div>
      )}
    </div>
  )
}

export default function AttackLab({ stats, feed, toast, onSelect, tick }) {
  const [sim, setSim] = useState(null)
  const [runs, setRuns] = useState([])
  useEffect(() => { api.simulator().then((s) => { setSim((cur) => cur || s); setRuns(s.log) }) }, [tick.txn])

  const setSimState = async (p) => setSim({ ...sim, ...(await api.patchSim(p)) })
  const launch = async (name) => {
    const r = await api.launch(name)
    toast({ tone: 'crit', title: `Attack launched: ${sim.scenarios[name].title}`, body: r.victim_name ? `Victim ${r.victim_name} (${r.home})` : `${r.victims.length} victims` })
    setTimeout(() => api.simulator().then((s) => setRuns(s.log)), 2500)
  }
  if (!sim) return <div className="page"><div className="skeleton" /></div>
  const a = stats?.attacks || {}

  return (
    <div className="page attack">
      <div className="lab-top">
        <div className="card">
          <div className="card-h"><h3>Traffic simulator</h3><span className="muted">{sim.users} synthetic cardholders with 45 days of history</span></div>
          <div className="sim-row">
            <button className={`btn ${sim.running ? '' : 'primary'}`} onClick={() => setSimState({ running: !sim.running })}>
              <Icon name={sim.running ? 'pause' : 'play'} size={14} />{sim.running ? 'Pause stream' : 'Start stream'}
            </button>
            <label className="slider grow"><span>Rate <b className="mono">{sim.rate.toFixed(1)}</b> txn/s</span>
              <input type="range" min="0.2" max="12" step="0.2" value={sim.rate} onChange={(e) => setSim({ ...sim, rate: +e.target.value })} onMouseUp={(e) => setSimState({ rate: +e.target.value })} onTouchEnd={(e) => setSimState({ rate: +e.target.value })} /></label>
          </div>
        </div>
        <div className="card scoreboard">
          <div><span>Attacks launched</span><b className="mono">{a.runs ?? 0}</b></div>
          <div><span>Detected</span><b className="mono good">{a.caught ?? 0}</b></div>
          <div><span>Txns to detect</span><b className="mono">{a.avg_txns_to_detect ?? '—'}</b></div>
          <div><span>Fraud $ intercepted</span><b className="mono">{money(a.blocked_amount || 0, 0)}</b></div>
        </div>
      </div>

      <div className="scen-grid">
        {Object.entries(sim.scenarios).map(([key, s]) => (
          <div key={key} className={`card scen ${key === 'fraud_storm' ? 'storm' : ''}`}>
            <div className="scen-ic"><Icon name={s.icon} size={20} /></div>
            <b>{s.title}</b>
            <p>{s.story}</p>
            <button className="btn crit" onClick={() => launch(key)}><Icon name="zap" size={14} />Launch</button>
          </div>
        ))}
      </div>

      <div className="two">
        <div className="card">
          <div className="card-h"><h3>Attack log</h3><span className="muted">ground truth vs. what the engine saw</span></div>
          {runs.length === 0 && <p className="muted">No attacks yet. Launch one above and watch the Command Center.</p>}
          {runs.slice(0, 12).map((r) => (
            <button key={r.run} className="run-row" onClick={() => onSelect(r.top_id)}>
              <span className="mono muted">{clock(r.started)}</span>
              <b>{pretty(r.scenario)}</b>
              <span>{r.victim_name} <span className="muted">· {r.n} txn{r.n > 1 ? 's' : ''}</span></span>
              <LevelBadge level={r.level} score={r.max_score} />
              <span className={`mono ${r.caught_at ? 'good' : 'muted'}`} title={r.caught_at ? `flagged on attack txn #${r.caught_at}` : ''}>{r.caught_at ? 'CAUGHT' : 'missed'}</span>
            </button>
          ))}
        </div>
        <ManualTxn toast={toast} defaultUser={feed.find((t) => t.source === 'simulator')?.user_id} />
      </div>
    </div>
  )
}
