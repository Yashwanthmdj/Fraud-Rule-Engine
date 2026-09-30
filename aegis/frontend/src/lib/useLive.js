import { useEffect, useRef, useState } from 'react'

/** Resilient WebSocket subscription with auto-reconnect and keepalive. */
export function useLive(onMessage) {
  const [status, setStatus] = useState('connecting')
  const handler = useRef(onMessage)
  handler.current = onMessage

  useEffect(() => {
    let ws, retry, ping
    let alive = true
    const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`
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
