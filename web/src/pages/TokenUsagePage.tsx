import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { tokenApi } from '../token-api'
import { TokenApiError } from '../token-api'
import { WorkerTokenUsageRecord, WorkerTokenUsageSummary } from '../token-types'
import { displayDate, displayDay, displayProvider, EMPTY_FILTERS, filterAndSortRecords, formatExact, formatTokens, getPathLabel, labelFor, rangeBounds, recordsToCsv, safeArtifactHref, toggleValue, usageSplit, usageStatus, validateCustomRange, FilterKey, RangeKey, SortKey, TokenFilters } from './tokenUsage'
import { BarChart3, Check, ChevronDown, ChevronRight, Clock3, Database, Download, FileText, Filter, RefreshCw, Search, SlidersHorizontal, X } from 'lucide-react'

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

function ProgressValue({ value }: { value: string | null }) {
  const href = safeArtifactHref(value)
  const label = getPathLabel(value)
  return href ? <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 truncate text-emerald-300 underline decoration-emerald-500/30 underline-offset-2 hover:text-emerald-200"><FileText size={12} />{label}</a> : <span className="truncate">{label}</span>
}

function errorGuidance(error: string | null): { title: string; detail: string } {
  if (!error) return { title: '', detail: '' }
  const lower = error.toLowerCase()
  if (lower.includes('no such table') || lower.includes('migration')) {
    return { title: 'Token usage migration is missing.', detail: 'Restart the CAO server once to create the durable usage table, then refresh.' }
  }
  if (lower.includes('401') || lower.includes('403')) {
    return { title: 'Token usage access is unavailable.', detail: 'Sign in with a scope that can read worker token usage, then retry.' }
  }
  return { title: 'Token usage API is unavailable.', detail: 'The worker usage page could not reach the server. Retry without changing your current filters.' }
}

