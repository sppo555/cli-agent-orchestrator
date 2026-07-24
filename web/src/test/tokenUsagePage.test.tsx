import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { tokenApi } from '../token-api'
import { WorkerTokenUsagePage, WorkerTokenUsageRecord, WorkerTokenUsageSummary } from '../token-types'
import { TokenUsagePage } from '../pages/TokenUsagePage'

const records: WorkerTokenUsageRecord[] = [
  {
    id: 'u1', terminal_id: 'term-1', provider: 'claude_code', agent: 'reviewer', run_id: 'run-1', step_id: 'review',
    model: 'claude-opus-4-8', effort: 'high', progress: '.cao/worker-results/review.md', input_tokens: 1000, output_tokens: 500,
    total_tokens: 1500, estimated: true, recorded_at: '2026-07-13T01:00:00Z',
  },
  {
    id: 'u2', terminal_id: 'term-2', provider: 'codex', agent: 'planner', run_id: 'run-1', step_id: 'plan',
    model: 'gpt-5', effort: 'medium', progress: '.cao/worker-results/plan.md', input_tokens: 800, output_tokens: 700,
    total_tokens: 1500, estimated: true, recorded_at: '2026-07-12T01:00:00Z',
  },
]

const page = (pageRecords: WorkerTokenUsageRecord[] = records): WorkerTokenUsagePage => ({ records: pageRecords, next_cursor: null, has_more: false, snapshot_at: '2026-07-13T02:00:00+00:00' })
const summary = (summaryRecords: WorkerTokenUsageRecord[] = records): WorkerTokenUsageSummary => ({
  attempts: summaryRecords.length,
  input_tokens: summaryRecords.reduce((total, row) => total + row.input_tokens, 0),
  output_tokens: summaryRecords.reduce((total, row) => total + row.output_tokens, 0),
  total_tokens: summaryRecords.reduce((total, row) => total + row.total_tokens, 0),
  daily: [{ value: '2026-07-13', attempts: summaryRecords.length, input_tokens: 1800, output_tokens: 1200, total_tokens: summaryRecords.reduce((total, row) => total + row.total_tokens, 0) }],
  by_provider: [
    ...[...new Set(summaryRecords.map(row => row.provider))].map(value => ({ value, attempts: 1, input_tokens: 0, output_tokens: 0, total_tokens: 1500, native_attempts: 0, estimated_attempts: 1, native_tokens: 0, estimated_tokens: 1500 })),
    { value: 'antigravity_cli', attempts: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0, native_attempts: 0, estimated_attempts: 0, native_tokens: 0, estimated_tokens: 0 },
  ],
  by_agent: [...new Set(summaryRecords.map(row => row.agent))].map(value => ({ value, attempts: 1, input_tokens: 0, output_tokens: 0, total_tokens: 1500 })),
  by_model: [...new Set(summaryRecords.map(row => row.model))].map(value => ({ value, attempts: 1, input_tokens: 0, output_tokens: 0, total_tokens: 1500 })),
  by_effort: [...new Set(summaryRecords.map(row => row.effort))].map(value => ({ value, attempts: 1, input_tokens: 0, output_tokens: 0, total_tokens: 1500 })),
  snapshot_at: '2026-07-13T02:00:00+00:00',
})

