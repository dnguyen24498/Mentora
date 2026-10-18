import { Link, learnPath } from '../router'
import { readSelectedArtifact } from '../institution'
import { TEACHING_WPM_MAX, TEACHING_WPM_MIN, useSettings } from './store'
import { Banner, Panel, Row } from '../components/ui'

/**
 * Teaching settings: how the automatic, **text-only** teaching behaves.
 *
 * What this feature is: the learning page reads the deck's authored teaching
 * script — the teacher's newest draft revision, else the package's lesson script,
 * else the slide's speaker notes, else the slide text — and plays it as a timed
 * narration, advancing slides and showing a transcript. What it is not: there is no
 * model generating teaching text (no LLM provider exists in this codebase, and the
 * decision ledger does not name one) and there is no audio. The voice capability is
 * the provider-neutral speech domain from V0-012, whose technology decision
 * (`DEC-TECH-007`) is still `OPEN`; this version never asks it for sound, so the
 * text path is all that runs.
 */
export default function TeachingSettings() {
  const [settings, updateSettings] = useSettings()
  const artifact = readSelectedArtifact()

  return (
    <div className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-2">
      <Panel title="Narration pacing">
        <label htmlFor="teaching-wpm" className="block text-sm font-medium text-slate-700">
          {settings.teachingWpm} words per minute
        </label>
        <input
          id="teaching-wpm"
          type="range"
          min={TEACHING_WPM_MIN}
          max={TEACHING_WPM_MAX}
          step={10}
          value={settings.teachingWpm}
          onChange={(event) => updateSettings({ teachingWpm: Number(event.target.value) })}
          className="mt-2 w-full"
        />
        <p className="mt-1 text-[11px] text-slate-400">
          Each slide stays on screen for the time its narration would take at this pace (between 2.5
          and 30 seconds), so longer passages get longer.
        </p>
      </Panel>

      <Panel title="Playback">
        <div className="space-y-3">
          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              checked={settings.teachingAutoplay}
              onChange={(event) => updateSettings({ teachingAutoplay: event.target.checked })}
              className="mt-1"
            />
            <span>
              <span className="block text-sm font-medium text-slate-700">
                Start narrating when a deck opens
              </span>
              <span className="block text-xs text-slate-500">
                Otherwise the learning page waits for Play.
              </span>
            </span>
          </label>

          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              checked={settings.teachingCaptions}
              onChange={(event) => updateSettings({ teachingCaptions: event.target.checked })}
              className="mt-1"
            />
            <span>
              <span className="block text-sm font-medium text-slate-700">Show the caption line</span>
              <span className="block text-xs text-slate-500">
                The narration is always in the transcript panel; this adds the single-line caption
                under the slide.
              </span>
            </span>
          </label>

          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              checked={settings.autoStartDueClasses}
              onChange={(event) => updateSettings({ autoStartDueClasses: event.target.checked })}
              className="mt-1"
            />
            <span>
              <span className="block text-sm font-medium text-slate-700">
                Start a scheduled class when its time arrives
              </span>
              <span className="block text-xs text-slate-500">
                Only while the Classes page is open — the server records{' '}
                <span className="font-mono">scheduled_for</span> but never acts on it, because a
                durable scheduler is <span className="font-mono">DEC-TECH-003</span>, still OPEN.
                Nothing runs with the page closed.
              </span>
            </span>
          </label>
        </div>
      </Panel>

      <Panel title="What runs" className="lg:col-span-2">
        <Banner tone="info">
          <strong>Text only.</strong> This version generates no sound: narration is text, shown as a
          caption and collected in a transcript. The speech domain is provider-neutral and its voice
          provider decision (<span className="font-mono">DEC-TECH-007</span>) is still
          <span className="font-mono"> OPEN</span>, so audio stays on the text fallback path.
        </Banner>

        <dl className="space-y-1 text-sm">
          <Row label="Narration source">the deck's authored script (no model)</Row>
          <Row label="Fallback order">
            draft revision → lesson script → speaker notes → slide text
          </Row>
          <Row label="Transport">client-side; no per-class event stream yet (DEC-DATA-003 OPEN)</Row>
          <Row label="Teaching at a time">the learning page waits on its own clock, while it is open</Row>
          <Row label="Starting a class on time">
            the Classes page, while it is open; the server has no scheduler (DEC-TECH-003 OPEN)
          </Row>
          <Row label="Written to the server">nothing</Row>
        </dl>

        <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
          {artifact ? (
            <Link
              to={learnPath(artifact)}
              className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white"
            >
              Open the last deck and teach it
            </Link>
          ) : (
            <p className="text-xs text-slate-400">
              Open a deck in the library to try the automatic teaching.
            </p>
          )}
        </div>
      </Panel>
    </div>
  )
}
