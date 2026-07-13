import { describe, expect, it } from 'vitest'
import {
  dailyStats,
  displayProvider,
  filterAndSortRecords,
  formatTokens,
  getPathLabel,
  labelFor,
  modelStats,
  sum,
  toggleValue,
} from '../pages/tokenUsage'
import { WorkerTokenUsageRecord } from '../token-types'

const records: WorkerTokenUsageRecord[] = [
  {
    id: 'new', terminal_id: 'term-2', provider: 'codex', agent: 'planner', run_id: 'run/2', step_id: 'plan',
    model: null, effort: null, progress: '.cao/worker-results/plan.md', input_tokens: 200, output_tokens: 300,
    total_tokens: 500, estimated: true, recorded_at: '2026-07-13T01:00:00Z',
  },
  {
    id: 'old', terminal_id: 'term-1', provider: 'claude_code', agent: 'reviewer', run_id: 'run-1', step_id: 'review',
    model: 'opus', effort: 'high', progress: '.cao/worker-results/review.md', input_tokens: 100, output_tokens: 400,
    total_tokens: 500, estimated: false, recorded_at: '2026-07-12T01:00:00Z',
  },
]

describe('token usage view model helpers', () => {
  it('formats token values and nullable labels', () => {
    expect(formatTokens(999)).toBe('999')
    expect(formatTokens(1_000)).toBe('1.0K')
    expect(formatTokens(1_000_000)).toBe('1.0M')
    expect(labelFor(null)).toBe('Default')
    expect(displayProvider('claude_code')).toBe('claude code')
    expect(getPathLabel(null)).toBe('Progress not recorded')
    expect(getPathLabel('.cao/worker-results/review.md')).toBe('…/worker-results/review.md')
  })

  it('filters with AND across fields and OR within a field', () => {
    const filtered = filterAndSortRecords(
      records,
      { provider: ['codex'], agent: ['planner'], model: [''], effort: [''] },
      'all',
      'RUN/2',
      'latest',
    )
    expect(filtered.map(row => row.id)).toEqual(['new'])
  })

  it('sorts by token count and aggregates the filtered records', () => {
    const sorted = filterAndSortRecords(records, { provider: [], agent: [], model: [], effort: [] }, 'all', '', 'output')
    expect(sorted.map(row => row.id)).toEqual(['old', 'new'])
    expect(sum(sorted, 'input_tokens')).toBe(300)
    expect(sum(sorted, 'output_tokens')).toBe(700)
    expect(sum(sorted, 'total_tokens')).toBe(1_000)
    expect(toggleValue(['codex'], 'codex')).toEqual([])
    expect(toggleValue([], 'codex')).toEqual(['codex'])
  })

  it('groups usage by day and model default bucket', () => {
    expect(dailyStats(records)).toEqual([
      ['2026-07-12', 500],
      ['2026-07-13', 500],
    ])
    expect(modelStats(records)).toEqual([
      ['provider default', 500],
      ['opus', 500],
    ])
  })
})
