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

export interface BollingerBands {
  upper: (number | null)[]
  middle: (number | null)[]
  lower: (number | null)[]
}

export interface RSIIndicators {
  rsi6: (number | null)[]
  rsi12: (number | null)[]
  rsi24: (number | null)[]
}

export interface CostChangeSeries {
  daily_change: (number | null)[]
  cumulative_positive: (number | null)[]
}

export interface MA5DeviationSeries {
  up: (number | null)[]
  down: (number | null)[]
}

export interface SmartMoneySeries {
  entity_change_3d: (number | null)[]
  smart_profit_3d: (number | null)[]
}

export interface FundFlowSeries {
  institution: (number | null)[]
  hot_money: (number | null)[]
  retail: (number | null)[]
  unit: 'shares' | 'amount'
}

export interface VolumeIndicators {
  predicted?: number | null
}

export interface KLineIndicators {
  ma: Record<string, (number | null)[]>
  bollinger: BollingerBands
  rsi: RSIIndicators
  average_cost: (number | null)[]
  cost_change: CostChangeSeries
  ma5_deviation: MA5DeviationSeries
  smart_money: SmartMoneySeries
  volume: VolumeIndicators
  fund_flow?: FundFlowSeries | null
}

export interface ChipDistribution {
  concentration_70: (number | null)[]
  concentration_90: (number | null)[]
  cost_70_low: (number | null)[]
  cost_70_high: (number | null)[]
  cost_90_low: (number | null)[]
  cost_90_high: (number | null)[]
}

export interface KLineResponse {
  code: string
  name: string
  kline: KLinePoint[]
  indicators: KLineIndicators
  chip_distribution: ChipDistribution
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
