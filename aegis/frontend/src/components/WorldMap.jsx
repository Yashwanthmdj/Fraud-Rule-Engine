import { geoEqualEarth, geoOrthographic, geoPath, geoGraticule10, geoInterpolate } from 'd3-geo'
import { feature } from 'topojson-client'
import world from 'world-atlas/countries-110m.json'
import { memo, useMemo, useState } from 'react'
import { money, flag } from '../lib/format'

const land = feature(world, world.objects.countries)
const W = 960, H = 470

function makeProjection(center) {
  // Evidence view: a globe turned to face the hop, so even polar routes read as one clean arc.
  if (center) return geoOrthographic().rotate([-center[0], -center[1]]).fitExtent([[8, 8], [W - 8, H - 8]], { type: 'Sphere' })
  return geoEqualEarth().fitExtent([[8, 8], [W - 8, H - 8]], { type: 'Sphere' })
}

const arcCenter = (a) => geoInterpolate([a.from.lon, a.from.lat], [a.to.lon, a.to.lat])(0.5)

const Base = memo(function Base({ path }) {
  return (
    <g>
      <path d={path({ type: 'Sphere' })} className="map-sphere" />
      <path d={path(geoGraticule10())} className="map-grat" />
      {land.features.map((f, i) => <path key={i} d={path(f)} className="map-land" />)}
    </g>
  )
})

/** Live world view. `points` are transactions, `arcs` are impossible-travel hops. */
export default function WorldMap({ points = [], arcs = [], onSelect, compact = false }) {
  const center = compact && arcs.length ? arcCenter(arcs[0]) : null
  const projection = useMemo(() => makeProjection(center), [center?.[0], center?.[1]])
  const path = useMemo(() => geoPath(projection), [projection])
  const [hover, setHover] = useState(null)
  const now = Date.now()

  return (
    <div className={`map ${compact ? 'compact' : ''}`}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label="World map of live transactions">
        <Base path={path} />
        {arcs.map((a) => {
          const interp = geoInterpolate([a.from.lon, a.from.lat], [a.to.lon, a.to.lat])
          const line = { type: 'LineString', coordinates: Array.from({ length: 33 }, (_, i) => interp(i / 32)) }
          const p1 = projection([a.from.lon, a.from.lat]), p2 = projection([a.to.lon, a.to.lat])
          return (
            <g key={a.id} className="arc" onClick={() => onSelect?.(a.id)}>
              <path d={path(line)} className="arc-glow" />
              <path d={path(line)} className="arc-line" />
              <circle cx={p1[0]} cy={p1[1]} r={4} className="arc-from" />
              <circle cx={p2[0]} cy={p2[1]} r={5} className="arc-to" />
              {(compact || a.label) && (
                <text x={p2[0]} y={p2[1] - 10} className="arc-label" textAnchor="middle">
                  {a.label || `${Math.round(a.speed).toLocaleString()} km/h`}
                </text>
              )}
            </g>
          )
        })}
        {points.map((t) => {
          if (t.lat == null) return null
          const [x, y] = projection([t.lon, t.lat])
          const age = (now - new Date(t.ts).getTime()) / 1000
          const hot = t.risk_level === 'critical' || t.risk_level === 'high'
          const opacity = hot ? Math.max(0.35, 1 - age / 900) : Math.max(0.12, 1 - age / 120)
          return (
            <g key={t.id} transform={`translate(${x},${y})`} style={{ opacity }}
              onMouseEnter={() => setHover({ t, x, y })} onMouseLeave={() => setHover(null)}
              onClick={() => onSelect?.(t.id)} className={`pt lv-${t.risk_level}`}>
              {hot && age < 60 && <circle r={4} className="pt-pulse" />}
              <circle r={t.risk_level === 'low' ? 2.3 : 4} className="pt-core" />
            </g>
          )
        })}
      </svg>
      {hover && (
        <div className="map-tip" style={{ left: `${(hover.x / W) * 100}%`, top: `${(hover.y / H) * 100}%` }}>
          <b>{money(hover.t.amount)}</b> · {hover.t.merchant}
          <span>{flag(hover.t.country)} {hover.t.city} · risk {Math.round(hover.t.risk_score)}</span>
        </div>
      )}
    </div>
  )
}
