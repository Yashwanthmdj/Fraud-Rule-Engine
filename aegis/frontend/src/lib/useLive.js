import { useEffect, useRef, useState } from 'react'
import { API_BASE } from './api'

/** Resilient WebSocket subscription with auto-reconnect and keepalive. */
export function useLive(onMessage) {
  const [status, setStatus] = useState('connecting')
  const handler = useRef(onMessage)
  handler.current = onMessage

  useEffect(() => {
    let ws, retry, ping
    let alive = true
    const origin = API_BASE ? new URL(API_BASE) : location
    const url = `${origin.protocol === 'https:' ? 'wss' : 'ws'}://${origin.host}/ws`
    const connect = () => {
      ws = new WebSocket(url)
      ws.onopen = () => {
        setStatus('live')
        ping = setInterval(() => ws.readyState === 1 && ws.send('ping'), 20000)
      }
      ws.onmessage = (e) => {
        try { handler.current(JSON.parse(e.data)) } catch (err) { console.error(err) }
      }
      ws.onclose = () => {
        clearInterval(ping)
        if (!alive) return
        setStatus('offline')
        retry = setTimeout(connect, 1500)
      }
    }
    connect()
    return () => { alive = false; clearTimeout(retry); clearInterval(ping); ws && ws.close() }
  }, [])

  return status
}
