import { useEffect, useMemo, useState } from 'react'
import { Icon, Empty } from './ui'
import { api } from '../lib/api'
import { money, num, pretty } from '../lib/format'

const CAT_ICON = { velocity: 'zap', behavioral: 'trend', geo: 'plane', identity: 'cpu', merchant: 'inbox' }

function Toggle({ on, onChange }) {
  return <button role="switch" aria-checked={on} className={`toggle ${on ? 'on' : ''}`} onClick={() => onChange(!on)}><i /></button>
}

function RuleCard({ rule, draft, setDraft, live }) {
  const [src, setSrc] = useState(false)
  const eff = { enabled: draft?.enabled ?? rule.enabled, weight: draft?.weight ?? rule.weight, params: { ...rule.params, ...(draft?.params || {}) } }
  const dirty = !!draft
  const s = rule.stats
  const upd = (patch) => setDraft({ ...(draft || {}), ...patch })
  return (
    <div className={`card rule ${eff.enabled ? '' : 'off'} ${dirty ? 'dirty' : ''}`}>
      <div className="rule-h">
        <span className="rule-ic"><Icon name={CAT_ICON[rule.category] || 'shield'} size={16} /></span>
        <div className="rule-t">
          <b>{rule.name}</b>
          <span className="mono muted">{rule.id} · {rule.file}</span>
        </div>
        <Toggle on={eff.enabled} onChange={(v) => upd({ enabled: v })} />
      </div>
      <p className="rule-d">{rule.description}</p>
      <div className="rule-stats">
        <div><span>evaluated</span><b className="mono">{num(s.evaluations)}</b></div>
        <div><span>fired</span><b className="mono">{(s.hit_rate * 100).toFixed(1)}%</b></div>
        <div><span>avg cost</span><b className="mono">{s.avg_ms < 0.01 ? '<0.01' : s.avg_ms.toFixed(3)}ms</b></div>
        <div><span>precision</span><b className="mono">{live?.precision == null ? '—' : `${Math.round(live.precision * 100)}%`}</b></div>
      </div>
      {s.errors > 0 && <div className="rule-err"><Icon name="alert" size={13} />{s.errors} runtime errors isolated · {s.last_error}</div>}
      <label className="slider">
        <span>Weight <b className="mono">{eff.weight.toFixed(2)}</b></span>
        <input type="range" min="0" max="1.5" step="0.05" value={eff.weight} onChange={(e) => upd({ weight: +e.target.value })} />
      </label>
      <div className="params">
        {Object.entries(eff.params).map(([k, v]) => (
          <label key={k} title={rule.param_help?.[k]}>
            <span>{pretty(k)}</span>
            <input type="number" value={v} step="any" onChange={(e) => upd({ params: { ...(draft?.params || {}), [k]: +e.target.value } })} />
          </label>
        ))}
      </div>
      <div className="rule-f">
        <button className="link" onClick={() => setSrc(!src)}><Icon name="code" size={13} />{src ? 'Hide' : 'View'} source</button>
        {dirty && <span className="dirty-tag">edited</span>}
      </div>
      {src && <pre className="src">{rule.source}</pre>}
    </div>
  )
}

function Metrics({ m }) {
  const pct = (x) => (x == null ? '—' : `${Math.round(x * 100)}%`)
  return <span className="mono">P {pct(m.precision)} · R {pct(m.recall)} <span className="muted">(tp {m.tp} fp {m.fp} fn {m.fn})</span></span>
}

