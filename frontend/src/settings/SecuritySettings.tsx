import { useState } from 'react'
import { changePassword, describeApiError } from '../api/client'
import { describeAuthenticator, describePrincipal, useSession } from '../auth/session'
import { Banner, BUTTON_PRIMARY, Field, INPUT_CLASS, Panel, Row } from '../components/ui'

/** The shortest password the backend will store, mirrored for a helpful hint. */
const MIN_PASSWORD_LENGTH = 8

/**
 * Security settings — your own password (V0-023).
 *
 * This is **self-service**, not the directory: it changes the password of the
 * account that is signed in, and it verifies the current one exactly as a sign-in
 * does. So it is not a weaker second path to an account — the check is the same
 * credential check. A wrong current password is refused and the session stays
 * valid, because a mistyped field is not a sign-out.
 *
 * On success the server revokes the account's **other** live sessions, so a
 * password change really does change who can get in; the tab that asked is kept so
 * the person is not thrown out of the page they are on. Resetting *someone else's*
 * password is an administrator action and lives in `Admin → Accounts`.
 *
 * The mechanism is the labelled development stand-in: no credential mechanism is a
 * decided technology, so the page says so rather than implying this is the
 * platform's authentication.
 */
export default function SecuritySettings() {
  const session = useSession()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const tooShort = next.length > 0 && next.length < MIN_PASSWORD_LENGTH
  const mismatch = confirm.length > 0 && next !== confirm
  const canSubmit =
    !busy && current.length > 0 && next.length >= MIN_PASSWORD_LENGTH && next === confirm

  async function submit() {
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const result = await changePassword(current, next)
      setCurrent('')
      setNext('')
      setConfirm('')
      setNotice(
        result.sessions_revoked > 0
          ? `Password changed. ${result.sessions_revoked} other live session(s) were revoked, so the old password cannot keep another tab or device working. You stay signed in here.`
          : 'Password changed. You stay signed in here.',
      )
    } catch (cause) {
      setError(describeChangeError(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto grid grid-cols-1 max-w-5xl gap-6 lg:grid-cols-2">
      <Panel title="Change your password">
        {!session ? (
          <Banner tone="warn">
            You are not signed in, so there is no password to change. Sign in first.
          </Banner>
        ) : (
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault()
              void submit()
            }}
          >
            <p className="text-sm text-slate-700">
              Signed in as <strong>{describePrincipal(session)}</strong>.
            </p>

            <Field
              label="Current password"
              htmlFor="password-current"
              hint="Verified exactly as a sign-in is. A wrong one is refused and does not sign you out."
            >
              <input
                id="password-current"
                type="password"
                value={current}
                onChange={(event) => setCurrent(event.target.value)}
                autoComplete="current-password"
                className={INPUT_CLASS}
              />
            </Field>

            <Field
              label="New password"
              htmlFor="password-new"
              hint={`At least ${MIN_PASSWORD_LENGTH} characters. Changing it revokes your other live sessions.`}
            >
              <input
                id="password-new"
                type="password"
                value={next}
                onChange={(event) => setNext(event.target.value)}
                autoComplete="new-password"
                className={INPUT_CLASS}
              />
            </Field>

            <Field label="Confirm new password" htmlFor="password-confirm">
              <input
                id="password-confirm"
                type="password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                autoComplete="new-password"
                className={INPUT_CLASS}
              />
            </Field>

            <button type="submit" disabled={!canSubmit} className={`${BUTTON_PRIMARY} w-full sm:w-auto`}>
              Change password
            </button>

            {tooShort && <Banner tone="warn">The new password is shorter than {MIN_PASSWORD_LENGTH} characters.</Banner>}
            {mismatch && <Banner tone="warn">The new password and its confirmation do not match.</Banner>}
            {error && <Banner tone="bad">{error}</Banner>}
            {notice && <Banner tone="good">{notice}</Banner>}
          </form>
        )}
      </Panel>

      <Panel title="How sign-in works here">
        <p className="text-sm text-slate-700">
          The credential mechanism is <strong>not a decided technology</strong>. The architecture
          names institutional federation (OIDC/OAuth) and no decision accepts an implementation, so
          the platform runs a clearly labelled development mock behind a provider-neutral interface: a
          password an administrator sets, stored only as a digest. Nothing here should be read as the
          finished mechanism.
        </p>
        <dl className="mt-3 space-y-1 text-sm">
          <Row label="Authenticator">{session?.authenticator.id ?? '—'}</Row>
          <Row label="Capability kind">{session?.authenticator.kind ?? '—'}</Row>
          <Row label="Written to the server">a new password digest; nothing else</Row>
          <Row label="Revokes other sessions">
            yes — a change really changes who can get in
          </Row>
        </dl>
        {session && <p className="mt-3 text-[11px] text-slate-400">{describeAuthenticator(session)}</p>}
      </Panel>
    </div>
  )
}

/** A change refusal, named by its precise cause. */
function describeChangeError(cause: unknown): string {
  const described = describeApiError(cause)
  if (described.includes('INVALID_CREDENTIALS')) {
    return `${described} — check the current password and try again. You are still signed in.`
  }
  if (described.includes('CREDENTIAL_TOO_WEAK')) {
    return `Choose a password of at least ${MIN_PASSWORD_LENGTH} characters.`
  }
  return described
}
