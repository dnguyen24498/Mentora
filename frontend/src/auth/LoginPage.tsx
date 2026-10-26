import { useState } from 'react'
import {
  ApiError,
  bootstrapAdministrator,
  describeApiError,
  login,
  logout,
  sessionFrom,
} from '../api/client'
import { DEFAULT_INSTITUTION, useInstitution, writeInstitution } from '../institution'
import {
  clearSession,
  describeAuthenticator,
  describePrincipal,
  useSession,
  writeSession,
} from './session'
import {
  Banner,
  BUTTON_PRIMARY,
  BUTTON_SECONDARY,
  Field,
  INPUT_CLASS,
  PAGE_PADDING,
  Panel,
} from '../components/ui'
import { LIBRARY_PATH, Link, navigate } from '../router'

/** The shortest password the backend will store, mirrored for a helpful hint. */
const MIN_PASSWORD_LENGTH = 8

/**
 * Sign in — `/login` (V0-021, V0-023). The **only** page reachable without a
 * session: every other route renders this form until there is one.
 *
 * The form is the whole credential exchange: an institution (the tenant the
 * account lives in), an address and a **password**. Administrators and teachers set
 * a password when they create an account, and the account holder can change it
 * afterwards (`Settings → Security`). The password is deliberately not presented as
 * a decided mechanism: the canonical architecture names **institutional federation**
 * (OIDC/OAuth), no ADR accepts an implementation, so the adapter behind this form is
 * a labelled development mock — and the page says so rather than presenting it as
 * the platform's authentication.
 *
 * Three roles sign in through this one form — an institution administrator, a
 * teacher and a student — because who you are is the account's role, not a choice on
 * this page. The **first** administrator is the one thing that cannot be signed into
 * existence: a fresh installation has no accounts at all, so the deployment
 * bootstrap creates that account here, once, and closes the moment the tenant has an
 * administrator. After that `Admin → Accounts` creates everyone else.
 */
