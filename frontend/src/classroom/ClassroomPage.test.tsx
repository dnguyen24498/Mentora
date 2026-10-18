import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import ClassroomPage from './ClassroomPage'
import { ScriptedTransport, TEST_CLASS, makeSnapshot, sceneChangedEvent } from './state/testing'

/**
 * Component-level end-to-end for the classroom page (the repo's `tests/e2e/`
 * convention, V0-007): the page is driven through an injected transport, so no
 * server is needed. The three acceptance criteria of V0-011 are asserted here as
 * the user would see them.
 */

function renderPage(transport: ScriptedTransport) {
  return render(<ClassroomPage classId={TEST_CLASS} createTransport={() => transport} />)
}

describe('ClassroomPage', () => {
  beforeEach(() => {
    localStorage.clear()
    window.history.replaceState({}, '', '/')
  })

  it('restores the scene and state from the authoritative snapshot on refresh', async () => {
    const transport = new ScriptedTransport({
      snapshot: makeSnapshot({
        sceneId: 'ppt/slides/slide2.xml',
        sectionIndex: 1,
        sequence: 4,
        stateVersion: 4,
      }),
    })

    const first = renderPage(transport)
    expect((await screen.findByTestId('classroom-scene-id')).textContent).toContain(
      'ppt/slides/slide2.xml',
    )
    expect(screen.getByTestId('classroom-status').textContent).toMatch(/In sync/i)
    first.unmount()

    // A refresh is a fresh mount against the same authoritative snapshot.
    renderPage(transport)
    expect((await screen.findByTestId('classroom-scene-id')).textContent).toContain(
      'ppt/slides/slide2.xml',
    )
    expect(screen.getByTestId('classroom-status').textContent).toMatch(/In sync/i)
  })

  it('ignores a duplicate event without changing the scene', async () => {
    const transport = new ScriptedTransport({
      snapshot: makeSnapshot({
        sequence: 2,
        stateVersion: 2,
        sceneId: 'ppt/slides/slide2.xml',
        sectionIndex: 1,
      }),
    })
    renderPage(transport)
    await screen.findByTestId('classroom-scene-id')

    act(() => {
      transport.emit(sceneChangedEvent(2, 'ppt/slides/slide9.xml', 8))
    })

    expect(screen.getByTestId('classroom-scene-id').textContent).toContain('ppt/slides/slide2.xml')
    expect(screen.queryByTestId('classroom-recovery')).toBeNull()
    expect(screen.getByTestId('classroom-last-outcome').textContent).toContain('ignored-duplicate')
  })

  it('freezes unsafe controls on a sequence gap and recovers by resync', async () => {
    const transport = new ScriptedTransport({
      snapshot: makeSnapshot({
        sequence: 2,
        stateVersion: 2,
        sceneId: 'ppt/slides/slide2.xml',
        sectionIndex: 1,
      }),
    })
    renderPage(transport)
    await screen.findByTestId('classroom-scene-id')

    const nextButton = () => screen.getByRole('button', { name: 'Next scene' }) as HTMLButtonElement
    expect(nextButton().disabled).toBe(false)

    // Hold the resync so the frozen state is observable.
    transport.hold = true
    act(() => {
      transport.emit(sceneChangedEvent(4, 'ppt/slides/slide4.xml', 3)) // gap: cursor is 2
    })

    const recovery = await screen.findByTestId('classroom-recovery')
    expect(recovery.getAttribute('data-reason')).toBe('gap')
    expect(recovery.getAttribute('role')).toBe('alert')
    expect(nextButton().disabled).toBe(true)
    expect(screen.getByTestId('classroom-scene-id').textContent).toContain('ppt/slides/slide2.xml')

    // The authoritative snapshot now reflects the events the client missed.
    transport.current = makeSnapshot({
      sequence: 4,
      stateVersion: 4,
      sceneId: 'ppt/slides/slide4.xml',
      sectionIndex: 3,
    })
    act(() => {
      transport.release()
    })

    await waitFor(() => expect(screen.queryByTestId('classroom-recovery')).toBeNull())
    expect(screen.getByTestId('classroom-scene-id').textContent).toContain('ppt/slides/slide4.xml')
    expect(nextButton().disabled).toBe(false)
  })

  it('meets the accessibility smoke checks and persists a preference', async () => {
    const transport = new ScriptedTransport({ snapshot: makeSnapshot() })
    renderPage(transport)
    await screen.findByTestId('classroom-scene-id')

    expect(screen.getByRole('heading', { level: 1, name: /Classroom/ })).toBeTruthy()
    expect(screen.getByRole('heading', { level: 2, name: /Live classroom/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Previous scene' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Next scene' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Resynchronise' })).toBeTruthy()

    const status = screen.getByTestId('classroom-status')
    expect(status.getAttribute('aria-live')).toBe('polite')

    const user = userEvent.setup()
    const reduceMotion = screen.getByRole('checkbox', { name: /Reduce motion/ }) as HTMLInputElement
    await user.click(reduceMotion)
    expect(reduceMotion.checked).toBe(true)
    expect(localStorage.getItem('mentora.classroom.prefs')).toContain('"reducedMotion":true')
  })

  it('explains that live events and commands are the V1-002 seam', async () => {
    const transport = new ScriptedTransport({
      snapshot: makeSnapshot(),
      capabilities: { liveEvents: false, commands: false },
    })
    renderPage(transport)
    await screen.findByTestId('classroom-scene-id')

    expect(screen.getByTestId('classroom-transport-notice').textContent).toContain('V1-002')
    expect((screen.getByRole('button', { name: 'Next scene' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
  })
})
