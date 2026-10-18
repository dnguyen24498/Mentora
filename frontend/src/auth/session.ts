import { useSyncExternalStore } from 'react'

/**
 * The signed-in session, shared by every page (V0-021).
 *
 * The session is the *only* thing that decides the tenant: the API derives it
 * from the token, so a page never has to send a tenant with a session (the
 * `X-Institution-Id` header stays for the development shortcut, described
 * below). This module is where the token lives and where the vocabulary of a
 * principal is defined.
 *
 * Two things are deliberately explicit rather than smoothed over:
 *
 * * `principal.authenticated` is false for the development tenant shortcut.
 *   That shortcut is accepted while the backend's `MENTORA_DEV_TENANT_HEADER`
 *   is on (default on) and resolves a *teacher* with no account behind it. It
 *   keeps the V0 teacher flows usable before an institutional-federation
 *   deployment, but it cannot request a class join — there is nobody to bind
 *   the join credential to. The UI says "development mode" rather than
 *   pretending a user is signed in.
 * * The credential mechanism is not a decided technology. The canonical
 *   architecture names institutional federation (OIDC/OAuth) and no ADR
 *   accepts an implementation, so the registered adapter is a labelled
 *   development mock; `authenticator` carries that fact and the UI shows it.
 */

/** A capability a session carries. Kept in step with the API's `Scope` enum. */
export type Scope =
  | 'class:write'
  | 'class:read'
  | 'content:write'
  | 'content:read'
  | 'review:write'
  | 'publication:write'
  | 'enrollment:write'
  | 'scene:read'
  | 'join'

export type Role = 'teacher' | 'student'

/** The identity a request is authorized as (`GET /auth/me`). */
export interface Principal {
  authenticated: boolean
  institution_id: string
  role: Role
  scopes: string[]
  account_id: string | null
  email: string | null
  display_name: string | null
  session_id: string | null
}

/** Who provided a replaceable capability, and whether it is a stand-in. */
export interface CapabilityIdentity {
  id: string
  name: string
  version: string
  kind: 'DEVELOPMENT_MOCK' | 'IMPLEMENTATION'
}

export interface AuthSession {
  token: string
  principal: Principal
  authenticator: CapabilityIdentity
  /** A sentence the API wrote about which mechanism answered. */
  notice: string
  /** A client-side hint about the bounded lifetime; never an authorization control. */
  expiresAt: string
}

const STORAGE_KEY = 'mentora.session'

let cached: AuthSession | null = null
let loaded = false
const listeners = new Set<() => void>()

function isExpired(session: AuthSession): boolean {
  const at = Date.parse(session.expiresAt)
  // An unparseable expiry is treated as valid: the server is the authority, and
  // dropping a fresh session because of a format change would be worse.
  return Number.isFinite(at) && at <= Date.now()
}

function parse(raw: string | null): AuthSession | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as AuthSession
    if (!parsed?.token || !parsed?.principal?.institution_id) return null
    if (isExpired(parsed)) return null
    return parsed
  } catch {
    // A corrupt value is not a session; the user signs in again.
    return null
  }
}

/**
 * The stored session, or null.
 *
 * The result is memoised for `useSyncExternalStore` (a fresh object on every
 * call would re-render forever), so all writes go through the functions below.
 */
export function readSession(): AuthSession | null {
  if (!loaded) {
    try {
      cached = parse(localStorage.getItem(STORAGE_KEY))
    } catch {
      cached = null
    }
    loaded = true
  }
  return cached
}

function publish(session: AuthSession | null, { persist }: { persist: boolean }): void {
  cached = session
  loaded = true
  if (persist) {
    try {
      if (session) localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
      else localStorage.removeItem(STORAGE_KEY)
    } catch {
      // Non-fatal: the session still applies to the page that is open.
    }
  }
  for (const listener of listeners) listener()
}

export function writeSession(session: AuthSession): void {
  // The same rule as reading: a session past its expiry is not a session. The
  // server would refuse it, so keeping it would only make pages look signed in
  // and 401.
  publish(isExpired(session) ? null : session, { persist: true })
}

export function clearSession(): void {
  publish(null, { persist: true })
}

/**
 * The current token, for the API client.
 *
 * Read straight through the memo so a request always carries the newest token;
 * the API client has no React context of its own.
 */
export function currentToken(): string | null {
  return readSession()?.token ?? null
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** The session as React state. */
export function useSession(): AuthSession | null {
  return useSyncExternalStore(subscribe, readSession, () => null)
}

/**
 * Whether the principal behind this request holds a capability.
 *
 * The check is **advisory**: it decides what the UI offers, never what is
 * allowed. The server re-derives scopes from the account's current role on
 * every request and refuses a verb the caller lacks, so a stale client can only
 * ever show a button that fails — never perform the action.
 *
 * With no session the development tenant shortcut is in use, which resolves a
 * teacher server-side, so teacher surfaces stay visible.
 */
export function hasScope(session: AuthSession | null, scope: Scope): boolean {
  if (!session) return true
  return session.principal.scopes.includes(scope)
}

/** Whether the caller is signed in, as opposed to riding the development shortcut. */
export function isSignedIn(session: AuthSession | null): boolean {
  return session?.principal.authenticated === true
}

/** Whether the caller is a student — the role that joins a class rather than runs one. */
export function isStudent(session: AuthSession | null): boolean {
  return session?.principal.role === 'student'
}

/** A short human label for whose session this is. */
export function describePrincipal(session: AuthSession | null): string {
  if (!session) return 'Development mode'
  const who =
    session.principal.display_name || session.principal.email || session.principal.account_id
  return `${who ?? 'Signed in'} · ${session.principal.role}`
}

/** A sentence about the credential mechanism, for a page to show honestly. */
export function describeAuthenticator(session: AuthSession | null): string | null {
  if (!session) return null
  if (session.authenticator.kind === 'DEVELOPMENT_MOCK') {
    return (
      `Signed in through the local development credential mock (${session.authenticator.id}). ` +
      'Institutional federation (OIDC/OAuth) is not decided yet, so this adapter is a ' +
      "stand-in, not the platform's authentication."
    )
  }
  return `Signed in through ${session.authenticator.id}.`
}

/**
 * Keep this tab in step with another tab's sign-in or sign-out.
 *
 * `useSyncExternalStore` cannot subscribe to `storage` for us, so one global
 * listener re-reads the persisted value when another tab writes it. It is
 * registered once, here, rather than per component — the Teacher Studio is
 * routinely open in a second tab, and a sign-out must reach it.
 */
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY && event.key !== null) return
    loaded = false
    publish(readSession(), { persist: false })
  })
}
