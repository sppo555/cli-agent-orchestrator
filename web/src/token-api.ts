import { WorkerTokenUsagePage, WorkerTokenUsageRecord, WorkerTokenUsageSummary } from './token-types'

export interface TokenUsageQuery {
  provider?: string[]
  agent?: string[]
  model?: string[]
  effort?: string[]
  from?: string
  to?: string
  limit?: number
  cursor?: string
  snapshotAt?: string
}

async function fetchTokenJSON<T>(url: string, timeoutMs = 10000): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, { signal: controller.signal })
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
    return response.json()
  } finally {
    clearTimeout(timeout)
  }
}

export const tokenApi = {
  listTokenUsagePage: (filters: TokenUsageQuery = {}) => {
    const params = new URLSearchParams()
    for (const field of ['provider', 'agent', 'model', 'effort'] as const) {
      for (const value of filters[field] || []) params.append(field, value)
    }
    if (filters.from) params.set('from', filters.from)
    if (filters.to) params.set('to', filters.to)
    params.set('limit', String(filters.limit ?? 100))
    if (filters.cursor) params.set('cursor', filters.cursor)
    if (filters.snapshotAt) params.set('snapshot_at', filters.snapshotAt)
    return fetchTokenJSON<WorkerTokenUsagePage>(`/token-usage/page?${params.toString()}`)
  },
  summarizeTokenUsage: (filters: Omit<TokenUsageQuery, 'limit' | 'cursor'> = {}) => {
    const params = new URLSearchParams()
    for (const field of ['provider', 'agent', 'model', 'effort'] as const) {
      for (const value of filters[field] || []) params.append(field, value)
    }
    if (filters.from) params.set('from', filters.from)
    if (filters.to) params.set('to', filters.to)
    if (filters.snapshotAt) params.set('snapshot_at', filters.snapshotAt)
    return fetchTokenJSON<WorkerTokenUsageSummary>(`/token-usage/summary?${params.toString()}`)
  },
  listTokenUsage: (filters?: { terminalId?: string; runId?: string; stepId?: string; limit?: number }) => {
    const params = [
      filters?.terminalId ? `terminal_id=${encodeURIComponent(filters.terminalId)}` : '',
      filters?.runId ? `run_id=${encodeURIComponent(filters.runId)}` : '',
      filters?.stepId ? `step_id=${encodeURIComponent(filters.stepId)}` : '',
      `limit=${filters?.limit ?? 1000}`,
    ].filter(Boolean).join('&')
    return fetchTokenJSON<WorkerTokenUsageRecord[]>(`/token-usage?${params}`)
  },
}
