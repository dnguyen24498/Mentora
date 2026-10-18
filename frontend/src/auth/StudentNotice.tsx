import { useState } from 'react'
import { describePrincipal, useSession } from './session'
import { joinPath, loginPath, Link, navigate } from '../router'
import {
  Banner,
  BUTTON_PRIMARY,
  BUTTON_SECONDARY,
  INPUT_CLASS,
  PAGE_PADDING,
  Panel,
} from '../components/ui'
import PageHeader from '../components/PageHeader'
import { readSelectedClass } from '../institution'

/**
 * Where a student lands when they open a teacher's page — V0-021.
 *
 * The authoring pages are the teacher's, and every request a student made there
 * would answer `403 INSUFFICIENT_SCOPE`, so showing them is worse than saying so.
 * But "this page is for teachers" is only half an answer: a student signed in here
 * has to be able to *get somewhere*. So this is a real landing page, not a
 * refusal:
 *
 * * the class they were last in is offered directly (a student's browser
 *   remembers the id from the join link, the same way a teacher's remembers the
 *   last deck);
 * * they can otherwise open a class by its id — the id the teacher's join link
 *   ends in. The id is not a secret: it identifies a class, and *enrolment* is
 *   what authorizes a join, which the server checks every time. Offering the
 *   field just means a student who typed the link into the wrong browser is not
 *   stuck;
 * * it carries the shared navigation, so Settings and Sign out are reachable
 *   like they are from every other page.
 */
export default function StudentNotice() {
  const session = useSession()
  const [classId, setClassId] = useState(readSelectedClass())
  const remembered = readSelectedClass()

  function open(value: string) {
    const id = value.trim()
    if (!id) return
    // The id is a path segment, so a stray slash must not silently become a
    // second segment — the URL would then lie about what was opened.
    navigate(joinPath(id.replace(/\//g, '')))
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <PageHeader
        nav="library"
        title="Your classes"
        subtitle={describePrincipal(session)}
        classId={remembered || null}
        institution={session?.principal.institution_id ?? ''}
        onInstitutionChange={() => undefined}
        institutionEditable={false}
      />

      <main className={`mx-auto grid max-w-3xl grid-cols-1 gap-5 ${PAGE_PADDING}`}>
        <p className="text-sm text-slate-600">
          You are signed in as a student. The authoring pages (library, studio, admin) belong to
          teachers, so they are not shown here — open the class you are attending instead.
        </p>

        {remembered ? (
          <Panel title="The class you were last in">
            <p className="font-mono text-xs break-all text-slate-500">{remembered}</p>
            <div className="mt-3">
              <button type="button" onClick={() => open(remembered)} className={BUTTON_PRIMARY}>
                Open class
              </button>
            </div>
          </Panel>
        ) : (
          <Banner tone="info">
            Your teacher gives you a join link for each class; it looks like{' '}
            <span className="font-mono text-xs">…/join/&lt;class id&gt;</span>. Open it, or enter the
            class id below.
          </Banner>
        )}

        <Panel title="Open a class by id">
          <div className="flex flex-wrap gap-2">
            <input
              aria-label="Class id"
              value={classId}
              onChange={(event) => setClassId(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && open(classId)}
              placeholder="the id at the end of your join link"
              className={`${INPUT_CLASS} min-w-0`}
            />
            <button
              type="button"
              onClick={() => open(classId)}
              disabled={!classId.trim()}
              className={`${BUTTON_PRIMARY} shrink-0`}
            >
              Open
            </button>
          </div>
          <p className="text-[11px] text-slate-400">
            Knowing a class id is not permission to attend: the join is refused unless your account is
            on that class's roster.
          </p>
        </Panel>

        <div>
          <Link to={loginPath()} className={BUTTON_SECONDARY}>
            Sign in as someone else
          </Link>
        </div>
      </main>
    </div>
  )
}
