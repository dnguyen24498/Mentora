import type { SessionSnapshot } from '../../api/client'
import type { ClassroomCommand, ClassroomEvent, EventOutcome } from './types'

/** A sink for structured classroom telemetry (injectable so tests can assert it). */
export interface ClassroomTelemetrySink {
  log(event: Record<string, unknown>): void
}

const consoleSink: ClassroomTelemetrySink = {
  log(event) {
    if (typeof console !== 'undefined' && typeof console.info === 'function') {
      console.info(JSON.stringify(event))
    }
  },
}

export interface ClassroomMetrics {
  connects: number
  resyncs: number
  eventsApplied: number
  eventsIgnored: number
  gaps: number
  staleEpochs: number
  commandsSent: number
  loadFailures: number
}

/**
 * Structured classroom client telemetry (doc 20): identities and counts only —
 * never scene text, transcript, audio or any student content.
 */
export class ClassroomTelemetry {
  readonly metrics: ClassroomMetrics = {
    connects: 0,
    resyncs: 0,
    eventsApplied: 0,
    eventsIgnored: 0,
    gaps: 0,
    staleEpochs: 0,
    commandsSent: 0,
    loadFailures: 0,
  }

  constructor(private readonly sink: ClassroomTelemetrySink = consoleSink) {}

  recordConnect(classId: string): void {
    this.metrics.connects += 1
    this.emit('classroom.connect', { class_id: classId })
  }

  recordSnapshot(classId: string, snapshot: SessionSnapshot): void {
    this.emit('classroom.snapshot', {
      class_id: classId,
      session_id: snapshot.session_id,
      actor_epoch: snapshot.actor_epoch,
      sequence: snapshot.event_sequence,
    })
  }

  recordEvent(classId: string, event: ClassroomEvent, outcome: EventOutcome): void {
    if (outcome === 'applied') this.metrics.eventsApplied += 1
    else if (outcome === 'gap') this.metrics.gaps += 1
    else if (outcome === 'stale-epoch') this.metrics.staleEpochs += 1
    else this.metrics.eventsIgnored += 1
    this.emit('classroom.event', {
      class_id: classId,
      event_id: event.event_id,
      type: event.type,
      sequence: event.sequence,
      actor_epoch: event.actor_epoch,
      outcome,
    })
  }

  recordResync(classId: string, reason: string, phase: 'requested' | 'ok'): void {
    if (phase === 'requested') this.metrics.resyncs += 1
    this.emit('classroom.resync', { class_id: classId, reason, phase })
  }

  recordCommand(classId: string, command: ClassroomCommand): void {
    this.metrics.commandsSent += 1
    this.emit('classroom.command', {
      class_id: classId,
      command_id: command.command_id,
      type: command.type,
    })
  }

  recordLoadFailure(classId: string, reason: string, detail: string): void {
    this.metrics.loadFailures += 1
    this.emit('classroom.load_failed', { class_id: classId, reason, detail })
  }

  private emit(event: string, fields: Record<string, unknown>): void {
    this.sink.log({ event, ...fields })
  }
}
