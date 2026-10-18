import { loadSnapshot, type SessionSnapshot } from '../../api/client'
import type {
  ClassroomCommand,
  ClassroomEvent,
  ClassroomTransportCapabilities,
} from './types'

/**
 * The seam between the classroom client and the actor's transport.
 *
 * V0-011 defines the interface and ships one implementation; the real ordered
 * per-class mechanism is V1-002 and its technology (`DEC-TECH-001`,
 * `DEC-TECH-002`) is `OPEN`, so nothing here names one.
 */
export interface ClassroomTransport {
  readonly capabilities: ClassroomTransportCapabilities
  /** Load the authoritative snapshot (a first load or a resync). */
  load(): Promise<SessionSnapshot>
  /** Subscribe to ordered events; returns an unsubscribe. */
  subscribe(handler: (event: ClassroomEvent) => void): () => void
  /** Send a command to the actor. */
  send(command: ClassroomCommand): void
  close(): void
}

/**
 * The V0 transport: it reads the authoritative snapshot, and nothing else.
 *
 * The ordered per-class command/event mechanism is `DEC-DATA-003`; its
 * technology is `OPEN` and the live stream and command path arrive with V1-002.
 * Until then this transport honestly reports `liveEvents:false` and
 * `commands:false`: the shell shows the authoritative state and says so, rather
 * than faking a stream.
 */
export function createHttpClassroomTransport(
  institutionId: string,
  classId: string,
): ClassroomTransport {
  return {
    capabilities: { liveEvents: false, commands: false },
    load: () => loadSnapshot(institutionId, classId),
    subscribe: () => () => {},
    send: () => {},
    close: () => {},
  }
}
