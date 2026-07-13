import { afterEach, describe, expect, it, vi } from 'vitest'
import { TokenApiError, tokenApi } from '../token-api'

describe('Token API wrapper', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('uses the default limit without empty query parameters', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve([]) })
    vi.stubGlobal('fetch', fetchMock)

    await tokenApi.listTokenUsage()

    expect(fetchMock).toHaveBeenCalledWith('/token-usage?limit=1000', expect.objectContaining({ signal: expect.any(AbortSignal) }))
  })

  it('serializes repeated page filters and cursor state', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve({}) })
    vi.stubGlobal('fetch', fetchMock)

    await tokenApi.listTokenUsagePage({ provider: ['codex', 'claude_code'], model: ['__default__'], from: '2026-07-01T00:00:00.000Z', limit: 25, cursor: 'abc', snapshotAt: '2026-07-13T00:00:00.000Z' })

    expect(fetchMock).toHaveBeenCalledWith('/token-usage/page?provider=codex&provider=claude_code&model=__default__&from=2026-07-01T00%3A00%3A00.000Z&limit=25&cursor=abc&snapshot_at=2026-07-13T00%3A00%3A00.000Z', expect.any(Object))
  })

  it('serializes summary filters without pagination parameters', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve({}) })
    vi.stubGlobal('fetch', fetchMock)

    await tokenApi.summarizeTokenUsage({ agent: ['planner'], to: '2026-07-13T00:00:00.000Z' })

    expect(fetchMock).toHaveBeenCalledWith('/token-usage/summary?agent=planner&to=2026-07-13T00%3A00%3A00.000Z', expect.any(Object))
  })

  it('encodes all legacy filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: 'OK', json: () => Promise.resolve([]) })
    vi.stubGlobal('fetch', fetchMock)

    await tokenApi.listTokenUsage({ terminalId: 'term 1', runId: 'run/2', stepId: 'step?&', limit: 25 })

    expect(fetchMock).toHaveBeenCalledWith('/token-usage?terminal_id=term%201&run_id=run%2F2&step_id=step%3F%26&limit=25', expect.any(Object))
  })

  it('surfaces HTTP, JSON, network, and timeout errors', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 503, statusText: 'Unavailable' })
      .mockResolvedValueOnce({ ok: true, status: 200, statusText: 'OK', json: () => Promise.reject(new Error('invalid json')) })
      .mockRejectedValueOnce(new Error('network down'))
    vi.stubGlobal('fetch', fetchMock)

    await expect(tokenApi.listTokenUsage()).rejects.toMatchObject({ status: 503, name: 'TokenApiError' } satisfies Partial<TokenApiError>)
    await expect(tokenApi.listTokenUsage()).rejects.toThrow('invalid json')
    await expect(tokenApi.listTokenUsage()).rejects.toThrow('network down')
  })

  it('aborts a request after the timeout', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn().mockImplementation((_url: string, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('The operation was aborted.', 'AbortError')))
    }))
    vi.stubGlobal('fetch', fetchMock)

    const request = tokenApi.listTokenUsage()
    const assertion = expect(request).rejects.toThrow('aborted')
    await vi.advanceTimersByTimeAsync(10_000)

    await assertion
  })
})
