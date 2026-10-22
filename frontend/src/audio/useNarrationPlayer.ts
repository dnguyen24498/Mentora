import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  describeApiError,
  openNarrationRelay,
  openNarrationStream,
} from '../api/client'
import { audioBlob, readNarrationEvents, type NarrationEvent } from './narrationStream'

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
  | 'waiting'
  | 'loading'
  | 'playing'
  | 'blocked'
  | 'completed'
  | 'fallback'
  | 'empty'
  | 'error'

/** `scene` synthesizes one slide (teacher); `relay` attaches to the teacher (student). */
export type NarrationMode = 'scene' | 'relay'

export interface NarrationPlayerOptions {
  classId: string
  /** The pinned scene order to narrate in `scene` mode; `null` narrates nothing. */
  order?: number | null
  /** Narrate only while true. */
  enabled: boolean
  /** `scene` (default) for the teacher's own generation, `relay` for a student. */
  mode?: NarrationMode
  /** The state version the stage shows; a `scene` request is fenced by it. */
  expectedStateVersion?: number
  /** In `relay` mode, the pinned scene the student's snapshot is showing. */
  expectedSceneId?: string
  /** Called once the whole scene has been heard (`scene` mode). */
  onComplete?: () => void
  createSink?: () => AudioSink
  /** How long `relay` waits before attaching again (204 or a completed slide). */
  retryMs?: number
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
 * The narration player for the teacher's stage and the student's live relay.
 *
 * `scene` mode (teacher): pinned script → semantic chunks → neutral voice → one
 * WAV per chunk → played in order while the slide is on screen. Each chunk plays
 * as soon as it arrives, so the first words are heard after one chunk's synthesis
 * rather than the whole slide's. A slide change, pause or end aborts the request
 * (the server cancels its synthesis) and stops playback; resuming starts a new
 * generation at the start of the current slide — a semantic segment, never a byte
 * offset. On a speech failure the stream carries the authored text instead; it is
 * surfaced as `fallbackText` so the lesson continues (`DEC-TURN-009`).
 *
 * `relay` mode (student, V1-005 bridge): attaches to the generation the teacher's
 * tab is producing. It starts no synthesis. A `204` means "nothing live right
 * now", so the hook waits and attaches again; a response ends at that generation's
 * terminal verdict and the hook attaches again for the next slide. The relay
 * replays the current slide's buffered chunks, so a late joiner hears that slide
 * from its start instead of silence; `afterGeneration` prevents replaying a slide
 * the page already consumed, and `expectedSceneId` keeps the audio tied to the slide
 * the snapshot shows. The browser may still refuse autoplay: `status === 'blocked'`
 * means the page must render the `enable()` button and the hook will reattach from
 * that click.
 */
export function useNarrationPlayer({
  classId,
  order = null,
  enabled,
  mode = 'scene',
  expectedStateVersion,
  expectedSceneId,
  onComplete,
  createSink = createElementSink,
  retryMs = 750,
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
    const relay = mode === 'relay'
    if (!enabled || (!relay && order === null)) {
      setStatus('idle')
      return
    }
    const controller = new AbortController()
    let stopped = false
    // Create the media element only when a chunk actually arrives. A relay in
    // "waiting for the teacher" state never touches an `<audio>` element (and a
    // test/headless browser without media playback is not asked to stop one).
    let sink: AudioSink | null = sinkRef.current
    const ensureSink = (): AudioSink => {
      if (!sink) {
        sink = createSinkRef.current()
        sinkRef.current = sink
      }
      return sink
    }
    setStatus('loading')
    setFallbackText(null)
    setError(null)

    let chain: Promise<void> = Promise.resolve()
    let blocked = false
    let generation: number | null = null
    // The relay generation this page has already consumed in this effect. It is
    // reset when the scene changes (the effect restarts), so a new slide can
    // replay while the same completed slide is not replayed in a wait loop.
    let lastGeneration: number | null = null

    const waitForRetry = () =>
      new Promise<void>((resolve) => {
        if (stopped || controller.signal.aborted) {
          resolve()
          return
        }
        const timer = setTimeout(resolve, Math.max(0, retryMs))
        controller.signal.addEventListener(
          'abort',
          () => {
            clearTimeout(timer)
            resolve()
          },
          { once: true },
        )
      })

    const enqueue = (blob: Blob) => {
      const expected = generation
      chain = chain.then(async () => {
        // A chunk from a generation that has been superseded must never speak
        // over the current one (`DEC-RUNTIME-007`).
        if (stopped || blocked || generation !== expected) return
        try {
          setStatus('playing')
          await ensureSink().play(blob)
        } catch (cause) {
          if (stopped) return
          blocked = true
          if (cause instanceof Error && cause.name === 'NotAllowedError') {
            setStatus('blocked')
          } else {
            setError(cause instanceof Error ? cause.message : 'audio playback failed')
            setStatus('error')
          }
        }
      })
    }

    const handleEvent = (
      event: NarrationEvent,
    ): 'continue' | 'completed' | 'cancelled' | 'terminal' => {
      if (event.type === 'narration.started') {
        if (relay || generation === null) {
          if (generation !== null && event.generation !== generation) {
            sink?.stop()
            chain = Promise.resolve()
          }
          generation = event.generation
        } else if (event.generation !== generation) {
          // The teacher's per-scene stream never changes generation; a mismatch
          // is a stale event and is ignored.
          return 'continue'
        }
        setProvider(event.provider?.name ?? null)
        setStatus('loading')
        setFallbackText(null)
        setError(null)
        return 'continue'
      }

      if (generation !== null && event.generation !== generation) return 'continue'

      switch (event.type) {
        case 'audio':
          enqueue(audioBlob(event))
          return 'continue'
        case 'segment.fallback':
          setFallbackText(event.text)
          return 'continue'
        case 'narration.completed':
          return 'completed'
        case 'narration.cancelled':
          return 'cancelled'
        case 'error':
          setError(`${event.code}: ${event.message}`)
          setStatus('error')
          return 'terminal'
        default:
          return 'continue'
      }
    }

    const consume = async (response: Response) => {
      let terminal = false
      for await (const event of readNarrationEvents(response)) {
        if (stopped) return
        const outcome = handleEvent(event)
        if (outcome === 'completed' && event.type === 'narration.completed') {
          terminal = true
          if (relay) lastGeneration = event.generation
          const verdict = event.status
          await chain
          if (stopped || blocked) return
          if (verdict === 'EMPTY') setStatus('empty')
          else if (verdict === 'FALLBACK') setStatus('fallback')
          else {
            setStatus('completed')
            // Only a fully spoken slide advances the teacher's stage. A fallback
            // or empty script is paced by its text instead. A student's relay
            // never advances anything; it waits for the teacher's next generation.
            if (!relay) onCompleteRef.current?.()
          }
          break
        }
        if (outcome === 'cancelled') {
          terminal = true
          generation = null
          sink?.stop()
          chain = Promise.resolve()
          setStatus(relay ? 'waiting' : 'idle')
          break
        }
        if (outcome === 'terminal') {
          terminal = true
          break
        }
      }
      if (!stopped && !terminal) {
        if (relay) {
          // A relay response can close without a verdict when the teacher's
          // stream was aborted. Attach again rather than treating it as a lesson
          // failure.
          setStatus('waiting')
        } else {
          await chain
          // The stream ended without a terminal verdict: treat it as a failure so
          // the stage's text pacing keeps the lesson moving.
          if (!stopped && !blocked) setStatus('error')
        }
      }
    }

    void (async () => {
      try {
        if (relay) {
          while (!stopped) {
            const response = await openNarrationRelay(classId, {
              afterGeneration: lastGeneration ?? undefined,
              expectedSceneId,
              signal: controller.signal,
            })
            if (stopped) return
            if (response.status === 204) {
              setStatus('waiting')
              await waitForRetry()
              continue
            }
            await consume(response)
            if (stopped || blocked) return
            // A completed/cancelled slide ends its response. Attach again shortly
            // for the next one; an idle 204 above is the "not speaking" path.
            await waitForRetry()
          }
          return
        }

        const response = await openNarrationStream(classId, order as number, {
          expectedStateVersion,
          signal: controller.signal,
        })
        if (!response) throw new ApiError('NARRATION_UNAVAILABLE', 'no narration stream')
        await consume(response)
      } catch (cause) {
        if (stopped || controller.signal.aborted) return
        setError(describeApiError(cause))
        setStatus('error')
      }
    })()

    return () => {
      stopped = true
      controller.abort()
      sink?.stop()
    }
  }, [
    classId,
    order,
    enabled,
    mode,
    expectedStateVersion,
    expectedSceneId,
    retryMs,
    attempt,
  ])

  useEffect(() => () => sinkRef.current?.stop(), [])

  const enable = useCallback(() => setAttempt((value) => value + 1), [])

  return { status, provider, fallbackText, error, enable }
}
