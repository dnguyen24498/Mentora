import { describe, expect, it } from 'vitest'
import { ClassroomSession } from './session'
import { ClassroomStore } from './store'
import { ClassroomTelemetry, type ClassroomTelemetrySink } from './telemetry'
import { ScriptedTransport, makeSnapshot, sceneChangedEvent } from './testing'

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0))

function recordingSink() {
  const events: Record<string, unknown>[] = []
  const sink: ClassroomTelemetrySink = { log: (event) => events.push(event) }
  return { events, sink }
}

describe('classroom session', () => {
  it('connects from the authoritative snapshot, then applies contiguous events', async () => {
    const transport = new ScriptedTransport({ snapshot: makeSnapshot({ sequence: 1 }) })
    const store = new ClassroomStore()
    const session = new ClassroomSession(store, transport, new ClassroomTelemetry(), {
      classId: 'class-1',
      retries: 0,
    })

    await session.connect()
    expect(store.getState().events.status).toBe('live')
    expect(store.getState().snapshot?.session_id).toBe('session-1')

    transport.emit(sceneChangedEvent(2, 'ppt/slides/slide2.xml', 1))
    expect(store.getState().events.scene.sceneId).toBe('ppt/slides/slide2.xml')
    expect(store.getState().events.lastSequence).toBe(2)
    session.disconnect()
  })

  it('requests a resync on a sequence gap and recovers from the snapshot', async () => {
    const transport = new ScriptedTransport({ snapshot: makeSnapshot({ sequence: 1 }) })
    const store = new ClassroomStore()
    const session = new ClassroomSession(store, transport, new ClassroomTelemetry(), {
      classId: 'class-1',
      retries: 0,
    })
    await session.connect()

    // Freeze the resync so the frozen state is observable.
    transport.hold = true
    transport.emit(sceneChangedEvent(3, 'ppt/slides/slide3.xml', 2)) // gap: cursor is 1
    await flush()
    expect(store.getState().events.status).toBe('resyncing')
    expect(store.getState().events.scene.sceneId).toBe('ppt/slides/slide1.xml')

    // The authoritative snapshot now reflects the events the client missed.
    transport.current = makeSnapshot({
      sequence: 3,
      sceneId: 'ppt/slides/slide3.xml',
      sectionIndex: 2,
    })
    transport.release()
    await flush()

    expect(store.getState().events.status).toBe('live')
    expect(store.getState().events.scene.sceneId).toBe('ppt/slides/slide3.xml')
    expect(store.getState().events.lastSequence).toBe(3)
    session.disconnect()
  })

  it('never lets a stale quiet poll move the teacher view backwards', async () => {
    const transport = new ScriptedTransport({
      snapshot: makeSnapshot({ sequence: 2, stateVersion: 2 }),
    })
    const store = new ClassroomStore()
    const session = new ClassroomSession(store, transport, new ClassroomTelemetry(), {
      classId: 'class-1',
      retries: 0,
    })
    await session.connect()
    expect(store.getState().events.stateVersion).toBe(2)

    // A poll that was already in flight when a navigation returned version 3
    // must not overwrite it with version 2.
    transport.current = makeSnapshot({
      sequence: 2,
      stateVersion: 2,
      sceneId: 'ppt/slides/slide3.xml',
      sectionIndex: 2,
    })
    store.applySnapshot(
      makeSnapshot({ sequence: 3, stateVersion: 3, sceneId: 'ppt/slides/slide2.xml', sectionIndex: 1 }),
    )
    await session.poll()
    expect(store.getState().events.stateVersion).toBe(3)
    expect(store.getState().events.scene.sceneId).toBe('ppt/slides/slide2.xml')

    // A poll that is genuinely newer still applies.
    transport.current = makeSnapshot({
      sequence: 4,
      stateVersion: 4,
      sceneId: 'ppt/slides/slide4.xml',
      sectionIndex: 3,
    })
    await session.poll()
    expect(store.getState().events.stateVersion).toBe(4)
    expect(store.getState().events.scene.sceneId).toBe('ppt/slides/slide4.xml')
    session.disconnect()
  })

  it('becomes disconnected after bounded load retries fail', async () => {
    const transport = new ScriptedTransport({ snapshot: makeSnapshot() })
    transport.failNext = 3
    const store = new ClassroomStore()
    const session = new ClassroomSession(store, transport, new ClassroomTelemetry(), {
      classId: 'class-1',
      retries: 2,
    })

    await session.connect()
    expect(store.getState().events.status).toBe('disconnected')
    expect(transport.loadCount).toBe(3) // the first attempt plus two retries
    session.disconnect()
  })

  it('records identities and counts only, never classroom content', async () => {
    const transport = new ScriptedTransport({ snapshot: makeSnapshot() })
    const store = new ClassroomStore()
    const { events, sink } = recordingSink()
    const telemetry = new ClassroomTelemetry(sink)
    const session = new ClassroomSession(store, transport, telemetry, {
      classId: 'class-1',
      retries: 0,
    })

    await session.connect()
    transport.emit(sceneChangedEvent(2, 'ppt/slides/slide2.xml', 1))
    expect(session.send('NAVIGATE_NEXT')).toBe(true)
    expect(transport.sent).toHaveLength(1)

    const names = events.map((event) => event.event)
    expect(names).toContain('classroom.connect')
    expect(names).toContain('classroom.snapshot')
    expect(names).toContain('classroom.event')
    expect(names).toContain('classroom.command')
    expect(telemetry.metrics.eventsApplied).toBe(1)
    expect(telemetry.metrics.commandsSent).toBe(1)
    // No scene text leaks into telemetry.
    expect(JSON.stringify(events)).not.toContain('slide2.xml')
    session.disconnect()
  })

  it('refuses to send a command when the transport cannot carry one', async () => {
    const transport = new ScriptedTransport({
      snapshot: makeSnapshot(),
      capabilities: { liveEvents: false, commands: false },
    })
    const store = new ClassroomStore()
    const session = new ClassroomSession(store, transport, new ClassroomTelemetry(), {
      classId: 'class-1',
      retries: 0,
    })
    await session.connect()
    expect(session.send('NAVIGATE_NEXT')).toBe(false)
    expect(transport.sent).toHaveLength(0)
    session.disconnect()
  })
})
