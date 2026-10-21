/**
 * The narration stream's wire events and an incremental NDJSON reader (V0-013).
 *
 * Every line is one JSON object; a line may arrive split across network chunks,
 * so the reader buffers until a newline. A malformed line is skipped rather than
 * ending the lesson, and an unknown `type` is passed through for the caller to
 * ignore (forward compatible).
 */

export interface NarrationEventBase {
  type: string
  sequence: number
  class_id: string
  scene_id: string
  actor_epoch: number
  state_version: number
  generation: number
}

export interface NarrationStarted extends NarrationEventBase {
  type: 'narration.started'
  source: string
  chunk_count: number
  word_count: number
  voice_id: string
  provider: { name?: string; version?: string; kind?: string }
  empty: boolean
}

export interface NarrationAudio extends NarrationEventBase {
  type: 'audio'
  chunk_index: number
  content_type: string
  duration_ms: number
  data: string
}

export interface NarrationCaption extends NarrationEventBase {
  type: 'caption'
  chunk_index: number
  text: string
}

export interface NarrationFallback extends NarrationEventBase {
  type: 'segment.fallback'
  chunk_index: number
  text: string
  reason: string
}

export interface NarrationCompleted extends NarrationEventBase {
  type: 'narration.completed'
  status: 'COMPLETED' | 'FALLBACK' | 'EMPTY'
  duration_ms: number
  fallback: boolean
}

export interface NarrationError extends NarrationEventBase {
  type: 'error'
  code: string
  message: string
}

export type NarrationEvent =
  | NarrationStarted
  | NarrationAudio
  | NarrationCaption
  | NarrationFallback
  | NarrationCompleted
  | NarrationError
  | (NarrationEventBase & { type: 'segment.started' | 'segment.completed' | 'marker' | 'narration.cancelled' })

function parseLine(line: string): NarrationEvent | null {
  const trimmed = line.trim()
  if (!trimmed) return null
  try {
    const value = JSON.parse(trimmed) as NarrationEvent
    return value && typeof value === 'object' && typeof value.type === 'string' ? value : null
  } catch {
    return null
  }
}

/** Yield events from an NDJSON response as they arrive. */
export async function* readNarrationEvents(response: Response): AsyncGenerator<NarrationEvent> {
  const body = response.body
  if (!body || typeof body.getReader !== 'function') {
    // No streaming body (some test environments): read it whole.
    for (const line of (await response.text()).split('\n')) {
      const event = parseLine(line)
      if (event) yield event
    }
    return
  }
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let newline = buffer.indexOf('\n')
      while (newline >= 0) {
        const event = parseLine(buffer.slice(0, newline))
        buffer = buffer.slice(newline + 1)
        if (event) yield event
        newline = buffer.indexOf('\n')
      }
    }
    buffer += decoder.decode()
    const tail = parseLine(buffer)
    if (tail) yield tail
  } finally {
    reader.releaseLock()
  }
}

/** Decode a base64 audio segment to a playable Blob. */
export function audioBlob(event: NarrationAudio): Blob {
  const binary = atob(event.data)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return new Blob([bytes], { type: event.content_type || 'audio/wav' })
}