export default function RulesLab({ tick, stats, toast }) {
  const [data, setData] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [th, setTh] = useState(null)
  const [bt, setBt] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = () => api.rules().then((d) => { setData(d); setTh((cur) => cur || d.thresholds) })
  useEffect(() => { load() }, [tick.rules])
  useEffect(() => { const h = setInterval(load, 4000); return () => clearInterval(h) }, [])

  const nDirty = Object.keys(drafts).length + (th && data && (th.flag !== data.thresholds.flag || th.alert !== data.thresholds.alert) ? 1 : 0)
  const thDirty = th && data && (th.flag !== data.thresholds.flag || th.alert !== data.thresholds.alert)

  const runBacktest = async () => {
    setBusy(true)
    try { setBt(await api.backtest({ limit: 800, rules: drafts, thresholds: th })) }
    catch (e) { toast({ tone: 'crit', title: 'Backtest failed', body: e.message }) }
    finally { setBusy(false) }
  }
  const apply = async () => {
    setBusy(true)
    try {
      for (const [id, patch] of Object.entries(drafts)) await api.patchRule(id, patch)
      if (thDirty) await api.thresholds(th)
      setDrafts({}); setBt(null); await load()
      toast({ tone: 'good', title: 'Configuration live', body: 'New settings apply to the very next transaction.' })
    } catch (e) { toast({ tone: 'crit', title: 'Apply failed', body: e.message }) }
    finally { setBusy(false) }
  }

  const rules = data?.rules || []
  const errors = Object.entries(data?.load_errors || {})
  const zones = useMemo(() => th && [
    { w: th.flag, c: 'var(--low)' }, { w: (th.alert - th.flag) / 2, c: 'var(--medium)' },
    { w: (th.alert - th.flag) / 2, c: 'var(--high)' }, { w: 100 - th.alert, c: 'var(--critical)' }], [th])

  if (!data) return <div className="page"><div className="skeleton" /></div>
  return (
    <div className="page lab">
      <div className="lab-top">
        <div className="card">
          <div className="card-h"><h3>Risk thresholds</h3><span className="muted">score 0–100 from noisy-OR fusion</span></div>
          <div className="zones">{zones.map((z, i) => <i key={i} style={{ flex: z.w, background: z.c }} />)}</div>
          <label className="slider"><span>Flag for review at <b className="mono">{th.flag}</b></span>
            <input type="range" min="5" max="95" value={th.flag} onChange={(e) => setTh({ ...th, flag: Math.min(+e.target.value, th.alert - 1) })} /></label>
          <label className="slider"><span>Send SES / SNS alert at <b className="mono">{th.alert}</b></span>
            <input type="range" min="10" max="100" value={th.alert} onChange={(e) => setTh({ ...th, alert: Math.max(+e.target.value, th.flag + 1) })} /></label>
        </div>
        <div className="card hotplug">
          <div className="card-h"><h3><Icon name="code" size={15} /> Hot-plug rules</h3><span className="mono muted">engine v{data.version}</span></div>
          <p>Every rule is a plugin. Drop a <code>.py</code> file that subclasses <code>Rule</code> into the rules folder and the engine loads it <b>in about a second, with no restart and no change to the core</b>. A broken file is quarantined and shown here; it never stops scoring.</p>
          <code className="path">{data.rules_dir}</code>
          <pre className="src tiny">{`class MyRule(Rule):
    id = "my_rule"; name = "My Rule"
    def evaluate(self, txn, ctx):
        if txn.amount > 9000:
            return RuleResult(0.8, "Very large ticket")`}</pre>
          {errors.map(([f, e]) => <div key={f} className="rule-err"><Icon name="alert" size={13} /><b>{f}</b> quarantined: {e}</div>)}
          <button className="btn sm" onClick={async () => { const r = await api.reloadRules(); toast({ tone: 'info', title: 'Rules rescanned', body: `${r.active.length} active` }); load() }}><Icon name="refresh" size={13} />Rescan now</button>
        </div>
      </div>

      <div className={`draftbar ${nDirty ? 'show' : ''}`}>
        <span><b>{nDirty}</b> unsaved change{nDirty === 1 ? '' : 's'}. See their effect on real traffic before you ship them.</span>
        <button className="btn" disabled={busy} onClick={runBacktest}><Icon name="flask" size={14} />Backtest</button>
        <button className="btn primary" disabled={busy} onClick={apply}><Icon name="check" size={14} />Apply live</button>
        <button className="btn ghost" disabled={busy} onClick={() => { setDrafts({}); setTh(data.thresholds); setBt(null) }}>Discard</button>
      </div>

      {bt && (
        <div className="card backtest">
          <div className="card-h"><h3><Icon name="flask" size={15} /> What-if backtest</h3><span className="muted">replayed {bt.evaluated} recent transactions in {bt.duration_ms} ms · no production data touched</span>
            <button className="icon-btn" onClick={() => setBt(null)}><Icon name="x" size={14} /></button></div>
          <div className="bt-grid">
            <div><span>Flagged now</span><b className="mono">{bt.flagged_before}</b></div>
            <div><span>Flagged with changes</span><b className="mono">{bt.flagged_after} <em className={bt.flagged_after > bt.flagged_before ? 'up' : 'down'}>{bt.flagged_after - bt.flagged_before >= 0 ? '+' : ''}{bt.flagged_after - bt.flagged_before}</em></b></div>
            <div><span>Alerts with changes</span><b className="mono">{bt.alerts_after}</b></div>
            <div><span>Labeled quality now</span><Metrics m={bt.labeled.before} /></div>
            <div><span>Labeled quality after</span><Metrics m={bt.labeled.after} /></div>
          </div>
          <div className="two">
            <div><h4>Newly flagged ({bt.newly_count})</h4>{bt.newly_flagged.slice(0, 8).map((t) => <div key={t.id} className="mini-row"><span>{t.user_name}</span><span>{t.merchant}</span><span className="mono">{money(t.amount)}</span><span className="mono">{Math.round(t.before)}→<b>{Math.round(t.after)}</b></span></div>)}{!bt.newly_count && <p className="muted">None</p>}</div>
            <div><h4>No longer flagged ({bt.dropped_count})</h4>{bt.no_longer_flagged.slice(0, 8).map((t) => <div key={t.id} className="mini-row"><span>{t.user_name}</span><span>{t.merchant}</span><span className="mono">{money(t.amount)}</span><span className="mono">{Math.round(t.before)}→<b>{Math.round(t.after)}</b></span></div>)}{!bt.dropped_count && <p className="muted">None</p>}</div>
          </div>
        </div>
      )}

      {rules.length === 0 && <Empty icon="alert" title="No rules loaded">Add a rule file to the rules folder.</Empty>}
      <div className="rules-grid">
        {rules.map((r) => (
          <RuleCard key={r.id} rule={r} live={stats?.rules?.[r.id]} draft={drafts[r.id]}
            setDraft={(d) => setDrafts({ ...drafts, [r.id]: d })} />
        ))}
      </div>
    </div>
  )
}