export default function LoginPage() {
  const session = useSession()
  const [institution, setInstitution] = useInstitution()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The first-administrator bootstrap. Kept beside the sign-in form rather than on
  // its own page, because creating that account is a *precondition* for signing in
  // as anyone who can administer anything.
  const [adminEmail, setAdminEmail] = useState('')
  const [adminPassword, setAdminPassword] = useState('')
  const [adminBusy, setAdminBusy] = useState(false)
  const [adminError, setAdminError] = useState<string | null>(null)
  const [adminCreated, setAdminCreated] = useState<string | null>(null)

  function nextPath(): string {
    // `/login?next=/join/abc` returns the teacher (or the student) to what they
    // were opening. Only a same-origin path is honoured.
    try {
      const next = new URLSearchParams(window.location.search).get('next')
      if (next && next.startsWith('/') && !next.startsWith('//')) return next
    } catch {
      /* fall through */
    }
    return LIBRARY_PATH
  }

  async function signIn() {
    setBusy(true)
    setError(null)
    try {
      const issuance = await login({
        institutionId: institution.trim() || DEFAULT_INSTITUTION,
        email: email.trim(),
        password,
      })
      writeSession(sessionFrom(issuance))
      // Keep the tenant and the session in step: a signed-in page derives it from
      // the session, but the sign-in form and the studio's tenant field read this.
      writeInstitution(issuance.principal.institution_id)
      navigate(nextPath())
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  async function bootstrap() {
    const tenant = institution.trim() || DEFAULT_INSTITUTION
    const address = adminEmail.trim()
    if (!address) return
    setAdminBusy(true)
    setAdminError(null)
    setAdminCreated(null)
    try {
      const mutation = await bootstrapAdministrator(tenant, address, adminPassword)
      // Prefill the sign-in form: the next step is always to sign in as the
      // administrator that was just created, and re-typing the password is pointless.
      setEmail(mutation.account.email)
      setPassword(adminPassword)
      setAdminCreated(mutation.account.email)
      setAdminEmail('')
      setAdminPassword('')
    } catch (cause) {
      setAdminError(describeBootstrapError(cause, tenant))
    } finally {
      setAdminBusy(false)
    }
  }

  async function signOut() {
    setBusy(true)
    try {
      // Best effort: the local session is dropped whatever the server says, so a
      // token the server no longer knows cannot keep a page looking signed in.
      await logout()
    } catch {
      /* the session is cleared below regardless */
    } finally {
      clearSession()
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-academic-canvas text-slate-900 bg-academic-grid">
      <header className="sticky top-0 z-20 border-b border-slate-200/90 bg-white/95 shadow-[0_1px_3px_rgba(0,0,0,0.03)] backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-700 via-indigo-600 to-blue-600 text-white shadow-xs"
              aria-hidden="true"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M12 14l9-5-9-5-9 5 9 5z M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z"
                />
              </svg>
            </div>
            <div>
              <div className="flex items-baseline gap-2">
                <h1 className="text-base font-bold tracking-tight text-slate-900">Sign in</h1>
                <span className="text-xs font-semibold text-slate-400">·</span>
                <span className="text-xs font-medium text-slate-600">Mentora University Portal</span>
              </div>
              <span className="text-[10px] font-semibold tracking-wider text-indigo-600 uppercase">
                Academic AI Learning Platform
              </span>
            </div>
          </div>
          {session && (
            <Link
              to={LIBRARY_PATH}
              className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-700 hover:text-indigo-900 hover:underline"
            >
              Back to the library →
            </Link>
          )}
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 pt-6 pb-2 sm:px-6">
        <div className="rounded-2xl border border-indigo-100/80 bg-gradient-to-r from-indigo-900 via-indigo-800 to-slate-900 p-6 text-white shadow-sm sm:p-8">
          <div className="max-w-2xl">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-indigo-200 backdrop-blur-xs">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              University Learning & AI Teaching System
            </span>
            <h2 className="mt-3 text-2xl font-bold tracking-tight text-white sm:text-3xl">
              Welcome to Mentora
            </h2>
            <p className="mt-2 text-sm text-indigo-100/90 leading-relaxed">
              Real-time multi-modal AI lecture delivery, verified curriculum ingestion, and authoritative
              slide synchronization for higher education classrooms.
            </p>
          </div>
        </div>
      </div>

      <main className={`${PAGE_PADDING} mx-auto grid grid-cols-1 max-w-5xl gap-6 lg:grid-cols-2`}>
        <Panel title="Sign in">
          {session ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-emerald-200/90 bg-emerald-50/80 p-4">
                <p className="text-sm font-medium text-emerald-900">
                  Signed in as <strong>{describePrincipal(session)}</strong>
                </p>
                <p className="mt-1 text-xs text-emerald-700">
                  Campus / Institution:{' '}
                  <span className="font-mono font-semibold">{session.principal.institution_id}</span>
                </p>
              </div>
              <p className="text-xs text-slate-500">{describeAuthenticator(session)}</p>
              <div className="flex flex-wrap gap-2 pt-1">
                <Link to={LIBRARY_PATH} className={BUTTON_PRIMARY}>
                  Continue to Library
                </Link>
                <button
                  type="button"
                  onClick={() => void signOut()}
                  disabled={busy}
                  className={BUTTON_SECONDARY}
                >
                  Sign out
                </button>
              </div>
            </div>
          ) : (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault()
                void signIn()
              }}
            >
              <div className="rounded-xl border border-slate-200/80 bg-slate-50/80 p-3">
                <p className="text-xs font-semibold text-slate-600">Quick Demo Accounts:</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <button
                    type="button"
                    onClick={() => {
                      setEmail('teacher@school.example')
                      setPassword('dev-teacher-pass')
                    }}
                    className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-indigo-50 hover:border-indigo-300 hover:text-indigo-700"
                  >
                    Teacher
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setEmail('student7@school.example')
                      setPassword('dev-pass-7')
                    }}
                    className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-emerald-50 hover:border-emerald-300 hover:text-emerald-700"
                  >
                    Student
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setEmail('root@school.example')
                      setPassword('admin-pass-1')
                    }}
                    className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-purple-50 hover:border-purple-300 hover:text-purple-700"
                  >
                    Administrator
                  </button>
                </div>
              </div>

              <Field
                label="Institution"
                htmlFor="login-institution"
                hint="The installation the account belongs to. Every request is scoped by it."
              >
                <input
                  id="login-institution"
                  value={institution}
                  onChange={(event) => setInstitution(event.target.value)}
                  autoComplete="organization"
                  className={INPUT_CLASS}
                />
              </Field>

              <Field label="Email" htmlFor="login-email">
                <input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  autoComplete="username"
                  placeholder="name@university.edu"
                  className={INPUT_CLASS}
                />
              </Field>

              <Field
                label="Password"
                htmlFor="login-password"
                hint="An administrator sets your password when they create your account. You can change it under Settings → Security."
              >
                <input
                  id="login-password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  className={INPUT_CLASS}
                />
              </Field>

              <button
                type="submit"
                disabled={busy || !email.trim() || !password}
                className={`${BUTTON_PRIMARY} w-full`}
              >
                {busy ? 'Authenticating…' : 'Sign in'}
              </button>
              {error && <Banner tone="bad">{error}</Banner>}
            </form>
          )}
        </Panel>

        <div className="space-y-6">
          <Panel title="How sign-in works here">
            <p className="text-sm text-slate-700">
              The credential mechanism is <strong>not a decided technology</strong>. The architecture
              names institutional federation (OIDC/OAuth) and no decision accepts an implementation, so
              the platform runs a clearly labelled development mock behind a provider-neutral interface:
              a password an administrator sets, stored only as a digest. Nothing here should be read as
              the finished mechanism.
            </p>
            <p className="text-[11px] text-slate-400">
              A session is short-lived; only its SHA-256 digest is stored, and a sign-out revokes it.
            </p>
          </Panel>

          <Panel title="Every page needs a sign-in">
            <p className="text-sm text-slate-700">
              The studio, the classroom, the learning page and the student pages all require a session,
              so opening one of them without signing in brings you back here. After signing in you land
              on the page you asked for.
            </p>
            <p className="mt-2 text-[11px] text-slate-400">
              A student opens the join link their teacher gave them — signing in first if they have not
              already.
            </p>
          </Panel>

          {!session && (
            <Panel title="First administrator">
              <p className="text-sm text-slate-700">
                A new installation has no accounts yet, so there is nobody who can sign in to create
                one. The <strong>first</strong> institution administrator is created here, once, by the
                deployment — after that this institution refuses it, and{' '}
                <span className="font-medium">Admin → Accounts</span> creates teachers and students.
              </p>
              {adminCreated ? (
                <div className="mt-3 space-y-1 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
                  <p className="font-medium">{adminCreated} is now this institution's administrator.</p>
                  <p>Its email and password are filled in above. Press <strong>Sign in</strong>.</p>
                </div>
              ) : (
                <div className="mt-3 space-y-3">
                  <Field
                    label="Administrator email"
                    htmlFor="bootstrap-email"
                    hint="The address this installation's administrator signs in with."
                  >
                    <input
                      id="bootstrap-email"
                      type="email"
                      value={adminEmail}
                      onChange={(event) => setAdminEmail(event.target.value)}
                      className={INPUT_CLASS}
                    />
                  </Field>
                  <Field
                    label="Administrator password"
                    htmlFor="bootstrap-password"
                    hint={`At least ${MIN_PASSWORD_LENGTH} characters. This account's password is stored only as a digest.`}
                  >
                    <input
                      id="bootstrap-password"
                      type="password"
                      value={adminPassword}
                      onChange={(event) => setAdminPassword(event.target.value)}
                      onKeyDown={(event) => event.key === 'Enter' && void bootstrap()}
                      autoComplete="new-password"
                      className={INPUT_CLASS}
                    />
                  </Field>
                  <button
                    type="button"
                    onClick={() => void bootstrap()}
                    disabled={
                      adminBusy ||
                      !adminEmail.trim() ||
                      adminPassword.length < MIN_PASSWORD_LENGTH
                    }
                    className={`${BUTTON_SECONDARY} w-full`}
                  >
                    Create the first administrator
                  </button>
                  {adminError && <Banner tone="warn">{adminError}</Banner>}
                </div>
              )}
            </Panel>
          )}
        </div>
      </main>
    </div>
  )
}

/** A bootstrap refusal, named by its precise cause (`issue_code`). */
function describeBootstrapError(cause: unknown, institution: string): string {
  if (cause instanceof ApiError) {
    if (cause.issueCode === 'TENANT_ALREADY_PROVISIONED') {
      return `${institution} already has an administrator, so this one-shot creation is closed. Sign in with that account — its administrator can create every other account in Admin → Accounts.`
    }
    if (cause.issueCode === 'BOOTSTRAP_DISABLED') {
      return 'This deployment does not expose the first-administrator bootstrap: with institutional federation the identity provider provisions that account. Ask your operator.'
    }
    if (cause.issueCode === 'CREDENTIAL_TOO_WEAK') {
      return `Choose a password of at least ${MIN_PASSWORD_LENGTH} characters.`
    }
  }
  return describeApiError(cause)
}
