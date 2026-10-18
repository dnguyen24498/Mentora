import { useEffect, useState } from 'react'
import { loadPrincipal } from '../api/client'
import { readInstitution } from '../institution'
import { isSignedIn, useSession } from './session'

/**
 * Whether this browser is riding the **development tenant shortcut** — V0-021.
 *
 * The shortcut (`X-Institution-Id`, accepted while the backend's
 * `MENTORA_DEV_TENANT_HEADER` is on) has no session and no account: it resolves a
 * *teacher* server-side. So the client cannot answer "am I signed in?" by looking
 * at its own state — there is none to look at — and it must ask, which is exactly
 * what `GET /auth/me` is for. That endpoint reports `authenticated: false` and
 * `development_shortcut: true` for this case, and `401 SESSION_REQUIRED` when the
 * deployment has switched the shortcut off.
 *
 * This matters because the app must never present the development shortcut as a
 * sign-in — nor present itself as signed out when it is in fact acting as a
 * teacher. Both readings are wrong in the same way: they hide which mode the
 * software is in.
 *
 * The answer is probed once per page and cached, since it can only change when the
 * deployment's configuration does.
 */

let cached: boolean | null = null
let inFlight: Promise<boolean> | null = null

async function probe(): Promise<boolean> {
  if (cached !== null) return cached
  if (inFlight) return inFlight
  inFlight = (async () => {
    try {
      const envelope = await loadPrincipal(readInstitution())
      cached = envelope.principal.authenticated === false
    } catch {
      // `401 SESSION_REQUIRED` means the shortcut is off in this deployment, and
      // any other failure means we cannot tell — either way this browser is not
      // acting as a development teacher.
      cached = false
    } finally {
      inFlight = null
    }
    return cached
  })()
  return inFlight
}

/** Forget the probe, so the next read asks again. Used on sign-in and sign-out. */
export function resetDevelopmentMode(): void {
  cached = null
}

export interface Mode {
  /** A real signed-in account is behind this request. */
  signedIn: boolean
  /** This request is authorized as a teacher by the development header alone. */
  development: boolean
}

export function useMode(): Mode {
  const session = useSession()
  const signedIn = isSignedIn(session)
  const [development, setDevelopment] = useState(cached === true)

  useEffect(() => {
    if (signedIn) {
      setDevelopment(false)
      return
    }
    let cancelled = false
    void probe().then((value) => {
      if (!cancelled) setDevelopment(value)
    })
    return () => {
      cancelled = true
    }
  }, [signedIn])

  return { signedIn, development: signedIn ? false : development }
}
