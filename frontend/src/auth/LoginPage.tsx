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
import { resetDevelopmentMode } from './mode'
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

/**
 * Sign in — `/login` (V0-021), and the institution's first administrator (V0-022).
 *
 * The form is the whole credential exchange: an institution (the tenant the
 * account lives in), an address and an opaque *sign-in code*. The code is
 * deliberately not called a password: no password mechanism is a decided
 * technology. The canonical architecture names **institutional federation**
 * (OIDC/OAuth), and no ADR accepts an implementation, so the adapter behind this
 * form is a labelled development mock — and the page says so rather than
 * presenting it as the platform's authentication.
 *
 * A student is given a code when an administrator creates their account
 * (`Admin → Accounts`), so this page is also where a student starts: sign in, then
 * open the class's join page.
 *
 * Three roles sign in through this one form — an institution administrator, a
 * teacher and a student — because who you are is the account's role, not a choice on
 * this page. The **first** administrator is the one thing that cannot be signed into
 * into existence: a fresh installation has no accounts at all, so the deployment
 * bootstrap creates that account here, once, while the development shortcut is on.
 * After that the tenant refuses it, and `Admin → Accounts` creates everyone else.
 *
 * What this page must never do is imply that signing in is required for the rest
 * of the app. The backend accepts an `X-Institution-Id` header as a *development*
 * shortcut (while `MENTORA_DEV_TENANT_HEADER` is on), which resolves a teacher
 * with no account. That is what the "Continue without signing in" button is, and
 * the page names it as development mode, not as a user.
 */
export default function LoginPage() {
  const session = useSession()
  const [institution, setInstitution] = useInstitution()
  const [email, setEmail] = useState('')
  const [credential, setCredential] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The first-administrator bootstrap. Kept beside the sign-in form rather than on
  // its own page, because creating that account is a *precondition* for signing in
  // as anyone who can administer anything.
  const [adminEmail, setAdminEmail] = useState('')
  const [adminBusy, setAdminBusy] = useState(false)
  const [adminError, setAdminError] = useState<string | null>(null)
  const [adminCode, setAdminCode] = useState<{ email: string; credential: string } | null>(null)

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
        credential,
      })
      writeSession(sessionFrom(issuance))
      // A session is not the development shortcut, so the cached answer to
      // "which mode is this browser in" is now stale.
      resetDevelopmentMode()
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
    try {
      const mutation = await bootstrapAdministrator(tenant, address)
      const code = mutation.development_credential
      if (code) {
        // Prefill the sign-in form: the next step is always to sign in as the
        // administrator that was just created, and re-typing the code is pointless.
        setEmail(mutation.account.email)
        setCredential(code)
        setAdminCode({ email: mutation.account.email, credential: code })
        setAdminEmail('')
      } else {
        setAdminError(
          `${mutation.account.email} already exists in ${tenant}, so nothing new was created. Sign in with its existing code.`,
        )
      }
    } catch (cause) {
      setAdminCode(null)
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
      resetDevelopmentMode()
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 sm:px-4 lg:py-3">
          <h1 className="text-base font-semibold text-slate-800">Sign in</h1>
          <span className="text-sm text-slate-500">Mentora</span>
          <Link
            to={LIBRARY_PATH}
            className="text-sm font-medium text-indigo-700 hover:underline lg:ml-auto"
          >
            Back to the library
          </Link>
        </div>
      </header>

      <main className={`${PAGE_PADDING} mx-auto grid grid-cols-1 max-w-3xl gap-6 lg:grid-cols-2`}>
        <Panel title="Sign in">
          {session ? (
            <div className="space-y-3">
              <p className="text-sm text-slate-700">
                Signed in as <strong>{describePrincipal(session)}</strong> in{' '}
                <span className="font-mono text-xs">{session.principal.institution_id}</span>.
              </p>
              <p className="text-[11px] text-slate-400">{describeAuthenticator(session)}</p>
              <div className="flex flex-wrap gap-2">
                <Link to={LIBRARY_PATH} className={BUTTON_SECONDARY}>
                  Continue
                </Link>
                <button type="button" onClick={() => void signOut()} disabled={busy} className={BUTTON_SECONDARY}>
                  Sign out
                </button>
              </div>
            </div>
          ) : (
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault()
                void signIn()
              }}
            >
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
                  className={INPUT_CLASS}
                />
              </Field>

              <Field
                label="Sign-in code"
                htmlFor="login-credential"
                hint="An administrator gives you one when they create your account."
              >
                <input
                  id="login-credential"
                  type="password"
                  value={credential}
                  onChange={(event) => setCredential(event.target.value)}
                  autoComplete="current-password"
                  className={INPUT_CLASS}
                />
              </Field>

              <button
                type="submit"
                disabled={busy || !email.trim() || !credential}
                className={`${BUTTON_PRIMARY} w-full`}
              >
                Sign in
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
              the platform runs a clearly labelled development mock behind a provider-neutral interface.
              Nothing here should be read as the finished mechanism.
            </p>
            <p className="text-[11px] text-slate-400">
              A session is short-lived; only its SHA-256 digest is stored, and a sign-out revokes it.
            </p>
          </Panel>

          <Panel title="Without signing in">
            <p className="text-sm text-slate-700">
              The API also accepts an <span className="font-mono text-xs">X-Institution-Id</span> header
              as a development shortcut, which resolves a <em>teacher</em> with no account behind it. It
              keeps the authoring flows usable before federation exists.
            </p>
            <p className="mt-2 text-sm text-slate-700">
              It is <strong>not</strong> a sign-in. It is a teacher, and joining a class is the
              student's own action — so it cannot join one, and students always sign in.
            </p>
            <div className="mt-3">
              <Link to={LIBRARY_PATH} className={BUTTON_SECONDARY}>
                Continue in development mode
              </Link>
            </div>
            <p className="mt-2 text-[11px] text-slate-400">
              A student opens the join link their teacher gave them, or signs in above and then opens it.
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
              {adminCode ? (
                <div className="mt-3 space-y-1 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                  <p className="font-medium">
                    The administrator {adminCode.email} exists. Its sign-in code is filled in above.
                  </p>
                  <p className="font-mono text-sm break-all">{adminCode.credential}</p>
                  <p className="text-[11px]">
                    Shown once and stored only as a digest. Press <strong>Sign in</strong>.
                  </p>
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
                      onKeyDown={(event) => event.key === 'Enter' && void bootstrap()}
                      className={INPUT_CLASS}
                    />
                  </Field>
                  <button
                    type="button"
                    onClick={() => void bootstrap()}
                    disabled={adminBusy || !adminEmail.trim()}
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
  }
  return describeApiError(cause)
}
