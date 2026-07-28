import { describe, expect, it, vi } from 'vitest'
import { copyTerminalSelection } from '../components/TerminalView'

describe('terminal selection auto-copy', () => {
  it('uses the configured clipboard path for a non-empty selection', () => {
    const copyToClipboard = vi.fn()

    copyTerminalSelection('selected over LAN HTTP', copyToClipboard)

    expect(copyToClipboard).toHaveBeenCalledOnce()
    expect(copyToClipboard).toHaveBeenCalledWith('selected over LAN HTTP')
  })

  it('does not copy an empty selection', () => {
    const copyToClipboard = vi.fn()

    copyTerminalSelection('', copyToClipboard)

    expect(copyToClipboard).not.toHaveBeenCalled()
  })
})
