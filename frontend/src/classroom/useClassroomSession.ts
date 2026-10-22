import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import type { SessionSnapshot } from '../api/client'
import { ClassroomStore } from './state/store'
import { ClassroomSession, type ClassroomSessionOptions } from './state/session'
import { ClassroomTelemetry } from './state/telemetry'
import { createHttpClassroomTransport, type ClassroomTransport } from './state/transport'
import type {
  ClassroomCommandType,
  ClassroomState,
  ClassroomTransportCapabilities,
  ClassroomUiPreferences,
} from './state/types'

export interface UseClassroomSessionArgs {
  institutionId: string
  classId: string
  /** Injectable for tests (and for the future ordered transport, V1-002). */
  createTransport?: (institutionId: string, classId: string) => ClassroomTransport
  telemetry?: ClassroomTelemetry
  sessionOptions?: Omit<ClassroomSessionOptions, 'classId'>
}

export interface ClassroomSessionApi {
  state: ClassroomState
  capabilities: ClassroomTransportCapabilities
  send: (type: ClassroomCommandType) => void
  resync: () => void
  /** Quietly re-read the snapshot (the teacher follows the background presenter). */
  poll: () => void
  /** Apply a snapshot the server returned (e.g. a navigation command's result). */
  applySnapshot: (snapshot: SessionSnapshot) => void
  toggleFocusScene: () => void
  updatePreferences: (patch: Partial<ClassroomUiPreferences>) => void
}

const OFF_DEFAULT: ClassroomTransportCapabilities = { liveEvents: false, commands: false }

/**
 * Owns the classroom store and session for one mounted page.
 *
 * The store lives for the page's lifetime; the session connects on mount and
 * disconnects on unmount, so a refresh (a fresh mount) re-reads the authoritative
 * snapshot. The connect factory is read through a ref, so passing a fresh closure
 * each render never re-opens the session.
 */
export function useClassroomSession({
  institutionId,
  classId,
  createTransport,
  telemetry,
  sessionOptions,
}: UseClassroomSessionArgs): ClassroomSessionApi {
  const storeRef = useRef<ClassroomStore | null>(null)
  if (storeRef.current === null) storeRef.current = new ClassroomStore()
  const store = storeRef.current

  const [capabilities, setCapabilities] = useState<ClassroomTransportCapabilities>(OFF_DEFAULT)
  const sessionRef = useRef<ClassroomSession | null>(null)

  const latest = useRef({ createTransport, telemetry, sessionOptions })
  useEffect(() => {
    latest.current = { createTransport, telemetry, sessionOptions }
  })

  useEffect(() => {
    const factory = latest.current.createTransport ?? createHttpClassroomTransport
    const transport = factory(institutionId, classId)
    const session = new ClassroomSession(
      store,
      transport,
      latest.current.telemetry ?? new ClassroomTelemetry(),
      { classId, ...latest.current.sessionOptions },
    )
    sessionRef.current = session
    setCapabilities(transport.capabilities)
    void session.connect()
    return () => {
      session.disconnect()
      if (sessionRef.current === session) sessionRef.current = null
    }
  }, [store, institutionId, classId])

  const state = useSyncExternalStore(store.subscribe, store.getState, store.getState)

  const send = useCallback((type: ClassroomCommandType) => {
    void sessionRef.current?.send(type)
  }, [])

  const resync = useCallback(() => {
    void sessionRef.current?.resync()
  }, [])

  const poll = useCallback(() => {
    void sessionRef.current?.poll()
  }, [])

  const applySnapshot = useCallback(
    (snapshot: SessionSnapshot) => {
      store.applySnapshot(snapshot)
    },
    [store],
  )

  const toggleFocusScene = useCallback(() => {
    store.setUi({ focusScene: !store.getState().ui.focusScene })
  }, [store])

  const updatePreferences = useCallback(
    (patch: Partial<ClassroomUiPreferences>) => {
      store.updatePreferences(patch)
    },
    [store],
  )

  return { state, capabilities, send, resync, poll, applySnapshot, toggleFocusScene, updatePreferences }
}
