import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { tokenApi } from '../token-api'
import { WorkerTokenUsageRecord } from '../token-types'
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

describe('TokenUsagePage', () => {
  afterEach(() => vi.restoreAllMocks())

  it('renders summary totals and worker progress', async () => {
    vi.spyOn(tokenApi, 'listTokenUsage').mockResolvedValue(records)
    render(<TokenUsagePage />)

    await waitFor(() => expect(screen.getByText('2 attempts')).toBeInTheDocument())
    expect(screen.getByText('…/worker-results/review.md')).toBeInTheDocument()
    expect(screen.getByText(/3,000 in current view/)).toBeInTheDocument()
  })

  it('filters records by checked provider label', async () => {
    vi.spyOn(tokenApi, 'listTokenUsage').mockResolvedValue(records)
    render(<TokenUsagePage />)

    await waitFor(() => expect(screen.getByLabelText('Provider: claude_code')).toBeInTheDocument())
    fireEvent.click(screen.getByLabelText('Provider: claude_code'))

    expect(screen.getByText('…/worker-results/review.md')).toBeInTheDocument()
    expect(screen.queryByText('…/worker-results/plan.md')).not.toBeInTheDocument()
    expect(screen.getByText('1 attempts')).toBeInTheDocument()
  })

  it('provides a link back to the dashboard', async () => {
    vi.spyOn(tokenApi, 'listTokenUsage').mockResolvedValue([])
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
})
