import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, WorkerTokenUsageRecord } from '../api'
import { BarChart3, Check, ChevronDown, Clock3, Database, Filter, RefreshCw, Search, SlidersHorizontal, X } from 'lucide-react'

type FilterKey = 'provider' | 'agent' | 'model' | 'effort'
type RangeKey = 'all' | '24h' | '7d' | '30d'
type SortKey = 'latest' | 'total' | 'input' | 'output'

const EMPTY_FILTERS: Record<FilterKey, string[]> = { provider: [], agent: [], model: [], effort: [] }

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(value >= 100_000 ? 0 : 1)}K`
  return value.toLocaleString()
}

function formatExact(value: number): string {
  return value.toLocaleString()
}

function labelFor(value: string | null | undefined): string {
  return value || 'Default'
}

function displayProvider(value: string): string {
  return value.replace(/_cli$/, '').replace(/_/g, ' ')
}

function displayDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function displayDay(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.slice(0, 10)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function getPathLabel(value: string | null): string {
  if (!value) return 'Progress not recorded'
  const parts = value.split('/')
  return parts.length > 2 ? `…/${parts.slice(-2).join('/')}` : value
}

function sum(records: WorkerTokenUsageRecord[], key: 'input_tokens' | 'output_tokens' | 'total_tokens'): number {
  return records.reduce((total, row) => total + row[key], 0)
}

function toggleValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter(item => item !== value) : [...values, value]
}

function FilterGroup({
  title,
  values,
  selected,
  onToggle,
}: {
  title: string
  values: string[]
  selected: string[]
  onToggle: (value: string) => void
}) {
  const [open, setOpen] = useState(true)
  if (values.length === 0) return null
  return (
    <section className="border-t border-gray-800/80 pt-3 first:border-t-0 first:pt-0">
      <button
        type="button"
        className="flex w-full items-center justify-between text-left text-xs font-semibold uppercase tracking-wider text-gray-400"
        onClick={() => setOpen(value => !value)}
        aria-expanded={open}
      >
        <span>{title}</span>
        <ChevronDown size={14} className={`transition-transform ${open ? '' : '-rotate-90'}`} />
      </button>
      {open && (
        <div className="mt-2 space-y-1.5">
          {values.map(value => {
            const checked = selected.includes(value)
            return (
              <label key={value} className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-sm text-gray-300 hover:bg-gray-800/70">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggle(value)}
                  className="sr-only"
                  aria-label={`${title}: ${labelFor(value)}`}
                />
                <span className={`flex h-4 w-4 items-center justify-center rounded border ${checked ? 'border-emerald-400 bg-emerald-500 text-white' : 'border-gray-600 bg-gray-900'}`}>
                  {checked && <Check size={11} strokeWidth={3} />}
                </span>
                <span className="truncate" title={labelFor(value)}>{labelFor(value)}</span>
              </label>
            )
          })}
        </div>
      )}
    </section>
  )
}

function StatCard({ label, value, detail, tone, icon }: { label: string; value: string; detail: string; tone: string; icon: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/70 p-4 shadow-lg shadow-black/10">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-gray-500">{label}</p>
          <p className="mt-2 text-2xl font-bold tracking-tight text-white">{value}</p>
          <p className="mt-1 text-xs text-gray-500">{detail}</p>
        </div>
        <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${tone}`}>{icon}</div>
      </div>
    </div>
  )
}

