import { WorkerTokenUsageRecord } from './token-types'

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
