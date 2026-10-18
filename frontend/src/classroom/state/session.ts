import type { SessionSnapshot } from '../../api/client'
import type { ClassroomCommand, ClassroomCommandType, ClassroomEvent } from './types'
import type { ClassroomStore } from './store'
import type { ClassroomTransport } from './transport'
import type { ClassroomTelemetry } from './telemetry'

export interface ClassroomSessionOptions {
  classId: string
  /** Bounded retry for a snapshot load (DEC-RELIABILITY-001). Default 2. */
  retries?: number
  /** Delay between retries in ms. Default 0 (deterministic in tests). */
  delayMs?: number
}

/**
 * Wires a store to a transport: connect, apply ordered events, and recover.
 *
 * Recovery is the point (DEC-RUNTIME-004): a gap or a stale epoch is answered by
 * re-reading the authoritative snapshot, never by guessing at the missing
 * events; a failed load leaves the client frozen and disconnected rather than
 * silently stale.
 */
export class ClassroomSession {
  private unsubscribe: (() => void) | null = null
  private loading = false
  private closed = false

  constructor(
    private readonly store: ClassroomStore,
    private readonly transport: ClassroomTransport,
    private readonly telemetry: ClassroomTelemetry,
    private readonly options: ClassroomSessionOptions,
  ) {}

  async connect(): Promise<void> {
    if (this.closed) return
    this.unsubscribe = this.transport.subscribe(this.onEvent)
    this.telemetry.recordConnect(this.options.classId)
    await this.load('connect')
  }

  disconnect(): void {
    this.closed = true
    this.unsubscribe?.()
    this.unsubscribe = null
    this.transport.close()
  }

  /** Re-read the authoritative snapshot on demand (the recovery control). */
  async resync(): Promise<void> {
    this.telemetry.recordResync(this.options.classId, 'manual', 'requested')
    await this.load('manual')
  }

  /** Send a command; returns false when the transport cannot carry commands. */
  send(type: ClassroomCommandType): boolean {
    if (!this.transport.capabilities.commands) return false
    const command: ClassroomCommand = {
      command_id: newId(),
      type,
      issued_at: new Date().toISOString(),
    }
    this.transport.send(command)
    this.telemetry.recordCommand(this.options.classId, command)
    return true
  }

  private onEvent = (event: ClassroomEvent): void => {
    const outcome = this.store.applyEvent(event)
    this.telemetry.recordEvent(this.options.classId, event, outcome)
    if (outcome === 'gap' || outcome === 'stale-epoch') {
      this.telemetry.recordResync(this.options.classId, outcome, 'requested')
      void this.load(outcome)
    }
  }

  private async load(reason: string): Promise<void> {
    if (this.loading || this.closed) return
    this.loading = true
    this.store.setStatus('resyncing')
    try {
      const snapshot = await this.loadWithRetry()
      this.store.applySnapshot(snapshot)
      this.telemetry.recordSnapshot(this.options.classId, snapshot)
      if (reason !== 'connect') this.telemetry.recordResync(this.options.classId, reason, 'ok')
    } catch (cause) {
      this.store.setStatus('disconnected')
      this.telemetry.recordLoadFailure(
        this.options.classId,
        reason,
        cause instanceof Error ? cause.message : String(cause),
      )
    } finally {
      this.loading = false
    }
  }

  private async loadWithRetry(): Promise<SessionSnapshot> {
    const retries = Math.max(0, this.options.retries ?? 2)
    const delayMs = Math.max(0, this.options.delayMs ?? 0)
    let lastError: unknown
    for (let attempt = 0; attempt <= retries; attempt += 1) {
      try {
        return await this.transport.load()
      } catch (cause) {
        lastError = cause
        if (attempt < retries && delayMs > 0) await sleep(delayMs)
      }
    }
    throw lastError
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function newId(): string {
  const cryptoObject = globalThis.crypto
  if (cryptoObject && typeof cryptoObject.randomUUID === 'function') return cryptoObject.randomUUID()
  return `cmd-${Date.now().toString(36)}-${Math.random().toString(16).slice(2)}`
}
