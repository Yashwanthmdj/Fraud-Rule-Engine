import { LEVEL_LABEL, STATUS_LABEL, DECISION_LABEL, TIER_LABEL } from '../lib/format'

const P = {
  shield: 'M12 2 4 5v6c0 5.5 3.4 9.7 8 11 4.6-1.3 8-5.5 8-11V5z',
  radar: 'M12 12 19 5M21 12a9 9 0 1 1-9-9M17 12a5 5 0 1 1-5-5',
  inbox: 'M22 12h-6l-2 3h-4l-2-3H2M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z',
  sliders: 'M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6',
  zap: 'M13 2 3 14h9l-1 8 10-12h-9z',
  bell: 'M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0',
  plane: 'M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z',
  trend: 'M22 7 13.5 15.5 8.5 10.5 2 17M16 7h6v6',
  skull: 'M9 22v-3M15 22v-3M12 2a8 8 0 0 0-8 8c0 3 1.5 5 3 6v3h10v-3c1.5-1 3-3 3-6a8 8 0 0 0-8-8zM9 11h.01M15 11h.01',
  storm: 'M19 16.9A5 5 0 0 0 18 7h-1.3A8 8 0 1 0 4 15.3M13 11l-4 6h6l-4 6',
  play: 'M6 4l14 8-14 8z',
  pause: 'M6 4h4v16H6zM14 4h4v16h-4z',
  check: 'M20 6 9 17l-5-5',
  x: 'M18 6 6 18M6 6l12 12',
  alert: 'M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3',
  code: 'M16 18l6-6-6-6M8 6l-6 6 6 6',
  mail: 'M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM22 6l-10 7L2 6',
  eye: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  undo: 'M3 7v6h6M21 17a9 9 0 0 0-15-6.7L3 13',
  flask: 'M9 3h6M10 3v6L4 20a1 1 0 0 0 .9 1.5h14.2A1 1 0 0 0 20 20L14 9V3',
  refresh: 'M23 4v6h-6M1 20v-6h6M3.5 9a9 9 0 0 1 14.8-3.4L23 10M1 14l4.7 4.4A9 9 0 0 0 20.5 15',
  volume: 'M11 5 6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14',
  mute: 'M11 5 6 9H2v6h4l5 4zM23 9l-6 6M17 9l6 6',
  send: 'M22 2 11 13M22 2l-7 20-4-9-9-4z',
  keyboard: 'M2 6h20v12H2zM6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10',
  cpu: 'M4 4h16v16H4zM9 9h6v6H9zM9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3',
  user: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
  brain: 'M12 5a3 3 0 1 0-5.9.8A4 4 0 0 0 4 13a4 4 0 0 0 3 6.5A3 3 0 0 0 12 19zM12 5a3 3 0 1 1 5.9.8A4 4 0 0 1 20 13a4 4 0 0 1-3 6.5A3 3 0 0 1 12 19z',
}

export function Icon({ name, size = 16, stroke = 2, className = '', style }) {
  return (
    <svg className={`icon ${className}`} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={P[name] || P.shield} />
    </svg>
  )
}

export function LevelBadge({ level, score }) {
  return (
    <span className={`badge lv-${level}`}>
      <span className="dot" />
      {LEVEL_LABEL[level] || level}
      {score != null && <b className="mono">{Math.round(score)}</b>}
    </span>
  )
}

export function StatusPill({ status }) {
  return <span className={`pill st-${status}`}>{STATUS_LABEL[status] || status}</span>
}

export function DecisionBadge({ decision }) {
  if (!decision) return null
  return <span className={`dec dec-${decision}`}>{DECISION_LABEL[decision] || decision}</span>
}

export function TierPill({ tier }) {
  if (!tier) return null
  return <span className={`pill tier-${tier}`}>{TIER_LABEL[tier] || tier}</span>
}

export function RiskRing({ score, level, size = 88 }) {
  const r = size / 2 - 7
  const c = 2 * Math.PI * r
  return (
    <div className={`ring lv-${level}`} style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} className="ring-track" />
        <circle cx={size / 2} cy={size / 2} r={r} className="ring-val"
          strokeDasharray={`${(c * Math.min(100, score)) / 100} ${c}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      </svg>
      <div className="ring-label">
        <b className="mono">{Math.round(score)}</b>
        <span>risk</span>
      </div>
    </div>
  )
}

export function Empty({ icon = 'check', title, children }) {
  return (
    <div className="empty">
      <Icon name={icon} size={22} />
      <b>{title}</b>
      {children && <span>{children}</span>}
    </div>
  )
}
