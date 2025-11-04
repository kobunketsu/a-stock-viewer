import { useQuery } from '@tanstack/react-query'
import client from './client'

export interface IntradayPoint {
  timestamp: string
  price: number
  volume: number
  rsi: number
  ma5: number
}

export function useIntraday(code: string, enabled = true) {
  return useQuery({
    queryKey: ['intraday', code],
    queryFn: async () => {
      const response = await client.get<IntradayPoint[]>(`/intraday/${code}`)
      return response.data
    },
    enabled,
    refetchInterval: 10_000
  })
}
