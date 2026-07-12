import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { api, WorkerTokenUsageRecord } from '../api'
import { TokenUsagePanel } from '../components/TokenUsagePanel'

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

describe('TokenUsagePanel', () => {
  afterEach(() => vi.restoreAllMocks())

  it('renders summary totals and worker progress', async () => {
    vi.spyOn(api, 'listTokenUsage').mockResolvedValue(records)
    render(<TokenUsagePanel />)

    await waitFor(() => expect(screen.getByText('2 attempts')).toBeInTheDocument())
    expect(screen.getByText('…/worker-results/review.md')).toBeInTheDocument()
    expect(screen.getByText(/3,000 in current view/)).toBeInTheDocument()
  })

  it('filters records by checked provider label', async () => {
    vi.spyOn(api, 'listTokenUsage').mockResolvedValue(records)
    render(<TokenUsagePanel />)

    await waitFor(() => expect(screen.getByLabelText('Provider: claude_code')).toBeInTheDocument())
    fireEvent.click(screen.getByLabelText('Provider: claude_code'))

    expect(screen.getByText('…/worker-results/review.md')).toBeInTheDocument()
    expect(screen.queryByText('…/worker-results/plan.md')).not.toBeInTheDocument()
    expect(screen.getByText('1 attempts')).toBeInTheDocument()
  })
})
