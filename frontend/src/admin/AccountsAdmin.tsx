import { useCallback, useEffect, useState } from 'react'
import {
  ApiError,
  createAccount,
  deleteAccount,
  describeApiError,
  listAccounts,
  updateAccount,
  type Account,
  type ManagedRole,
} from '../api/client'
import {
  Badge,
  Banner,
  BUTTON_PRIMARY,
  BUTTON_SECONDARY,
  BUTTON_SMALL,
  EmptyState,
  INPUT_CLASS,
  Panel,
  Row,
} from '../components/ui'

/** The shortest password the backend will store, mirrored for a helpful hint. */
const MIN_PASSWORD_LENGTH = 8

const ROLES: { role: ManagedRole; label: string }[] = [
  { role: 'student', label: 'Students' },
  { role: 'teacher', label: 'Teachers' },
]

/**
 * The account directory — `Admin → Accounts` (V0-022, V0-023).
 *
 * An institution administrator's surface: create, read, change and remove the
 * institution's **teacher and student** accounts, and set or reset their
 * passwords. Four things are deliberate:
 *
 * * **Administrator accounts are not created here.** The first one comes from the
 *   deployment bootstrap (`/login`), and under institutional federation the identity
 *   provider owns that account. So this page cannot mint a peer, and the API refuses
 *   it too — an administrator cannot multiply itself.
 * * **A removal is guarded by usage.** An account a class references is refused
 *   (`ACCOUNT_IN_USE`) and must be **deactivated** instead, so a roster and the audit
 *   trail behind it are never orphaned. This page offers the refusal's remedy
 *   directly rather than leaving the operator to discover it.
 * * **The administrator sets the password.** Creating an account means choosing the
 *   password it signs in with; the holder can change it later under
 *   `Settings → Security`. No credential value is ever returned by the API, and no
 *   password rides in a URL — it is sent in the request body.
 * * **A reset revokes the account's sessions.** Resetting a forgotten password
 *   (`Reset password`) revokes that account's live sessions, because a reset that
 *   left other sessions working would not really have changed who can get in. The
 *   page reports how many were revoked.
 *
 * The password mechanism is the **labelled development stand-in** — no credential
 * mechanism is a decided technology yet — so the page says that instead of implying
 * the mock is the platform's authentication.
 *
 * Every verb here is advisory only in the sense that the *server* decides: the page
 * is reachable because this principal holds `account:write`, and each request
 * re-derives the caller's capabilities from its current role.
 */
