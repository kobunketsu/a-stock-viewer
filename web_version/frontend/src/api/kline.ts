import { useQuery } from '@tanstack/react-query'
import client from './client'

export interface KLinePoint {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface KLineResponse {
  code: string
  name: string
  kline: KLinePoint[]
  indicators: Record<string, number[]>
  chip_distribution: {
    concentration_70: number[]
    concentration_90: number[]
    [key: string]: number[]
  }
}

export function useKLine(code: string, enabled = true) {
  return useQuery({
    queryKey: ['kline', code],
    queryFn: async () => {
      const response = await client.get<KLineResponse>(`/kline/${code}`)
      return response.data
    },
    enabled
  })
}
