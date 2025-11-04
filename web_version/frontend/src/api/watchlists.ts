import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import client from './client'

export interface WatchlistMeta {
  name: string
  type: 'custom' | 'system'
  symbol_count: number
  description?: string
  metadata?: Record<string, unknown>
}

export interface QuoteDetail {
  last_price?: number | null
  change_percent?: number | null
  industry?: string | null
  cost_change?: number | null
  ma5_deviation?: number | null
  next_day_limit_up_ma5_deviation?: number | null
  intraday_trend?: string | null
  day_trend?: string | null
  week_trend?: string | null
  month_trend?: string | null
  holders_change?: number | null
  capita_change?: number | null
  message?: string | null
  signal_level?: string | null
}

export interface WatchlistSymbol {
  code: string
  name: string
  lists: string[]
  tags: string[]
  notes?: string | null
  quote?: QuoteDetail | null
}

export const WATCHLISTS_QUERY_KEY = ['watchlists']

export function useWatchlists() {
  return useQuery({
    queryKey: WATCHLISTS_QUERY_KEY,
    queryFn: async () => {
      const response = await client.get<WatchlistMeta[]>('/watchlists')
      return response.data
    }
  })
}

export function useWatchlistSymbols(name: string | undefined, withQuotes = true) {
  return useQuery({
    queryKey: ['watchlists', name, 'symbols', { withQuotes }],
    queryFn: async () => {
      if (!name) return []
      const response = await client.get<WatchlistSymbol[]>(`/watchlists/${encodeURIComponent(name)}/symbols`, {
        params: { with_quotes: withQuotes }
      })
      return response.data
    },
    enabled: Boolean(name)
  })
}

export function useCreateWatchlist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { name: string; description?: string }) => {
      const response = await client.post('/watchlists', payload)
      return response.data as WatchlistMeta
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: WATCHLISTS_QUERY_KEY })
      queryClient.invalidateQueries({ queryKey: ['watchlists', variables.name, 'symbols'] })
    }
  })
}

export function useDeleteWatchlist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) => {
      await client.delete(`/watchlists/${encodeURIComponent(name)}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WATCHLISTS_QUERY_KEY })
    }
  })
}

export function useAddSymbol() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { list: string; code: string; name?: string }) => {
      await client.post(`/watchlists/${encodeURIComponent(payload.list)}/symbols`, {
        code: payload.code,
        name: payload.name
      })
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['watchlists', variables.list, 'symbols'] })
      queryClient.invalidateQueries({ queryKey: WATCHLISTS_QUERY_KEY })
    }
  })
}

export function useRemoveSymbol() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { list: string; code: string }) => {
      await client.delete(`/watchlists/${encodeURIComponent(payload.list)}/symbols/${encodeURIComponent(payload.code)}`)
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['watchlists', variables.list, 'symbols'] })
      queryClient.invalidateQueries({ queryKey: WATCHLISTS_QUERY_KEY })
    }
  })
}

export async function searchSymbols(keyword: string) {
  const response = await client.get<WatchlistSymbol[]>('/symbols/search', { params: { q: keyword } })
  return response.data
}

export async function fetchQuotes(codes: string[]) {
  if (!codes.length) return {}
  const response = await client.get<Record<string, QuoteDetail>>('/quotes', {
    params: { codes: codes.join(',') }
  })
  return response.data
}
