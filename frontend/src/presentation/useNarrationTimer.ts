import { useEffect, useRef } from 'react'

export interface NarrationTimerOptions {
  /** Whether the narration is running. */
  playing: boolean
  /** How long the current segment should stay on screen. */
  durationMs: number
  /**
   * Identifies the current segment. The timer restarts when it changes even if
   * the new segment happens to have the same length, so two equally long slides
   * do not merge into one tick.
   */
  segmentKey: string
  /** Called once the segment has been on screen long enough. */
  onElapsed: () => void
}

/**
 * One timer per narrated segment.
 *
 * `onElapsed` is held in a ref so a re-render (a keystroke, a fetch settling)
 * cannot silently restart the countdown — the timer only depends on whether it is
 * playing, how long the segment is, and which segment it is.
 */
export function useNarrationTimer({
  playing,
  durationMs,
  segmentKey,
  onElapsed,
}: NarrationTimerOptions): void {
  const callback = useRef(onElapsed)

  useEffect(() => {
    callback.current = onElapsed
  }, [onElapsed])

  useEffect(() => {
    if (!playing) return undefined
    const timer = window.setTimeout(() => callback.current(), durationMs)
    return () => window.clearTimeout(timer)
  }, [playing, durationMs, segmentKey])
}