export default function AccountsAdmin({ institutionId }: { institutionId: string }) {
  const [role, setRole] = useState<ManagedRole>('student')
  const [accounts, setAccounts] = useState<Account[]>([])
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [newRole, setNewRole] = useState<ManagedRole>('student')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // The account whose name is being edited, and the value in its field.
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null)
  // The account whose password is being reset, and the value in its field.
  const [resetting, setResetting] = useState<{ id: string; password: string } | null>(null)

  const refresh = useCallback(async () => {
    try {
      const loaded = await listAccounts(institutionId, role)
      setAccounts(loaded.accounts)
    } catch (cause) {
      setAccounts([])
      setError(describeApiError(cause))
    }
  }, [institutionId, role])

  // Only the fetch lives here. Outcome banners are cleared by the handlers that
  // start an action, never by this effect: creating an account can switch the
  // visible list (and so re-run this fetch) in the same turn it sets its notice,
  // and a reset here would wipe that notice before it was ever seen.
  useEffect(() => {
    void refresh()
  }, [refresh])

  async function create() {
    if (!email.trim() || password.length < MIN_PASSWORD_LENGTH) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const mutation = await createAccount(
        institutionId,
        email.trim(),
        newRole,
        password,
        displayName.trim(),
      )
      setEmail('')
      setDisplayName('')
      setPassword('')
      // Show the new role's list, so the account that was just created is visible.
      if (newRole !== role) setRole(newRole)
      else await refresh()
      setNotice(
        mutation.created
          ? `Created ${mutation.account.email} as a ${mutation.account.role}. They sign in with the password you set — hand it to them out of band, and they can change it under Settings → Security.`
          : `${mutation.account.email} already had an account here as a ${mutation.account.role}; it was linked, and its existing password was left untouched.`,
      )
    } catch (cause) {
      setError(describeCreateError(cause, email.trim()))
    } finally {
      setBusy(false)
    }
  }

  async function saveName(accountId: string) {
    if (!editing) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const mutation = await updateAccount(institutionId, accountId, {
        displayName: editing.name.trim(),
      })
      setEditing(null)
      await refresh()
      setNotice(`Renamed ${mutation.account.email}.`)
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  async function savePassword(account: Account) {
    if (!resetting || resetting.password.length < MIN_PASSWORD_LENGTH) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const mutation = await updateAccount(institutionId, account.account_id, {
        password: resetting.password,
      })
      setResetting(null)
      await refresh()
      setNotice(
        `Reset the password for ${mutation.account.email} and revoked ${mutation.sessions_revoked} ` +
          'live session(s). Their old password no longer works; hand them the new one out of band.',
      )
    } catch (cause) {
      setError(describeCreateError(cause, account.email))
    } finally {
      setBusy(false)
    }
  }

  async function switchRole(account: Account) {
    const next: ManagedRole = account.role === 'teacher' ? 'student' : 'teacher'
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const mutation = await updateAccount(institutionId, account.account_id, { role: next })
      await refresh()
      setNotice(
        `${mutation.account.email} is now a ${next}. Capabilities are re-derived on the next request, ` +
          'so a session already open can only ever lose one — the change takes full effect at their next sign-in.',
      )
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  async function setStatus(account: Account, status: 'ACTIVE' | 'DISABLED') {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const mutation = await updateAccount(institutionId, account.account_id, { status })
      await refresh()
      setNotice(
        status === 'DISABLED'
          ? `Disabled ${mutation.account.email} and revoked ${mutation.sessions_revoked} live session(s). ` +
              'They cannot sign in until they are enabled again.'
          : `Enabled ${mutation.account.email}; they can sign in again.`,
      )
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  async function remove(account: Account) {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await deleteAccount(institutionId, account.account_id)
      await refresh()
      setNotice(`Removed ${account.email}. Its credentials and sessions went with it.`)
    } catch (cause) {
      setError(describeDeleteError(cause, account))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto grid max-w-7xl grid-cols-1 gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
      <div className="space-y-6">
        <Panel title="Create an account">
          <div className="space-y-3">
            <div>
              <label htmlFor="account-email" className="block text-sm font-medium text-slate-700">
                Email address
              </label>
              <input
                id="account-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                onKeyDown={(event) => event.key === 'Enter' && void create()}
                placeholder="person@school.example"
                className={`${INPUT_CLASS} mt-1`}
              />
            </div>

            <div>
              <label htmlFor="account-name" className="block text-sm font-medium text-slate-700">
                Display name (optional)
              </label>
              <input
                id="account-name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="Ana Alvarez"
                className={`${INPUT_CLASS} mt-1`}
              />
            </div>

            <div>
              <label htmlFor="account-role" className="block text-sm font-medium text-slate-700">
                Role
              </label>
              <select
                id="account-role"
                value={newRole}
                onChange={(event) => setNewRole(event.target.value as ManagedRole)}
                className={`${INPUT_CLASS} mt-1`}
              >
                <option value="student">Student</option>
                <option value="teacher">Teacher</option>
              </select>
            </div>

            <div>
              <label htmlFor="account-password" className="block text-sm font-medium text-slate-700">
                Initial password
              </label>
              <input
                id="account-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                onKeyDown={(event) => event.key === 'Enter' && void create()}
                autoComplete="new-password"
                placeholder={`at least ${MIN_PASSWORD_LENGTH} characters`}
                className={`${INPUT_CLASS} mt-1`}
              />
              <p className="mt-1 text-[11px] text-slate-400">
                The account signs in with this. It is stored only as a digest, is sent in the request
                body (never a URL), and the holder changes it under Settings → Security.
              </p>
            </div>

            <button
              type="button"
              onClick={() => void create()}
              disabled={busy || !email.trim() || password.length < MIN_PASSWORD_LENGTH}
              className={`${BUTTON_PRIMARY} w-full`}
            >
              Create account
            </button>

            <p className="text-[11px] text-slate-400">
              Creating the same address twice links the account that exists and <strong>does not touch
              its password</strong> — a retry can never re-mint a secret. An address that already
              belongs to the other role is refused rather than silently changed.
            </p>
          </div>
        </Panel>

        <Panel title="Administrator accounts">
          <p className="text-sm text-slate-600">
            Administrators are not created here. The institution's <strong>first</strong> one is
            created by the deployment bootstrap on the{' '}
            <a href="/login" className="text-indigo-600 underline">
              sign-in page
            </a>
            , and with institutional federation the identity provider owns that account. An
            administrator therefore cannot create a peer from this page — and the API refuses it too.
          </p>
        </Panel>
      </div>

      <div className="space-y-6">
        {error && <Banner tone="bad">{error}</Banner>}
        {notice && <Banner tone="good">{notice}</Banner>}

        <Panel
          title={`${ROLES.find((item) => item.role === role)?.label ?? 'Accounts'} (${accounts.length})`}
          actions={
            <div className="flex flex-wrap gap-1">
              {ROLES.map((item) => (
                <button
                  key={item.role}
                  type="button"
                  onClick={() => {
                    setError(null)
                    setNotice(null)
                    setRole(item.role)
                  }}
                  aria-pressed={item.role === role}
                  className={
                    item.role === role
                      ? 'inline-flex min-h-11 items-center rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white lg:min-h-0 lg:px-2.5 lg:py-1 lg:text-xs'
                      : 'inline-flex min-h-11 items-center rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 lg:min-h-0 lg:px-2.5 lg:py-1 lg:text-xs'
                  }
                >
                  {item.label}
                </button>
              ))}
            </div>
          }
        >
          <ul className="space-y-2">
            {accounts.map((account) => (
              <li
                key={account.account_id}
                className="space-y-2 rounded-lg border border-slate-200 px-3 py-2"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">
                    {account.email}
                  </span>
                  <Badge tone={account.status === 'DISABLED' ? 'warn' : 'good'}>
                    {account.status === 'DISABLED' ? 'DISABLED' : 'ACTIVE'}
                  </Badge>
                  <Badge tone="info">{account.role}</Badge>
                </div>

                {editing?.id === account.account_id ? (
                  <div className="flex flex-wrap gap-2">
                    <label htmlFor={`account-name-${account.account_id}`} className="sr-only">
                      Display name
                    </label>
                    <input
                      id={`account-name-${account.account_id}`}
                      value={editing.name}
                      onChange={(event) => setEditing({ id: account.account_id, name: event.target.value })}
                      className={`${INPUT_CLASS} min-w-0 flex-1`}
                    />
                    <button
                      type="button"
                      onClick={() => void saveName(account.account_id)}
                      disabled={busy}
                      className={`${BUTTON_SMALL} shrink-0`}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditing(null)}
                      className={`${BUTTON_SMALL} shrink-0`}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <dl className="space-y-1 text-xs">
                    <Row label="Display name">{account.display_name || '—'}</Row>
                    <Row label="Account">{account.account_id}</Row>
                    <Row label="Created">{account.created_at}</Row>
                  </dl>
                )}

                {resetting?.id === account.account_id && (
                  <div className="flex flex-wrap gap-2">
                    <label htmlFor={`account-password-${account.account_id}`} className="sr-only">
                      New password
                    </label>
                    <input
                      id={`account-password-${account.account_id}`}
                      type="password"
                      value={resetting.password}
                      onChange={(event) =>
                        setResetting({ id: account.account_id, password: event.target.value })
                      }
                      onKeyDown={(event) => event.key === 'Enter' && void savePassword(account)}
                      autoComplete="new-password"
                      placeholder={`at least ${MIN_PASSWORD_LENGTH} characters`}
                      className={`${INPUT_CLASS} min-w-0 flex-1`}
                    />
                    <button
                      type="button"
                      onClick={() => void savePassword(account)}
                      disabled={busy || resetting.password.length < MIN_PASSWORD_LENGTH}
                      className={`${BUTTON_SMALL} shrink-0`}
                    >
                      Save password
                    </button>
                    <button
                      type="button"
                      onClick={() => setResetting(null)}
                      className={`${BUTTON_SMALL} shrink-0`}
                    >
                      Cancel
                    </button>
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  {editing?.id !== account.account_id && (
                    <button
                      type="button"
                      onClick={() => setEditing({ id: account.account_id, name: account.display_name })}
                      className={BUTTON_SMALL}
                    >
                      Rename
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() =>
                      setResetting({ id: account.account_id, password: '' })
                    }
                    disabled={busy}
                    className={BUTTON_SMALL}
                  >
                    Reset password
                  </button>
                  <button
                    type="button"
                    onClick={() => void switchRole(account)}
                    disabled={busy}
                    className={BUTTON_SMALL}
                  >
                    Make {account.role === 'teacher' ? 'student' : 'teacher'}
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void setStatus(account, account.status === 'DISABLED' ? 'ACTIVE' : 'DISABLED')
                    }
                    disabled={busy}
                    className={BUTTON_SMALL}
                  >
                    {account.status === 'DISABLED' ? 'Enable' : 'Disable'}
                  </button>
                  <button
                    type="button"
                    onClick={() => void remove(account)}
                    disabled={busy}
                    className={`${BUTTON_SECONDARY} lg:px-2.5 lg:py-1 lg:text-[11px]`}
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
          {accounts.length === 0 && (
            <EmptyState>
              No {ROLES.find((item) => item.role === role)?.label.toLowerCase()} in this institution
              yet.
            </EmptyState>
          )}

          <p className="text-[11px] text-slate-400">
            Disabling an account revokes its live sessions in the same call, so it takes effect on
            their next request rather than at expiry. Deleting is refused while a class references
            the account — deactivate it instead, so a roster is never left pointing at nobody.
          </p>
        </Panel>
      </div>
    </div>
  )
}

/** A create or reset refusal, named by its precise cause (`issue_code`). */
function describeCreateError(cause: unknown, email: string): string {
  if (cause instanceof ApiError) {
    if (cause.issueCode === 'CREDENTIAL_TOO_WEAK') {
      return `Choose a password of at least ${MIN_PASSWORD_LENGTH} characters.`
    }
    if (cause.issueCode === 'EMAIL_ROLE_CONFLICT') {
      return `${email} already has an account here with a different role. Change that account's role instead — creating a second account for one address would split one person in two.`
    }
    if (cause.issueCode === 'ROLE_NOT_MANAGEABLE') {
      return 'Administrator accounts are provisioned by the deployment, not created here.'
    }
  }
  return describeApiError(cause)
}

/** A removal refusal, with the remedy the guard is pointing at. */
function describeDeleteError(cause: unknown, account: Account): string {
  if (cause instanceof ApiError && cause.issueCode === 'ACCOUNT_IN_USE') {
    return `${account.email} is on a class roster, so it is deactivated rather than removed — a removal would orphan the roster and its audit history. Use Disable instead; they keep their place in the class and lose the ability to sign in.`
  }
  return describeApiError(cause)
}
