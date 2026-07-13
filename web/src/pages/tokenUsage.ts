import { WorkerTokenUsageRecord } from '../token-types'

export type FilterKey = 'provider' | 'agent' | 'model' | 'effort'
export type RangeKey = 'all' | '24h' | '7d' | '30d' | 'custom'
export type SortKey = 'latest' | 'total' | 'input' | 'output'
export type TokenFilters = Record<FilterKey, string[]>

export const EMPTY_FILTERS: TokenFilters = { provider: [], agent: [], model: [], effort: [] }

export function rangeBounds(
  range: RangeKey,
  now = new Date(),
  custom: { from?: string; to?: string } = {},
): { from?: string; to?: string } {
  if (range === 'custom') {
    const from = custom.from ? new Date(`${custom.from}T00:00:00`) : null
    const to = custom.to ? new Date(`${custom.to}T23:59:59.999`) : null
    return {
      ...(from && !Number.isNaN(from.getTime()) ? { from: from.toISOString() } : {}),
      ...(to && !Number.isNaN(to.getTime()) ? { to: to.toISOString() } : {}),
    }
  }
  const durations: Record<RangeKey, number | null> = { all: null, '24h': 24 * 60 * 60 * 1000, '7d': 7 * 24 * 60 * 60 * 1000, '30d': 30 * 24 * 60 * 60 * 1000, custom: null }
  const duration = durations[range]
  return duration === null ? {} : { from: new Date(now.getTime() - duration).toISOString(), to: now.toISOString() }
}

export function validateCustomRange(from: string, to: string): string | null {
  if (!from || !to) return 'Choose both a start and end date.'
  const start = new Date(`${from}T00:00:00`)
  const end = new Date(`${to}T23:59:59.999`)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return 'Enter valid calendar dates.'
  if (start.getTime() > end.getTime()) return 'Start date must be on or before end date.'
  return null
}

export function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(value >= 100_000 ? 0 : 1)}K`
  return value.toLocaleString()
}

export function formatExact(value: number): string {
  return value.toLocaleString()
}

export function labelFor(value: string | null | undefined): string {
  return value || 'Default'
}

export function displayProvider(value: string): string {
  return value.replace(/_cli$/, '').replace(/_/g, ' ')
}

export function displayDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function displayDay(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.slice(0, 10)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function getPathLabel(value: string | null): string {
  if (!value) return 'Progress not recorded'
  const parts = value.split('/')
  return parts.length > 2 ? `…/${parts.slice(-2).join('/')}` : value
}

export function safeArtifactHref(value: string | null): string | null {
  if (!value || value.length > 512 || /[\u0000-\u001f\\?#]/.test(value)) return null
  if (!value.startsWith('.cao/worker-results/')) return null
  const parts = value.split('/')
  if (parts.some(part => !part || part === '.' || part === '..')) return null
  return value
}

function csvCell(value: string | number | boolean | null): string {
  const text = value === null ? '' : String(value)
  const safeText = /^[=+\-@]/.test(text) ? `'${text}` : text
  return /[",\n\r]/.test(safeText) ? `"${safeText.replace(/"/g, '""')}"` : safeText
}

export function recordsToCsv(records: WorkerTokenUsageRecord[]): string {
  const headers = ['recorded_at', 'provider', 'agent', 'run_id', 'step_id', 'progress', 'model', 'effort', 'input_tokens', 'output_tokens', 'total_tokens', 'estimated']
  const rows = records.map(row => [
    row.recorded_at, row.provider, row.agent, row.run_id, row.step_id, row.progress, row.model, row.effort,
    row.input_tokens, row.output_tokens, row.total_tokens, row.estimated,
  ].map(csvCell).join(','))
  return `\ufeff${headers.join(',')}\n${rows.join('\n')}${rows.length ? '\n' : ''}`
}

export function usageSplit(records: WorkerTokenUsageRecord[]): { native: number; estimated: number; unknown: number } {
  return records.reduce((split, row) => {
    if (row.estimated === false) split.native += row.total_tokens
    else if (row.estimated === true) split.estimated += row.total_tokens
    else split.unknown += row.total_tokens
    return split
  }, { native: 0, estimated: 0, unknown: 0 })
}

export function usageStatus(value: boolean | null | undefined): 'native' | 'estimated' | 'unknown' {
  if (value === false) return 'native'
  if (value === true) return 'estimated'
  return 'unknown'
}

export function sum(records: WorkerTokenUsageRecord[], key: 'input_tokens' | 'output_tokens' | 'total_tokens'): number {
  return records.reduce((total, row) => total + row[key], 0)
}

export function toggleValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter(item => item !== value) : [...values, value]
}

export function filterAndSortRecords(
  records: WorkerTokenUsageRecord[],
  filters: TokenFilters,
  range: RangeKey,
  query: string,
  sort: SortKey,
): WorkerTokenUsageRecord[] {
  const now = Date.now()
  const rangeMs: Record<RangeKey, number | null> = { all: null, '24h': 24 * 60 * 60 * 1000, '7d': 7 * 24 * 60 * 60 * 1000, '30d': 30 * 24 * 60 * 60 * 1000, custom: null }
  const needle = query.trim().toLowerCase()
  return records.filter(row => {
    const date = new Date(row.recorded_at).getTime()
    const inRange = rangeMs[range] === null || (!Number.isNaN(date) && now - date <= rangeMs[range]!)
    const matchesSearch = !needle || [row.progress, row.run_id, row.step_id, row.terminal_id, row.agent, row.model].some(value => value?.toLowerCase().includes(needle))
    return inRange && matchesSearch &&
      (!filters.provider.length || filters.provider.includes(row.provider)) &&
      (!filters.agent.length || filters.agent.includes(row.agent)) &&
      (!filters.model.length || filters.model.includes(row.model || '')) &&
      (!filters.effort.length || filters.effort.includes(row.effort || ''))
  }).sort((a, b) => {
    if (sort === 'total') return b.total_tokens - a.total_tokens
    if (sort === 'input') return b.input_tokens - a.input_tokens
    if (sort === 'output') return b.output_tokens - a.output_tokens
    return new Date(b.recorded_at).getTime() - new Date(a.recorded_at).getTime()
  })
}

export function dailyStats(records: WorkerTokenUsageRecord[]): [string, number][] {
  const byDay = new Map<string, number>()
  records.forEach(row => {
    const key = row.recorded_at.slice(0, 10)
    byDay.set(key, (byDay.get(key) || 0) + row.total_tokens)
  })
  return [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-7)
}

export function modelStats(records: WorkerTokenUsageRecord[]): [string, number][] {
  const byModel = new Map<string, number>()
  records.forEach(row => {
    const key = row.model || 'provider default'
    byModel.set(key, (byModel.get(key) || 0) + row.total_tokens)
  })
  return [...byModel.entries()].sort(([, a], [, b]) => b - a).slice(0, 5)
}