export function TokenUsagePanel() {
  const [records, setRecords] = useState<WorkerTokenUsageRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<Record<FilterKey, string[]>>(EMPTY_FILTERS)
  const [range, setRange] = useState<RangeKey>('all')
  const [sort, setSort] = useState<SortKey>('latest')
  const [query, setQuery] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(true)

  const loadRecords = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    try {
      const data = await api.listTokenUsage({ limit: 1000 })
      setRecords(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load token usage')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    loadRecords()
    const interval = setInterval(() => loadRecords(true), 15000)
    return () => clearInterval(interval)
  }, [loadRecords])

  const options = useMemo(() => ({
    provider: [...new Set(records.map(row => row.provider))].sort(),
    agent: [...new Set(records.map(row => row.agent))].sort(),
    model: [...new Set(records.map(row => row.model || ''))].sort((a, b) => labelFor(a).localeCompare(labelFor(b))),
    effort: [...new Set(records.map(row => row.effort || ''))].sort((a, b) => labelFor(a).localeCompare(labelFor(b))),
  }), [records])

  const filteredRecords = useMemo(() => {
    const now = Date.now()
    const rangeMs: Record<RangeKey, number | null> = { all: null, '24h': 24 * 60 * 60 * 1000, '7d': 7 * 24 * 60 * 60 * 1000, '30d': 30 * 24 * 60 * 60 * 1000 }
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
  }, [records, filters, range, query, sort])

  const totals = useMemo(() => ({
    input: sum(filteredRecords, 'input_tokens'),
    output: sum(filteredRecords, 'output_tokens'),
    total: sum(filteredRecords, 'total_tokens'),
  }), [filteredRecords])

  const dailyStats = useMemo(() => {
    const byDay = new Map<string, number>()
    filteredRecords.forEach(row => {
      const key = row.recorded_at.slice(0, 10)
      byDay.set(key, (byDay.get(key) || 0) + row.total_tokens)
    })
    return [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-7)
  }, [filteredRecords])

  const modelStats = useMemo(() => {
    const byModel = new Map<string, number>()
    filteredRecords.forEach(row => {
      const key = row.model || 'provider default'
      byModel.set(key, (byModel.get(key) || 0) + row.total_tokens)
    })
    return [...byModel.entries()].sort(([, a], [, b]) => b - a).slice(0, 5)
  }, [filteredRecords])

  const maxDay = Math.max(...dailyStats.map(([, value]) => value), 1)
  const maxModel = Math.max(...modelStats.map(([, value]) => value), 1)
  const activeFilterCount = Object.values(filters).reduce((count, values) => count + values.length, 0) + (range !== 'all' ? 1 : 0) + (query ? 1 : 0)

  const clearFilters = () => {
    setFilters(EMPTY_FILTERS)
    setRange('all')
    setQuery('')
  }

  const toggleFilter = (key: FilterKey, value: string) => {
    setFilters(current => ({ ...current, [key]: toggleValue(current[key], value) }))
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-emerald-400">
            <BarChart3 size={18} />
            <span className="text-xs font-semibold uppercase tracking-[0.18em]">Operations insight</span>
          </div>
          <h2 className="mt-2 text-2xl font-bold tracking-tight text-white">Token Usage</h2>
          <p className="mt-1 max-w-2xl text-sm text-gray-400">See how much context each worker used, what it was working on, and which model or effort level drove the cost.</p>
        </div>
        <button type="button" onClick={() => loadRecords(true)} disabled={refreshing} className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm font-medium text-gray-300 transition hover:border-emerald-500/60 hover:text-white disabled:opacity-50">
          <RefreshCw size={15} className={refreshing ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {error && (
        <div role="alert" className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 text-sm text-amber-200">
          <Database size={18} className="mt-0.5 shrink-0 text-amber-400" />
          <div><p className="font-medium">Token usage is not available yet.</p><p className="mt-1 text-amber-200/70">{error}. Restart the CAO server once so the usage table migration can run.</p></div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total tokens" value={formatTokens(totals.total)} detail={`${formatExact(totals.total)} in current view`} tone="bg-emerald-950/60" icon={<BarChart3 size={18} className="text-emerald-400" />} />
        <StatCard label="Input tokens" value={formatTokens(totals.input)} detail="Prompt and context" tone="bg-cyan-950/60" icon={<span className="text-sm font-bold text-cyan-400">IN</span>} />
        <StatCard label="Output tokens" value={formatTokens(totals.output)} detail="Worker responses" tone="bg-violet-950/60" icon={<span className="text-sm font-bold text-violet-400">OUT</span>} />
        <StatCard label="Completed attempts" value={formatExact(filteredRecords.length)} detail={filteredRecords.length ? `${formatTokens(Math.round(totals.total / filteredRecords.length))} average / attempt` : 'No records match'} tone="bg-amber-950/60" icon={<Clock3 size={18} className="text-amber-400" />} />
      </div>

      <div className="flex flex-col gap-4 rounded-xl border border-gray-800 bg-gray-900/60 p-4 xl:flex-row">
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-gray-800 bg-gray-950/60 px-3 py-2">
          <Search size={16} className="shrink-0 text-gray-500" />
          <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search progress, run, step, terminal, agent…" className="min-w-0 flex-1 bg-transparent text-sm text-gray-200 outline-none placeholder:text-gray-600" aria-label="Search token usage" />
          {query && <button type="button" onClick={() => setQuery('')} aria-label="Clear search" className="text-gray-500 hover:text-white"><X size={15} /></button>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-gray-500"><SlidersHorizontal size={14} /> Range</span>
          {(['all', '24h', '7d', '30d'] as RangeKey[]).map(key => (
            <button key={key} type="button" onClick={() => setRange(key)} className={`rounded-md px-2.5 py-1.5 text-xs font-medium transition ${range === key ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>
              {key === 'all' ? 'All time' : key}
            </button>
          ))}
          <label className="ml-1 flex items-center gap-2 text-xs text-gray-500">
            Sort
            <select value={sort} onChange={event => setSort(event.target.value as SortKey)} className="rounded-md border border-gray-700 bg-gray-950 px-2 py-1.5 text-xs text-gray-300 outline-none">
              <option value="latest">Latest</option><option value="total">Total tokens</option><option value="input">Input tokens</option><option value="output">Output tokens</option>
            </select>
          </label>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[220px_minmax(0,1fr)]">
        <aside className={`rounded-xl border border-gray-800 bg-gray-900/50 p-4 ${filtersOpen ? '' : 'hidden xl:block'}`}>
          <div className="mb-4 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-white"><Filter size={15} className="text-emerald-400" /> Labels</h3>
            {activeFilterCount > 0 && <button type="button" onClick={clearFilters} className="text-xs text-emerald-400 hover:text-emerald-300">Clear ({activeFilterCount})</button>}
          </div>
          <div className="space-y-4">
            <FilterGroup title="Provider" values={options.provider} selected={filters.provider} onToggle={value => toggleFilter('provider', value)} />
            <FilterGroup title="Worker / agent" values={options.agent} selected={filters.agent} onToggle={value => toggleFilter('agent', value)} />
            <FilterGroup title="Model" values={options.model} selected={filters.model} onToggle={value => toggleFilter('model', value)} />
            <FilterGroup title="Effort" values={options.effort} selected={filters.effort} onToggle={value => toggleFilter('effort', value)} />
          </div>
        </aside>

        <div className="min-w-0 space-y-6">
          <button type="button" onClick={() => setFiltersOpen(value => !value)} className="inline-flex items-center gap-2 rounded-lg border border-gray-800 bg-gray-900 px-3 py-2 text-xs font-medium text-gray-400 hover:text-white xl:hidden">
            <Filter size={14} /> {filtersOpen ? 'Hide labels' : 'Show labels'}
          </button>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(260px,1fr)]">
            <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
              <div className="flex items-center justify-between"><div><h3 className="text-sm font-semibold text-white">Usage by day</h3><p className="mt-1 text-xs text-gray-500">Last 7 days in the current view</p></div><span className="text-xs text-gray-500">{filteredRecords.length} attempts</span></div>
              {dailyStats.length ? (
                <div className="mt-5 flex h-36 items-end gap-2 sm:gap-3">
                  {dailyStats.map(([day, value]) => (
                    <div key={day} className="flex min-w-0 flex-1 flex-col items-center gap-2">
                      <span className="text-[10px] text-gray-500">{formatTokens(value)}</span>
                      <div className="flex h-24 w-full items-end"><div className="w-full rounded-t-md bg-gradient-to-t from-emerald-700 to-emerald-400 transition-all" style={{ height: `${Math.max((value / maxDay) * 100, 5)}%` }} title={`${formatExact(value)} tokens`} /></div>
                      <span className="text-[10px] text-gray-500">{displayDay(day)}</span>
                    </div>
                  ))}
                </div>
              ) : <EmptyChart message="No usage in this range" />}
            </div>
            <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
              <h3 className="text-sm font-semibold text-white">By model</h3><p className="mt-1 text-xs text-gray-500">Total tokens by resolved model</p>
              {modelStats.length ? <div className="mt-5 space-y-4">{modelStats.map(([model, value]) => <div key={model}><div className="mb-1 flex items-center justify-between gap-3 text-xs"><span className="truncate text-gray-300" title={model}>{model}</span><span className="shrink-0 text-gray-500">{formatTokens(value)}</span></div><div className="h-2 rounded-full bg-gray-800"><div className="h-2 rounded-full bg-cyan-400/80" style={{ width: `${Math.max((value / maxModel) * 100, 4)}%` }} /></div></div>)}</div> : <EmptyChart message="No model data yet" />}
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-gray-800 bg-gray-900/60">
            <div className="flex flex-col gap-2 border-b border-gray-800 px-4 py-4 sm:flex-row sm:items-center sm:justify-between"><div><h3 className="text-sm font-semibold text-white">Worker attempts</h3><p className="mt-1 text-xs text-gray-500">Each row is persisted before the worker terminal is torn down.</p></div><span className="text-xs text-gray-500">Showing {filteredRecords.length} of {records.length}</span></div>
            {loading ? <div className="px-4 py-12 text-center text-sm text-gray-500">Loading token usage…</div> : filteredRecords.length === 0 ? <div className="px-4 py-12 text-center"><Database size={24} className="mx-auto text-gray-700" /><p className="mt-3 text-sm text-gray-400">{records.length ? 'No records match these filters.' : 'No worker usage records yet.'}</p><p className="mt-1 text-xs text-gray-600">{records.length ? 'Try clearing a label or changing the time range.' : 'Complete a worker attempt after restarting the CAO server migration.'}</p></div> : (
              <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left"><thead className="bg-gray-950/50 text-[10px] uppercase tracking-wider text-gray-500"><tr><th className="px-4 py-3 font-semibold">Recorded</th><th className="px-4 py-3 font-semibold">Progress</th><th className="px-4 py-3 font-semibold">Worker</th><th className="px-4 py-3 font-semibold">Model / effort</th><th className="px-4 py-3 text-right font-semibold">Tokens</th><th className="px-4 py-3 text-right font-semibold">In / out</th></tr></thead><tbody className="divide-y divide-gray-800/80">{filteredRecords.map(row => <tr key={row.id} className="transition hover:bg-gray-800/30"><td className="whitespace-nowrap px-4 py-3 align-top"><div className="text-xs text-gray-300">{displayDate(row.recorded_at)}</div><div className="mt-1 text-[10px] text-gray-600">{row.estimated ? 'estimated' : 'provider reported'}</div></td><td className="max-w-[300px] px-4 py-3 align-top"><div className="truncate text-xs text-emerald-300" title={row.progress || undefined}>{getPathLabel(row.progress)}</div>{row.step_id && <div className="mt-1 text-[10px] text-gray-600">step: {row.step_id}</div>}</td><td className="px-4 py-3 align-top"><div className="text-xs font-medium text-gray-300">{row.agent}</div><div className="mt-1 text-[10px] capitalize text-gray-600">{displayProvider(row.provider)}</div></td><td className="px-4 py-3 align-top"><div className="max-w-[180px] truncate text-xs text-gray-300" title={row.model || undefined}>{labelFor(row.model)}</div><div className="mt-1 text-[10px] text-gray-500">effort: {labelFor(row.effort)}</div></td><td className="whitespace-nowrap px-4 py-3 text-right align-top"><div className="text-sm font-semibold text-white">{formatExact(row.total_tokens)}</div></td><td className="whitespace-nowrap px-4 py-3 text-right align-top"><div className="text-xs text-gray-400">{formatExact(row.input_tokens)} / {formatExact(row.output_tokens)}</div></td></tr>)}</tbody></table></div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function EmptyChart({ message }: { message: string }) {
  return <div className="flex h-36 items-center justify-center text-xs text-gray-600">{message}</div>
}