describe('TokenUsagePage', () => {
  afterEach(() => vi.restoreAllMocks())

  it('renders summary totals and worker progress', async () => {
    vi.spyOn(tokenApi, 'listTokenUsagePage').mockResolvedValue(page())
    vi.spyOn(tokenApi, 'summarizeTokenUsage').mockResolvedValue(summary())
    render(<TokenUsagePage />)

    await waitFor(() => expect(screen.getByText('2 attempts')).toBeInTheDocument())
    expect(screen.getByText('…/worker-results/review.md')).toBeInTheDocument()
    expect(screen.getByText(/3,000 in current view/)).toBeInTheDocument()
  })

  it('filters records by checked provider label', async () => {
    vi.spyOn(tokenApi, 'listTokenUsagePage').mockImplementation(async filters => page(filters?.provider?.includes('claude_code') ? [records[0]] : records))
    vi.spyOn(tokenApi, 'summarizeTokenUsage').mockImplementation(async filters => summary(filters?.provider?.includes('claude_code') ? [records[0]] : records))
    render(<TokenUsagePage />)

    await waitFor(() => expect(screen.getByLabelText('Provider: claude_code')).toBeInTheDocument())
    fireEvent.click(screen.getByLabelText('Provider: claude_code'))

    await waitFor(() => {
      expect(screen.getByText('…/worker-results/review.md')).toBeInTheDocument()
      expect(screen.queryByText('…/worker-results/plan.md')).not.toBeInTheDocument()
      expect(screen.getByText('1 attempts')).toBeInTheDocument()
    })
  })

  it('keeps zero-usage providers visible with friendly labels and totals', async () => {
    vi.spyOn(tokenApi, 'listTokenUsagePage').mockResolvedValue(page())
    vi.spyOn(tokenApi, 'summarizeTokenUsage').mockResolvedValue(summary())
    render(<TokenUsagePage />)

    await waitFor(() => expect(screen.getByLabelText('Provider: antigravity_cli')).toBeInTheDocument())
    expect(screen.getByText('Agy')).toBeInTheDocument()
    expect(screen.getAllByText('0').length).toBeGreaterThan(0)
  })

  it('provides a link back to the dashboard', async () => {
    vi.spyOn(tokenApi, 'listTokenUsagePage').mockResolvedValue(page([]))
    vi.spyOn(tokenApi, 'summarizeTokenUsage').mockResolvedValue(summary([]))
    render(<TokenUsagePage />)

    expect(screen.getByRole('link', { name: /back to dashboard/i })).toHaveAttribute('href', '/')
  })

  it('uses the durable token usage endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: () => Promise.resolve(records),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(tokenApi.listTokenUsage({ limit: 25 })).resolves.toEqual(records)
    expect(fetchMock).toHaveBeenCalledWith('/token-usage?limit=25', expect.objectContaining({ signal: expect.any(AbortSignal) }))
  })

  it('opens an attempt drill-down and exposes provenance split', async () => {
    vi.spyOn(tokenApi, 'listTokenUsagePage').mockResolvedValue(page())
    vi.spyOn(tokenApi, 'summarizeTokenUsage').mockResolvedValue(summary())
    render(<TokenUsagePage />)

    await waitFor(() => expect(screen.getByRole('link', { name: /review\.md/ })).toBeInTheDocument())
    expect(screen.getByText('Native 0')).toBeInTheDocument()
    expect(screen.getByText('Estimated 3.0K')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: /review\.md/ }))
    expect(screen.getByText('run-1')).toBeInTheDocument()
    expect(screen.getByText('term-1')).toBeInTheDocument()
  })

  it('shows migration guidance and retries after an API error', async () => {
    const list = vi.spyOn(tokenApi, 'listTokenUsagePage')
      .mockRejectedValueOnce(new Error('500 Failed to summarize token usage: no such table: worker_token_usage'))
      .mockResolvedValueOnce(page([]))
    vi.spyOn(tokenApi, 'summarizeTokenUsage').mockResolvedValue(summary([]))
    render(<TokenUsagePage />)

    await waitFor(() => expect(screen.getByText('Token usage migration is missing.')).toBeInTheDocument())
    expect(screen.getByText(/Restart the CAO server once/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /refresh/i }))
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
    expect(screen.queryByText('Token usage migration is missing.')).not.toBeInTheDocument()
  })

  it('resets pagination state when a custom date range changes', async () => {
    const list = vi.spyOn(tokenApi, 'listTokenUsagePage').mockResolvedValue(page())
    vi.spyOn(tokenApi, 'summarizeTokenUsage').mockResolvedValue(summary())
    render(<TokenUsagePage />)

    await waitFor(() => expect(screen.getByText('2 attempts')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Custom' }))
    fireEvent.change(screen.getByLabelText('Custom date from'), { target: { value: '2026-07-01' } })
    fireEvent.change(screen.getByLabelText('Custom date to'), { target: { value: '2026-07-13' } })

    await waitFor(() => {
      const latest = list.mock.calls[list.mock.calls.length - 1]?.[0]
      expect(new Date(latest?.from || '').getTime()).toBe(new Date('2026-07-01T00:00:00').getTime())
      expect(new Date(latest?.to || '').getTime()).toBe(new Date('2026-07-13T23:59:59.999').getTime())
      expect(latest?.cursor).toBeUndefined()
      expect(latest?.snapshotAt).toBeUndefined()
    })
  })
})
