import { useEffect, useState } from 'react'
import { Icon, Empty } from './ui'
import { api } from '../lib/api'
import { dateTime } from '../lib/format'

export default function Alerts({ tick, onSelect, toast }) {
  const [rows, setRows] = useState([])
  const [cfg, setCfg] = useState(null)
  const [busy, setBusy] = useState('')
  useEffect(() => { api.notifications().then(setRows).catch(() => {}) }, [tick.alert])
  useEffect(() => { api.settings().then((s) => setCfg(s.notifier)).catch(() => {}) }, [])
  const live = cfg?.mode === 'live'

  const run = async (key, fn) => {
    setBusy(key)
    try { await fn() } catch (e) { toast({ tone: 'crit', title: 'Failed', body: e.message }) } finally { setBusy('') }
  }
  const recheck = () => run('check', async () => {
    const c = await api.recheckAlerts()
    setCfg(c)
    toast({ tone: c.mode === 'live' ? 'good' : 'info', title: `Notifier ${c.mode === 'live' ? 'LIVE' : 'still in dry-run'}`, body: c.detail })
  })
  const test = () => run('test', async () => {
    const r = await api.testAlert()
    const failed = r.filter((n) => n.status === 'failed')
    toast({ tone: failed.length ? 'crit' : 'good', title: `Test alert: ${r.map((n) => `${n.channel.toUpperCase()} ${n.status}`).join(' · ')}`,
      body: failed[0]?.error || (live ? `Check ${cfg.ses_to.join(', ') || 'your inbox'} (and the spam folder)` : 'Dry-run: rendered and logged, not sent') })
    api.notifications().then(setRows)
  })

  return (
    <div className="page alerts">
      <div className="lab-top">
        <div className={`card notifier ${live ? 'live' : ''}`}>
          <div className="card-h"><h3><Icon name="bell" size={15} /> AWS notifier</h3>
            <span className={`pill ${live ? 'st-cleared' : 'st-flagged'}`}>{live ? 'LIVE' : 'DRY-RUN'}</span>
            <span className="muted">{cfg?.detail}</span></div>
          {cfg && (
            <div className="facts">
              <div><span>Channels</span><b>{cfg.channels.map((c) => c.toUpperCase()).join(' + ')}</b></div>
              <div><span>Region</span><b className="mono">{cfg.region}</b></div>
              <div><span>Report recipient</span><b className="mono">{cfg.ses_to.join(', ') || '—'}</b></div>
              <div><span>Storm guard</span><b>1 alert / cardholder / {cfg.cooldown_seconds}s · max {cfg.max_per_hour}/h</b></div>
            </div>
          )}
          <div className="checks">
            {(cfg?.checks || []).map((c, i) => (
              <div key={i} className="check">
                <Icon name={c.ok ? 'check' : 'x'} size={14} className={c.ok ? 'ok' : 'bad'} />
                <b>{c.name}</b><span>{c.detail}</span>
              </div>
            ))}
          </div>
          <div className="row gap">
            <button className="btn primary" disabled={!!busy} onClick={test}><Icon name="send" size={14} />{busy === 'test' ? 'Sending…' : 'Send test alert'}</button>
            <button className="btn" disabled={!!busy} onClick={recheck}><Icon name="refresh" size={14} />{busy === 'check' ? 'Checking…' : 'Re-check AWS'}</button>
          </div>
        </div>
        <div className="card">
          <div className="card-h"><h3>Why an email might not arrive</h3></div>
          <p className="muted">Every red check in the notifier panel is a reason. The usual ones:</p>
          <ul className="muted">
            <li><b>No AWS credentials</b> → AEGIS stays in dry-run: alerts are rendered and logged, never sent.</li>
            <li><b>SES sandbox</b> → both the sender and the recipient must be verified identities. Click the link AWS emails you, then <i>Re-check AWS</i>.</li>
            <li><b>SNS email</b> → the subscription must be confirmed from the inbox before anything is delivered.</li>
            <li><b>Spam folder</b> → mail sent through SES from a gmail.com address is often filtered. Mark it “Not spam” once.</li>
          </ul>
          <p className="muted">Alerts fire when risk crosses the alert threshold (tune it in Rules Lab). Each email carries the decision, the rule-by-rule explanation and a link back to this console.</p>
        </div>
      </div>
      <div className="card">
        <div className="card-h"><h3>Dispatch log</h3><span className="muted">{rows.length} records</span></div>
        {rows.length === 0 && <Empty icon="bell" title="No alerts yet">Launch an Account Takeover in the Attack Lab, or send a test alert.</Empty>}
        <div className="table">
          {rows.map((n) => (
            <button key={n.id} className="tr" onClick={() => !n.txn_id.startsWith('TEST-') && onSelect(n.txn_id)}>
              <span className="mono muted">{dateTime(n.ts)}</span>
              <span className="mono">{n.channel.toUpperCase()}</span>
              <span className={`pill ns-${n.status}`}>{n.status}</span>
              <span className="tr-subj">{n.subject}{n.error && <em className="muted"> · {n.error}</em>}</span>
              <span className="mono muted">{n.message_id ? n.message_id.slice(0, 14) + '…' : n.mode}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
