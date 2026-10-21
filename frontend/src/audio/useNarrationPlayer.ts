import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, describeApiError, openNarrationStream } from '../api/client'
import { audioBlob, readNarrationEvents } from './narrationStream'

/**
 * Plays one audio segment at a time. `play` resolves when the segment has ended
 * and rejects (with a `NotAllowedError`) when the browser's autoplay policy
 * refuses sound before a user gesture.
 */
export interface AudioSink {
  play(blob: Blob): Promise<void>
  stop(): void
}

/** The browser sink: one reused `<audio>` element and an object URL per segment. */
export function createElementSink(): AudioSink {
  const element = typeof Audio === 'function' ? new Audio() : null
  let url: string | null = null
  let settle: (() => void) | null = null
  const release = () => {
    if (url) URL.revokeObjectURL(url)
    url = null
  }
  return {
    play(blob) {
      if (!element) return Promise.reject(new Error('audio playback is unavailable'))
      release()
      url = URL.createObjectURL(blob)
      element.src = url
      return new Promise<void>((resolve, reject) => {
        settle = resolve
        element.onended = () => {
          settle = null
          resolve()
        }
        element.onerror = () => reject(new Error('the audio segment could not be decoded'))
        element.play().catch(reject)
      })
    },
    stop() {
      if (element) {
        try {
          element.pause()
        } catch {
          // An environment without media playback has nothing to stop.
        }
        element.removeAttribute('src')
      }
      release()
      // A stopped segment is finished as far as its waiter is concerned.
      settle?.()
      settle = null
    },
  }
}

export type NarrationStatus =
  | 'idle'
  | 'loading'
  | 'playing'
  | 'blocked'
  | 'completed'
  | 'fallback'
  | 'empty'
  | 'error'

export interface NarrationPlayerOptions {
  classId: string
  /** The pinned scene order to narrate; `null` narrates nothing. */
  order: number | null
  /** Narrate only while true (the stage is playing and the class is running). */
  enabled: boolean
  /** The state version the stage shows; the server refuses a stale one. */
  expectedStateVersion?: number
  /** Called once the whole scene has been heard. */
  onComplete?: () => void
  createSink?: () => AudioSink
}

export interface NarrationPlayer {
  status: NarrationStatus
  provider: string | null
  fallbackText: string | null
  error: string | null
  /** Retry after the browser refused autoplay; call from a click handler. */
  enable: () => void
}

/**
 * The teacher tab's narration player (V0-013).
 *
 * script (pinned package) → semantic chunks → neutral voice → one WAV per chunk →
 * played in order while the slide is on screen. Each chunk plays as soon as it
 * arrives, so the first words are heard after one chunk's synthesis rather than
 * the whole slide's. A slide change, pause or end aborts the request (the server
 * cancels its synthesis) and stops playback; resuming starts a new generation at
 * the start of the current slide — a semantic segment, never a byte offset.
 *
 * On a speech failure the stream carries the authored text instead; it is
 * surfaced as `fallbackText` so the lesson continues (DEC-TURN-009).
 */
export function useNarrationPlayer({
  classId,
  order,
  enabled,
  expectedStateVersion,
  onComplete,
  createSink = createElementSink,
}: NarrationPlayerOptions): NarrationPlayer {
  const [status, setStatus] = useState<NarrationStatus>('idle')
  const [provider, setProvider] = useState<string | null>(null)
  const [fallbackText, setFallbackText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete
  const createSinkRef = useRef(createSink)
  createSinkRef.current = createSink
  const sinkRef = useRef<AudioSink | null>(null)

  useEffect(() => {
    if (!enabled || order === null) {
      setStatus('idle')
      return
    }
    const controller = new AbortController()
    let stopped = false
    if (!sinkRef.current) sinkRef.current = createSinkRef.current()
    const sink = sinkRef.current
    setStatus('loading')
    setFallbackText(null)
    setError(null)

    let chain: Promise<void> = Promise.resolve()
    let blocked = false
    const enqueue = (blob: Blob) => {
      chain = chain.then(async () => {
        if (stopped || blocked) return
        try {
          setStatus('playing')
          await sink.play(blob)
        } catch (cause) {
          if (stopped) return
          blocked = true
          if (cause instanceof Error && cause.name === 'NotAllowedError') setStatus('blocked')
          else {
            setError(cause instanceof Error ? cause.message : 'audio playback failed')
            setStatus('error')
          }
        }
      })
    }

    void (async () => {
      try {
        const response = await openNarrationStream(classId, order, {
          expectedStateVersion,
          signal: controller.signal,
        })
        if (!response) throw new ApiError('NARRATION_UNAVAILABLE', 'no narration stream')
        for await (const event of readNarrationEvents(response)) {
          if (stopped) return
          switch (event.type) {
            case 'narration.started':
              setProvider(event.provider?.name ?? null)
              break
            case 'audio':
              enqueue(audioBlob(event))
              break
            case 'segment.fallback':
              setFallbackText(event.text)
              break
            case 'narration.completed': {
              const verdict = event.status
              await chain
              if (stopped || blocked) return
              if (verdict === 'EMPTY') setStatus('empty')
              else if (verdict === 'FALLBACK') setStatus('fallback')
              else {
                setStatus('completed')
                onCompleteRef.current?.()
              }
              return
            }
            case 'error':
              setError(`${event.code}: ${event.message}`)
              setStatus('error')
              return
            default:
              break
          }
        }
        if (!stopped) {
          await chain
          // The stream ended without a terminal verdict: treat it as a failure so
          // the stage's text pacing keeps the lesson moving.
          if (!stopped && !blocked) setStatus('error')
        }
      } catch (cause) {
        if (stopped || controller.signal.aborted) return
        setError(describeApiError(cause))
        setStatus('error')
      }
    })()

    return () => {
      stopped = true
      controller.abort()
      sink.stop()
    }
  }, [classId, order, enabled, expectedStateVersion, attempt])

  useEffect(() => () => sinkRef.current?.stop(), [])

  const enable = useCallback(() => setAttempt((value) => value + 1), [])

  return { status, provider, fallbackText, error, enable }
}
