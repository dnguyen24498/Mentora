import { useEffect, useRef, useState } from 'react'
import { classSceneUrl, describeApiError } from '../api/client'

export interface PinnedSlide {
  /** A blob URL for the slide render, or null while loading / after a refusal. */
  url: string | null
  /** A stable, user-facing error when the pinned bytes cannot be shown. */
  error: string | null
}

/**
 * Load one slide of the package a class pinned (V0-025).
 *
 * The URL is a blob, so the previous one is released when the next slide arrives
 * and on unmount — a lesson that follows a teacher all period does not grow the
 * tab's memory. `order=null` means "nothing to show yet"; no request is made.
 */
export function usePinnedSlide(classId: string, order: number | null): PinnedSlide {
  // The order the loaded URL belongs to. Returning the URL only for the current
  // order means a teacher's move never paints the *previous* slide under the new
  // slide's label while the new render is still being fetched.
  const [loaded, setLoaded] = useState<{ order: number; url: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const liveUrl = useRef<string | null>(null)

  useEffect(() => {
    if (order === null) {
      if (liveUrl.current) {
        URL.revokeObjectURL(liveUrl.current)
        liveUrl.current = null
      }
      setLoaded(null)
      return
    }
    let cancelled = false
    setError(null)
    void (async () => {
      try {
        const next = await classSceneUrl(classId, order)
        if (cancelled) {
          URL.revokeObjectURL(next)
          return
        }
        if (liveUrl.current) URL.revokeObjectURL(liveUrl.current)
        liveUrl.current = next
        setLoaded({ order, url: next })
      } catch (cause) {
        if (!cancelled) {
          // A failed slide must not leave the previous one on screen: the
          // teacher has moved on, and showing stale content would be a lie.
          if (liveUrl.current) {
            URL.revokeObjectURL(liveUrl.current)
            liveUrl.current = null
          }
          setLoaded(null)
          setError(describeApiError(cause))
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [classId, order])

  useEffect(
    () => () => {
      if (liveUrl.current) URL.revokeObjectURL(liveUrl.current)
    },
    [],
  )

  return { url: loaded && loaded.order === order ? loaded.url : null, error }
}
