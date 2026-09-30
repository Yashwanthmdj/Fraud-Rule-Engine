import { useEffect, useState } from 'react'
import { Icon, Empty } from './ui'
import { api } from '../lib/api'
import { dateTime } from '../lib/format'

export default function Alerts({ tick, onSelect }) {
  const [rows, setRows] = useState([])
  const [cfg, setCfg] = useState(null)
  useEffect(() => { api.notifications().then(setRows) }, [tick.alert])
  useEffect(() => { api.settings().then((s) => setCfg(s.notifier)) }, [])
  const live = cfg?.mode === 'live'

  return (
    <div className="page alerts">
      <div className="lab-top">
        <div className={`card notifier ${live ? 'live' : ''}`}>
          <div className="card-h"><h3><Icon name="bell" size={15} /> AWS notifier</h3>
            <span className={`pill ${live ? 'st-cleared' : 'st-flagged'}`}>{live ? 'LIVE' : 'DRY-RUN'}</span></div>
          {cfg && (
            <div className="facts">
              <div><span>Channels</span><b>{cfg.channels.map((c) => c.toUpperCase()).join(' + ')}</b></div>
              <div><span>Region</span><b className="mono">{cfg.region}</b></div>
              <div><span>SES from → to</span><b className="mono">{cfg.ses_from || '—'} → {cfg.ses_to.join(', ') || '—'}</b></div>
              <div><span>SNS topic</span><b className="mono">{cfg.sns_topic || '—'}</b></div>
              <div><span>Storm guard</span><b>1 alert / cardholder / {cfg.cooldown_seconds}s</b></div>
            </div>
          )}
          <p className="muted">{live ? `Connected (${cfg.detail}). Critical transactions email your reviewers in real time.` : `Alerts are fully rendered and logged but not sent (${cfg?.detail}).`}</p>
        </div>
        <div className="card">
          <div className="card-h"><h3>Go live in 30 seconds</h3></div>
          <pre className="src tiny">{`export AWS_REGION=us-east-1          # + aws credentials
export AEGIS_SES_FROM=alerts@yourdomain.com  # SES-verified
export AEGIS_SES_TO=reviewer@yourdomain.com
export AEGIS_SNS_TOPIC_ARN=arn:aws:sns:us-east-1:123:aegis  # optional
./run.sh`}</pre>
          <p className="muted">Alerts fire when risk crosses the alert threshold (tune it in Rules Lab). Each email includes the full rule-by-rule explanation and a deep link back to this console.</p>
        </div>
      </div>
      <div className="card">
        <div className="card-h"><h3>Dispatch log</h3><span className="muted">{rows.length} records</span></div>
        {rows.length === 0 && <Empty icon="bell" title="No alerts yet">Launch an Account Takeover in the Attack Lab.</Empty>}
        <div className="table">
          {rows.map((n) => (
            <button key={n.id} className="tr" onClick={() => onSelect(n.txn_id)}>
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
