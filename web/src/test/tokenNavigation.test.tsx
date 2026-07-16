import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../api', () => ({
  api: {
    getMemoryStatus: () => Promise.resolve({ enabled: false }),
  },
}))

vi.mock('../store', () => ({
  useStore: () => ({ sessions: [], connected: false, fetchSessions: () => Promise.resolve(), snackbar: null, hideSnackbar: () => {} }),
}))

vi.mock('../components/DashboardHome', () => ({ DashboardHome: () => <div /> }))

import App from '../App'

describe('Token navigation', () => {
  it('keeps token usage out of dashboard tabs and exposes one standalone link', () => {
    render(<App />)

    expect(screen.queryByRole('tab', { name: /token usage/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Token' })).toHaveAttribute('href', '/token.html')
  })
})