export function TokenUsagePage() {
  const [records, setRecords] = useState<WorkerTokenUsageRecord[]>([])
  const [summary, setSummary] = useState<WorkerTokenUsageSummary | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [snapshotAt, setSnapshotAt] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<TokenFilters>(EMPTY_FILTERS)
  const [range, setRange] = useState<RangeKey>('all')
  const [sort, setSort] = useState<SortKey>('latest')
  const [query, setQuery] = useState('')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [expandedAttempt, setExpandedAttempt] = useState<string | null>(null)
  const [filtersOpen, setFiltersOpen] = useState(true)
  const requestSequence = useRef(0)

  const customRangeError = range === 'custom' ? validateCustomRange(customFrom, customTo) : null

  const serverQuery = useMemo(() => ({
    ...filters,
    ...rangeBounds(range, new Date(), { from: customFrom, to: customTo }),
  }), [customFrom, customTo, filters, range])

  const loadRecords = useCallback(async (isRefresh = false) => {
    const sequence = ++requestSequence.current
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    if (customRangeError) {
      setError(customRangeError)
      setLoading(false)
      setRefreshing(false)
      return
    }
    try {
      const page = await tokenApi.listTokenUsagePage({ ...serverQuery, limit: 100 })
      const data = await tokenApi.summarizeTokenUsage({ ...serverQuery, snapshotAt: page.snapshot_at })
      if (sequence !== requestSequence.current) return
      setRecords(page.records)
      setNextCursor(page.next_cursor)
      setSnapshotAt(page.snapshot_at)
      setSummary(data)
      setError(null)
    } catch (err) {
      if (sequence !== requestSequence.current) return
      setError(err instanceof TokenApiError ? err.message : err instanceof Error ? err.message : 'Unable to load token usage')
    } finally {
      if (sequence === requestSequence.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [customRangeError, serverQuery])

  const loadMore = useCallback(async () => {
    if (!nextCursor || !snapshotAt || loadingMore) return
    setLoadingMore(true)
    try {
      const page = await tokenApi.listTokenUsagePage({ ...serverQuery, limit: 100, cursor: nextCursor, snapshotAt })
      setRecords(current => [...current, ...page.records])
      setNextCursor(page.next_cursor)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load more token usage')
    } finally {
      setLoadingMore(false)
    }
  }, [loadingMore, nextCursor, serverQuery, snapshotAt])

  useEffect(() => {
    loadRecords()
    const interval = setInterval(() => loadRecords(true), 15000)
    return () => clearInterval(interval)
  }, [loadRecords])

  const options = useMemo(() => ({
    provider: summary?.by_provider.map(bucket => bucket.value).filter((value): value is string => value !== null).sort() || [],
    agent: summary?.by_agent.map(bucket => bucket.value).filter((value): value is string => value !== null).sort() || [],
    model: summary?.by_model.map(bucket => bucket.value || '').sort((a, b) => labelFor(a).localeCompare(labelFor(b))) || [],
    effort: summary?.by_effort.map(bucket => bucket.value || '').sort((a, b) => labelFor(a).localeCompare(labelFor(b))) || [],
  }), [summary])

  const filteredRecords = useMemo(() => {
    return filterAndSortRecords(records, filters, 'all', query, sort)
  }, [records, filters, query, sort])

  const totals = {
    input: summary?.input_tokens || 0,
    output: summary?.output_tokens || 0,
    total: summary?.total_tokens || 0,
  }

  const usageByDay = useMemo<[string, number][]>(() => (summary?.daily || []).slice(-7).map(bucket => [bucket.value || '', bucket.total_tokens]), [summary])
  const usageByModel = useMemo<[string, number][]>(() => (summary?.by_model || []).slice(0, 5).map(bucket => [bucket.value || 'provider default', bucket.total_tokens]), [summary])
  const provenance = useMemo(() => usageSplit(records), [records])

  const maxDay = Math.max(...usageByDay.map(([, value]) => value), 1)
  const maxModel = Math.max(...usageByModel.map(([, value]) => value), 1)
  const activeFilterCount = Object.values(filters).reduce((count, values) => count + values.length, 0) + (range !== 'all' ? 1 : 0) + (query ? 1 : 0)

  const clearFilters = () => {
    setFilters(EMPTY_FILTERS)
    setRange('all')
    setQuery('')
    setCustomFrom('')
    setCustomTo('')
    setNextCursor(null)
    setSnapshotAt(null)
  }

  const guidance = errorGuidance(error)

  const updateCustomDate = (field: 'from' | 'to', value: string) => {
    if (field === 'from') setCustomFrom(value)
    else setCustomTo(value)
    setNextCursor(null)
    setSnapshotAt(null)
  }

  const downloadCsv = () => {
    const blob = new Blob([recordsToCsv(filteredRecords)], { type: 'text/csv;charset=utf-8' })
    const href = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = href
    anchor.download = 'token-usage.csv'
    anchor.click()
    URL.revokeObjectURL(href)
  }

  const toggleFilter = (key: FilterKey, value: string) => {
    setFilters(current => ({ ...current, [key]: toggleValue(current[key], value) }))
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <a href="/" className="text-xs text-emerald-400 hover:text-emerald-300">← Back to Dashboard</a>
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
          <div><p className="font-medium">{guidance.title}</p><p className="mt-1 text-amber-200/70">{guidance.detail}</p><p className="mt-1 text-[11px] text-amber-200/50">{error}</p></div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total tokens" value={formatTokens(totals.total)} detail={`${formatExact(totals.total)} in current view`} tone="bg-emerald-950/60" icon={<BarChart3 size={18} className="text-emerald-400" />} />
        <StatCard label="Input tokens" value={formatTokens(totals.input)} detail="Prompt and context" tone="bg-cyan-950/60" icon={<span className="text-sm font-bold text-cyan-400">IN</span>} />
        <StatCard label="Output tokens" value={formatTokens(totals.output)} detail="Worker responses" tone="bg-violet-950/60" icon={<span className="text-sm font-bold text-violet-400">OUT</span>} />
        <StatCard label="Completed attempts" value={formatExact(summary?.attempts || 0)} detail={summary?.attempts ? `${formatTokens(Math.round(totals.total / summary.attempts))} average / attempt` : 'No records match'} tone="bg-amber-950/60" icon={<Clock3 size={18} className="text-amber-400" />} />
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-gray-800 bg-gray-900/60 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div><h3 className="text-sm font-semibold text-white">Usage provenance</h3><p className="mt-1 text-xs text-gray-500">Loaded records split by provider-reported versus estimate status.</p></div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-md bg-emerald-950/60 px-2.5 py-1.5 text-emerald-300">Native {formatTokens(provenance.native)}</span>
          <span className="rounded-md bg-amber-950/60 px-2.5 py-1.5 text-amber-300">Estimated {formatTokens(provenance.estimated)}</span>
          <span className="rounded-md bg-gray-800 px-2.5 py-1.5 text-gray-400">Unknown {formatTokens(provenance.unknown)}</span>
        </div>
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
          <button type="button" onClick={() => setRange('custom')} className={`rounded-md px-2.5 py-1.5 text-xs font-medium transition ${range === 'custom' ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}>Custom</button>
          {range === 'custom' && <div className="flex items-center gap-2 text-xs text-gray-500"><label>From <input type="date" value={customFrom} onChange={event => updateCustomDate('from', event.target.value)} aria-label="Custom date from" className="rounded-md border border-gray-700 bg-gray-950 px-2 py-1.5 text-xs text-gray-300" /></label><label>To <input type="date" value={customTo} onChange={event => updateCustomDate('to', event.target.value)} aria-label="Custom date to" className="rounded-md border border-gray-700 bg-gray-950 px-2 py-1.5 text-xs text-gray-300" /></label></div>}
          <label className="ml-1 flex items-center gap-2 text-xs text-gray-500">
            Sort
            <select value={sort} onChange={event => setSort(event.target.value as SortKey)} className="rounded-md border border-gray-700 bg-gray-950 px-2 py-1.5 text-xs text-gray-300 outline-none">
              <option value="latest">Latest</option><option value="total">Total tokens</option><option value="input">Input tokens</option><option value="output">Output tokens</option>
            </select>
          </label>
        </div>
        {customRangeError && <p className="text-xs text-amber-300" role="alert">{customRangeError}</p>}
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
              <div className="flex items-center justify-between"><div><h3 className="text-sm font-semibold text-white">Usage by day</h3><p className="mt-1 text-xs text-gray-500">Last 7 days in the current view</p></div><span className="text-xs text-gray-500">{summary?.attempts || 0} attempts</span></div>
              {usageByDay.length ? (
                <div className="mt-5 flex h-36 items-end gap-2 sm:gap-3">
                  {usageByDay.map(([day, value]) => (
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
              {usageByModel.length ? <div className="mt-5 space-y-4">{usageByModel.map(([model, value]) => <div key={model}><div className="mb-1 flex items-center justify-between gap-3 text-xs"><span className="truncate text-gray-300" title={model}>{model}</span><span className="shrink-0 text-gray-500">{formatTokens(value)}</span></div><div className="h-2 rounded-full bg-gray-800"><div className="h-2 rounded-full bg-cyan-400/80" style={{ width: `${Math.max((value / maxModel) * 100, 4)}%` }} /></div></div>)}</div> : <EmptyChart message="No model data yet" />}
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-gray-800 bg-gray-900/60">
            <div className="flex flex-col gap-2 border-b border-gray-800 px-4 py-4 sm:flex-row sm:items-center sm:justify-between"><div><h3 className="text-sm font-semibold text-white">Worker attempts</h3><p className="mt-1 text-xs text-gray-500">Each row is persisted before the worker terminal is torn down.</p></div><div className="flex items-center gap-3"><span className="text-xs text-gray-500">Showing {filteredRecords.length} loaded of {summary?.attempts || 0}</span><button type="button" onClick={downloadCsv} disabled={!filteredRecords.length} className="inline-flex items-center gap-1.5 rounded-md border border-gray-700 px-2.5 py-1.5 text-xs text-gray-300 hover:border-emerald-500/60 hover:text-white disabled:opacity-40"><Download size={13} />CSV</button></div></div>
            {loading ? <div className="px-4 py-12 text-center text-sm text-gray-500">Loading token usage…</div> : filteredRecords.length === 0 ? <div className="px-4 py-12 text-center"><Database size={24} className="mx-auto text-gray-700" /><p className="mt-3 text-sm text-gray-400">{summary?.attempts ? 'No loaded records match this search.' : 'No worker usage records yet.'}</p><p className="mt-1 text-xs text-gray-600">{summary?.attempts ? 'Try clearing the search or loading another page.' : 'Complete a worker attempt after restarting the CAO server migration.'}</p></div> : (
              <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left"><thead className="bg-gray-950/50 text-[10px] uppercase tracking-wider text-gray-500"><tr><th className="px-4 py-3 font-semibold">Recorded</th><th className="px-4 py-3 font-semibold">Progress</th><th className="px-4 py-3 font-semibold">Worker</th><th className="px-4 py-3 font-semibold">Model / effort</th><th className="px-4 py-3 text-right font-semibold">Tokens</th><th className="px-4 py-3 text-right font-semibold">In / out</th></tr></thead><tbody className="divide-y divide-gray-800/80">{filteredRecords.map(row => { const isExpanded = expandedAttempt === row.id; return <Fragment key={row.id}><tr className="cursor-pointer transition hover:bg-gray-800/30" onClick={() => setExpandedAttempt(isExpanded ? null : row.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') setExpandedAttempt(isExpanded ? null : row.id) }} tabIndex={0}><td className="whitespace-nowrap px-4 py-3 align-top"><div className="flex items-center gap-1 text-xs text-gray-300">{isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}{displayDate(row.recorded_at)}</div><div className="mt-1 text-[10px] text-gray-600">{usageStatus(row.estimated)}</div></td><td className="max-w-[300px] px-4 py-3 align-top"><div className="truncate text-xs text-emerald-300" title={row.progress || undefined}><ProgressValue value={row.progress} /></div>{row.step_id && <div className="mt-1 text-[10px] text-gray-600">step: {row.step_id}</div>}</td><td className="px-4 py-3 align-top"><div className="text-xs font-medium text-gray-300">{row.agent}</div><div className="mt-1 text-[10px] capitalize text-gray-600">{displayProvider(row.provider)}</div></td><td className="px-4 py-3 align-top"><div className="max-w-[180px] truncate text-xs text-gray-300" title={row.model || undefined}>{labelFor(row.model)}</div><div className="mt-1 text-[10px] text-gray-500">effort: {labelFor(row.effort)}</div></td><td className="whitespace-nowrap px-4 py-3 text-right align-top"><div className="text-sm font-semibold text-white">{formatExact(row.total_tokens)}</div></td><td className="whitespace-nowrap px-4 py-3 text-right align-top"><div className="text-xs text-gray-400">{formatExact(row.input_tokens)} / {formatExact(row.output_tokens)}</div></td></tr>{isExpanded && <tr><td colSpan={6} className="bg-gray-950/40 px-6 py-4"><div className="grid gap-3 text-xs text-gray-400 sm:grid-cols-3"><div><span className="text-gray-600">Run</span><p className="mt-1 text-gray-300">{labelFor(row.run_id)}</p></div><div><span className="text-gray-600">Step</span><p className="mt-1 text-gray-300">{labelFor(row.step_id)}</p></div><div><span className="text-gray-600">Terminal</span><p className="mt-1 text-gray-300">{row.terminal_id}</p></div></div></td></tr>}</Fragment> })}</tbody></table></div>
            )}
            {!loading && nextCursor && <div className="border-t border-gray-800 px-4 py-4 text-center"><button type="button" onClick={loadMore} disabled={loadingMore} className="inline-flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-900 px-4 py-2 text-sm font-medium text-gray-300 transition hover:border-emerald-500/60 hover:text-white disabled:opacity-50"><RefreshCw size={14} className={loadingMore ? 'animate-spin' : ''} />{loadingMore ? 'Loading…' : 'Load more'}</button></div>}
          </div>
        </div>
      </div>
    </div>
  )
}

function EmptyChart({ message }: { message: string }) {
  return <div className="flex h-36 items-center justify-center text-xs text-gray-600">{message}</div>
}
