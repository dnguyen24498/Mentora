import { useState } from 'react'
import {
  readClassroomPreferences,
  updateClassroomPreferences,
} from '../classroom/state/store'
import { Banner, Panel, Row } from '../components/ui'

/**
 * Accessibility settings.
 *
 * These are the **classroom's** own preferences (reduced motion, high contrast),
 * read and written through the classroom store so there is exactly one copy: the
 * settings page is a second way to change them, not a second place they live. A
 * preference set here applies to the classroom the moment it is opened.
 */
export default function AccessibilitySettings() {
  const [preferences, setPreferences] = useState(readClassroomPreferences)

  function update(patch: Partial<typeof preferences>) {
    setPreferences(updateClassroomPreferences(patch))
  }

  return (
    <div className="mx-auto grid grid-cols-1 max-w-5xl gap-6 lg:grid-cols-2">
      <Panel title="Motion">
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={preferences.reducedMotion}
            onChange={(event) => update({ reducedMotion: event.target.checked })}
            className="mt-1"
          />
          <span>
            <span className="block text-sm font-medium text-slate-700">Reduce motion</span>
            <span className="block text-xs text-slate-500">
              Removes transitions and animated progress in the classroom client.
            </span>
          </span>
        </label>
      </Panel>

      <Panel title="Contrast">
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={preferences.highContrast}
            onChange={(event) => update({ highContrast: event.target.checked })}
            className="mt-1"
          />
          <span>
            <span className="block text-sm font-medium text-slate-700">High contrast</span>
            <span className="block text-xs text-slate-500">
              Strengthens borders and text contrast in the classroom client.
            </span>
          </span>
        </label>
      </Panel>

      <Panel title="Where these apply" className="lg:col-span-2">
        <Banner tone="info">
          These are the classroom's stored preferences — changing them here is the same change the
          classroom's own controls make, and the classroom picks them up on its next render.
        </Banner>
        <dl className="space-y-1 text-sm">
          <Row label="Reduced motion">{preferences.reducedMotion ? 'on' : 'off'}</Row>
          <Row label="High contrast">{preferences.highContrast ? 'on' : 'off'}</Row>
          <Row label="Stored in">this browser only</Row>
        </dl>
      </Panel>
    </div>
  )
}
