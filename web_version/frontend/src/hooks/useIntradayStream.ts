import { useEffect, useRef, useState } from 'react'
import type { IntradayPoint } from '../api/intraday'

export type StreamStatus = 'idle' | 'connecting' | 'connected' | 'error'

interface StreamResult {
  data: IntradayPoint[] | null
  status: StreamStatus
  error: string | null
}

const WS_BASE = typeof window !== 'undefined'
  ? (import.meta.env.VITE_WS_BASE as string | undefined) ?? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.hostname}:8000`
  : 'ws://localhost:8000'

export function useIntradayStream(code: string): StreamResult {
  const [data, setData] = useState<IntradayPoint[] | null>(null)
  const [status, setStatus] = useState<StreamStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<number | null>(null)

  useEffect(() => {
    let active = true
    if (!code) {
      cleanup()
      setStatus('idle')
      setData(null)
      return
    }

    connect()

    return () => {
      active = false
      cleanup()
    }

    function connect() {
      cleanup()
      setStatus('connecting')
      setError(null)

      try {
        const ws = new WebSocket(`${WS_BASE}/ws/intraday/${code}`)
        wsRef.current = ws

        ws.onopen = () => {
          setStatus('connected')
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('init')
          }
        }

        ws.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data) as { data: IntradayPoint[] }
            setData(payload.data)
            setStatus('connected')
            if (ws.readyState === WebSocket.OPEN) {
              ws.send('ack')
            }
          } catch (parseError) {
            console.error('Failed to parse intraday payload', parseError)
          }
        }

        ws.onerror = (evt) => {
          console.error('WebSocket error', evt)
          setStatus('error')
          setError('WebSocket error')
        }

        ws.onclose = () => {
          if (!active) return
          setStatus('error')
          setError('连接已关闭')
          scheduleReconnect()
        }
      } catch (err) {
        console.error('WebSocket connection failed', err)
        setStatus('error')
        setError('WebSocket connection failed')
        scheduleReconnect()
      }
    }

    function cleanup() {
      if (reconnectTimer.current) {
        window.clearTimeout(reconnectTimer.current)
        reconnectTimer.current = null
      }
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }

    function scheduleReconnect() {
      if (!active) return
      if (reconnectTimer.current) return
      reconnectTimer.current = window.setTimeout(() => {
        reconnectTimer.current = null
        connect()
      }, 15000)
    }
  }, [code])

  return { data, status, error }
}
