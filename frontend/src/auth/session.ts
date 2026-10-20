import { useSyncExternalStore } from 'react'

/**
 * The signed-in session, shared by every page (V0-021, V0-022, V0-023).
 *
 * The session is the *only* thing that decides the tenant: the API derives it
 * from the token, so a page never has to send a tenant with a session. This module
 * is where the token lives and where the vocabulary of a principal is defined — the
 * three roles the platform models, and the capabilities that decide what each page
 * offers.
 *
 * Two things are deliberately explicit rather than smoothed over:
 *
 * * **No session is no capabilities.** Since V0-023 every page requires a sign-in,
 *   and the development tenant shortcut (`X-Institution-Id`) is off by default. So
 *   `hasScope(null, …)` is `false` for every scope: a caller with no session is
 *   shown nothing, and the route guard sends it to `/login`. A deployment that
 *   turns the shortcut back on does so for *its* clients to use; the UI never
 *   depends on it.
 * * The credential mechanism is not a decided technology. The canonical
 *   architecture names institutional federation (OIDC/OAuth) and no ADR accepts an
 *   implementation, so the registered adapter is a labelled development mock;
 *   `authenticator` carries that fact and the UI shows it.
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
  | 'account:read'
  | 'account:write'

export type Role = 'institution_admin' | 'teacher' | 'student'

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
 * **No session is no capabilities** (V0-023): every page requires a sign-in, and
 * the development tenant shortcut is off by default, so a caller with no session
 * holds nothing and is shown nothing (the route guard sends it to `/login`).
 */
export function hasScope(session: AuthSession | null, scope: Scope): boolean {
  if (!session) return false
  return session.principal.scopes.includes(scope)
}

/** Whether the caller is signed in. */
export function isSignedIn(session: AuthSession | null): boolean {
  return session?.principal.authenticated === true
}

/** Whether the caller is a student — the role that joins a class rather than runs one. */
export function isStudent(session: AuthSession | null): boolean {
  return session?.principal.role === 'student'
}

/**
 * Whether the caller administers the institution's directory (V0-022).
 *
 * Read from the **capability**, not the role name: `account:write` is what the
 * Accounts surface needs, and it is what the server checks.
 */
export function isAdministrator(session: AuthSession | null): boolean {
  return session?.principal.scopes.includes('account:write') === true
}

/** A short human label for a role, for a chip or a heading. */
export function describeRole(role: Role | null | undefined): string {
  if (role === 'institution_admin') return 'Administrator'
  if (role === 'teacher') return 'Teacher'
  if (role === 'student') return 'Student'
  return 'Not signed in'
}

/** A short human label for whose session this is. */
export function describePrincipal(session: AuthSession | null): string {
  if (!session) return 'Not signed in'
  const who =
    session.principal.display_name || session.principal.email || session.principal.account_id
  return `${who ?? 'Signed in'} · ${describeRole(session.principal.role)}`
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
