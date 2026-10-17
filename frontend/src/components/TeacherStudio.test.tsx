import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import TeacherStudio, { type TeacherStudioProps } from './TeacherStudio'
import type {
  ReviewDecision,
  ReviewDraft,
  ReviewDraftSection,
  ReviewPackage,
  ReviewScene,
  ReviewSection,
  ReviewState,
} from '../api/client'

const INSTITUTION = 'university-001'
const ARTIFACT = 'artifact-1'

function scene(order: number, overrides: Partial<ReviewScene> = {}): ReviewScene {
  const sceneId = `ppt/slides/slide${order + 1}.xml`
  return {
    order,
    scene_id: sceneId,
    fidelity: 'STRUCTURAL_RENDERED',
    render_status: 'RENDERED',
    fallback_asset: `assets/${order}.svg`,
    render_url: `/artifacts/${ARTIFACT}/review-package/renders/${order}`,
    requires_review: false,
    missing_fonts: [],
    warnings: [],
    notes: `Notes for slide ${order + 1}`,
    text: [`Slide ${order + 1} body`],
    object_count: 1,
    step_count: 1,
    renderer: null,
    source_ref: {},
    ...overrides,
  }
}

function section(order: number, sectionId: string, sceneId: string, script: string | null): ReviewSection {
  return {
    order,
    section_id: sectionId,
    type: 'EXPLANATION',
    scene_id: sceneId,
    scene_step_id: `${sceneId}#step-0`,
    safe_markers: [`${sceneId}#step-0`],
    script,
    scene_fidelity: 'THEMED_RENDERED',
    requires_review: false,
  }
}

function makePackage(overrides: Partial<ReviewPackage> = {}): ReviewPackage {
  return {
    artifact_id: ARTIFACT,
    package_id: 'pkg-abc',
    prefix: 'packages/pkg-abc',
    course_id: 'course-1',
    course_version: '3',
    content_package_version: 'cpv-abc',
    lesson_plan_version: 'lp-abc',
    knowledge_index_version: 'unindexed',
    teaching_graph_version: null,
    created_at: '2026-10-16T09:00:00Z',
    state: 'READY',
    publishable: true,
    requires_review: false,
    scene_count: 2,
    file_count: 5,
    renderer: {
      name: 'local-structural-svg',
      version: '3.1.0',
      engine: 'stdlib-svg',
      config_hash: 'hash',
      data_region: 'local',
    },
    placeholder_notice:
      "Each slide keeps the deck's own layout and styling — this is not a native PowerPoint render. Where a component cannot be reproduced (an unavailable source font, a chart/SmartArt, a picture that cannot be embedded) it is drawn in the Mentora theme's look, in its original place, and listed as a warning. A production renderer technology is still an open decision (DEC-TECH-005).",
    lesson_order: [
      section(0, 'sec-1', 'ppt/slides/slide1.xml', 'Explain slide 1'),
      section(1, 'sec-2', 'ppt/slides/slide2.xml', null),
    ],
    scenes: [scene(0), scene(1)],
    ...overrides,
  }
}

function makeState(overrides: Partial<ReviewState> = {}): ReviewState {
  return {
    artifact_id: ARTIFACT,
    version_id: 'version-1',
    version_status: 'DRAFT',
    package_id: 'pkg-abc',
    content_package_version: 'cpv-abc',
    state: 'READY',
    publishable: true,
    requires_review: false,
    stale: false,
    blocking_scene_orders: [],
    decision: null,
    draft: null,
    draft_count: 0,
    ...overrides,
  }
}

function draftSection(order: number, sectionId: string, sceneId: string, script: string | null): ReviewDraftSection {
  return {
    order,
    section_id: sectionId,
    type: 'EXPLANATION',
    scene_id: sceneId,
    scene_step_id: `${sceneId}#step-0`,
    safe_markers: [`${sceneId}#step-0`],
    script,
  }
}

function makeDraft(overrides: Partial<ReviewDraft> = {}): ReviewDraft {
  return {
    draft_id: 'draft-1',
    artifact_id: ARTIFACT,
    version_id: 'version-1',
    package_id: 'pkg-abc',
    content_package_version: 'cpv-abc',
    lesson_plan_version: 'lp-abc',
    revision: 2,
    edited_by: 'dr-nguyen',
    created_at: '2026-10-16T10:00:00Z',
    sections: [
      draftSection(0, 'sec-2', 'ppt/slides/slide2.xml', 'Rewritten for slide 2'),
      draftSection(1, 'sec-1', 'ppt/slides/slide1.xml', null),
    ],
    ...overrides,
  }
}

function makeDecision(overrides: Partial<ReviewDecision> = {}): ReviewDecision {
  return {
    decision_id: 'decision-1',
    artifact_id: ARTIFACT,
    version_id: 'version-1',
    package_id: 'pkg-abc',
    content_package_version: 'cpv-abc',
    decision: 'APPROVE',
    reason: null,
    reviewer: 'dr-nguyen',
    created_at: '2026-10-16T10:05:00Z',
    ...overrides,
  }
}

async function setup(props: Partial<TeacherStudioProps> = {}) {
  const onDecide = vi.fn()
  const onSaveDraft = vi.fn()
  const loadRender = vi.fn(async () => 'blob:slide')
  const view = render(
    <TeacherStudio
      institutionId={INSTITUTION}
      review={makePackage()}
      reviewState={makeState()}
      onDecide={onDecide}
      onSaveDraft={onSaveDraft}
      loadRender={loadRender}
      {...props}
    />,
  )
  // The slide render is fetched asynchronously; settle it inside act() so no
  // test observes an update that React flags as outside act().
  await act(async () => {})
  return { onDecide, onSaveDraft, loadRender, ...view }
}

describe('TeacherStudio — side-by-side review', async () => {
  it('shows the rendered scene next to the extracted information', async () => {
    await setup()

    const sideBySide = screen.getByTestId('scene-side-by-side')
    expect(await within(sideBySide).findByAltText(/Fallback render of slide 1/)).toBeTruthy()
    expect(within(sideBySide).getByText('Slide 1 body')).toBeTruthy()
    expect(within(sideBySide).getByText('Notes for slide 1')).toBeTruthy()
    expect(within(sideBySide).getByRole('heading', { name: /extracted text/i })).toBeTruthy()
    expect(within(sideBySide).getByRole('heading', { name: /speaker notes/i })).toBeTruthy()
    expect(within(sideBySide).getByRole('heading', { name: /warnings/i })).toBeTruthy()
  })

  it('says how the slides were rendered, and never implies a native render', async () => {
    await setup()
    expect(screen.getByText(/keeps the deck's own layout/)).toBeTruthy()
    expect(screen.getByText(/not a native PowerPoint render/)).toBeTruthy()
    expect(screen.getByText(/DEC-TECH-005/)).toBeTruthy()
  })
})

describe('TeacherStudio — blocking status', async () => {
  const blockedReview = makePackage({
    state: 'BLOCKED',
    publishable: false,
    requires_review: true,
    scene_count: 1,
    scenes: [
      scene(0, {
        render_status: 'FAILED',
        fidelity: null,
        fallback_asset: null,
        render_url: null,
        requires_review: true,
      }),
    ],
    lesson_order: [section(0, 'sec-1', 'ppt/slides/slide1.xml', null)],
  })

  it('refuses to offer approval of a blocking failure', async () => {
    await setup({
      review: blockedReview,
      reviewState: makeState({ state: 'BLOCKED', publishable: false, blocking_scene_orders: [0] }),
    })

    const alert = screen.getByRole('alert')
    expect(alert.textContent).toMatch(/cannot be approved/i)

    const approve = screen.getByRole('button', { name: 'Approve' }) as HTMLButtonElement
    expect(approve.disabled).toBe(true)
    // The reason is programmatically associated, not only visual.
    expect(approve.getAttribute('aria-describedby')).toBe('approve-blocked-reason')
    expect(document.getElementById('approve-blocked-reason')).toBe(alert)
  })

  it('allows approval when nothing blocks it', async () => {
    await setup()
    const approve = screen.getByRole('button', { name: 'Approve' }) as HTMLButtonElement
    expect(approve.disabled).toBe(false)
    expect(approve.getAttribute('aria-describedby')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

describe('TeacherStudio — review decision', async () => {
  it('records an approval, with the optional reviewer attribution', async () => {
    const user = userEvent.setup()
    const { onDecide } = await setup()

    await user.type(screen.getByLabelText(/reviewer/i), 'Dr Nguyen')
    await user.click(screen.getByRole('button', { name: 'Approve' }))

    expect(onDecide).toHaveBeenCalledWith({ decision: 'APPROVE', reviewer: 'Dr Nguyen' })
  })

  it('requires a reason before recording a rejection', async () => {
    const user = userEvent.setup()
    const { onDecide } = await setup()

    await user.click(screen.getByRole('button', { name: 'Reject' }))
    expect(onDecide).not.toHaveBeenCalled()
    expect(screen.getByText(/must record a reason/i)).toBeTruthy()

    await user.type(screen.getByLabelText(/rejection reason/i), 'Slide 2 contradicts slide 1')
    await user.click(screen.getByRole('button', { name: 'Reject' }))

    expect(onDecide).toHaveBeenCalledWith({
      decision: 'REJECT',
      reason: 'Slide 2 contradicts slide 1',
      reviewer: undefined,
    })
  })

  it('surfaces a stale decision so it cannot be read as a current approval', async () => {
    await setup({
      reviewState: makeState({
        decision: makeDecision({ content_package_version: 'cpv-older' }),
        stale: true,
        version_status: 'APPROVED',
      }),
    })

    expect(screen.getByTestId('current-decision').textContent).toBe('Approved')
    expect(screen.getByText(/stale — the stored content changed/)).toBeTruthy()
  })

  it('shows the version status and reports the package version under review', async () => {
    await setup({ reviewState: makeState({ version_status: 'APPROVED', decision: makeDecision() }) })
    expect(screen.getByText('version APPROVED')).toBeTruthy()
    expect(screen.getAllByText('cpv-abc').length).toBeGreaterThan(0)
  })
})

describe('TeacherStudio — lesson-order edits', async () => {
  it('enters the lesson order as a draft, not as a package change', async () => {
    await setup()
    const order = screen.getByTestId('lesson-order')
    expect(order.tagName).toBe('OL')
    expect(within(order).getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText(/the built package is never modified/i)).toBeTruthy()
    expect(screen.getByText(/No draft yet/)).toBeTruthy()
  })

  it('reorders with the keyboard and saves a draft revision', async () => {
    const user = userEvent.setup()
    const { onSaveDraft } = await setup()

    const moveDown = screen.getByRole('button', { name: 'Move section 1 (explanation) down' })
    moveDown.focus()
    await user.keyboard('{Enter}')

    // The reorder is announced for assistive technology.
    expect(screen.getByText(/Moved section 1 \(explanation\) to position 2 of 2/)).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Save draft' }))
    expect(onSaveDraft).toHaveBeenCalledTimes(1)
    const [sections] = onSaveDraft.mock.calls[0] as [{ section_id: string; script: string }[]]
    expect(sections.map((item) => item.section_id)).toEqual(['sec-2', 'sec-1'])
  })

  it('does not offer to save an unedited draft', async () => {
    const user = userEvent.setup()
    const { onSaveDraft } = await setup()

    const save = screen.getByRole('button', { name: 'Save draft' }) as HTMLButtonElement
    expect(save.disabled).toBe(true)
    await user.click(save)
    expect(onSaveDraft).not.toHaveBeenCalled()
  })

  it('edits a script and sends it with the draft', async () => {
    const user = userEvent.setup()
    const { onSaveDraft } = await setup()

    const script = screen.getByLabelText('Script for section 2')
    await user.type(script, 'Walk through the worked example')
    await user.click(screen.getByRole('button', { name: 'Save draft' }))

    const [sections] = onSaveDraft.mock.calls[0] as [{ section_id: string; script: string }[]]
    expect(sections[1]).toEqual({ section_id: 'sec-2', script: 'Walk through the worked example' })
  })

  it('discards local changes back to the saved revision', async () => {
    const user = userEvent.setup()
    await setup()

    await user.click(screen.getByRole('button', { name: 'Move section 1 (explanation) down' }))
    expect((screen.getByRole('button', { name: 'Save draft' }) as HTMLButtonElement).disabled).toBe(false)

    await user.click(screen.getByRole('button', { name: 'Discard local changes' }))
    expect((screen.getByRole('button', { name: 'Save draft' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('starts from the newest draft revision and states the package is unchanged', async () => {
    await setup({ reviewState: makeState({ draft: makeDraft(), draft_count: 2 }) })

    expect((screen.getByLabelText('Script for section 1') as HTMLTextAreaElement).value).toBe(
      'Rewritten for slide 2',
    )
    expect(screen.getByText(/Revision 2 of 2 saved/)).toBeTruthy()
    expect(screen.getByText(/The built package is unchanged/)).toBeTruthy()
    expect(screen.getByText(/draft rev 2/)).toBeTruthy()
  })
})

describe('TeacherStudio — large-screen focus', async () => {
  it('gives the slide the full width and takes the editor out of the reading order', async () => {
    const user = userEvent.setup()
    await setup()

    // Default: the editor and the slide sit side by side.
    expect(screen.getByRole('heading', { name: 'Lesson order' })).toBeTruthy()
    const toggle = screen.getByRole('button', { name: 'Focus slide' })
    expect(toggle.getAttribute('aria-pressed')).toBe('false')

    await user.click(toggle)

    const back = screen.getByRole('button', { name: 'Show lesson order' })
    expect(back.getAttribute('aria-pressed')).toBe('true')
    // The editor is gone from the accessibility tree, so the slide is the content.
    expect(screen.queryByRole('heading', { name: 'Lesson order' })).toBeNull()
    expect(screen.getByRole('region', { name: 'Slide review' })).toBeTruthy()
  })

  it('keeps unsaved edits through a focus toggle', async () => {
    const user = userEvent.setup()
    await setup()

    await user.click(screen.getByRole('button', { name: 'Move section 1 (explanation) down' }))
    await user.click(screen.getByRole('button', { name: 'Focus slide' }))
    await user.click(screen.getByRole('button', { name: 'Show lesson order' }))

    const items = within(screen.getByTestId('lesson-order')).getAllByRole('listitem')
    expect(items[0].textContent).toContain('slide2.xml')
    expect((screen.getByRole('button', { name: 'Save draft' }) as HTMLButtonElement).disabled).toBe(false)
  })
})

describe('TeacherStudio — keyboard and screen-reader basics', async () => {
  it('names every control and groups the lesson order as a list', async () => {
    await setup()

    expect(screen.getByRole('heading', { name: /Teacher Studio/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /1\. explanation/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Move section 2 (explanation) up' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Move section 1 (explanation) down' })).toBeTruthy()
    expect(screen.getByLabelText('Script for section 1')).toBeTruthy()
    expect(screen.getByLabelText(/reviewer/i)).toBeTruthy()
    // First and last positions cannot move past the ends.
    expect((screen.getByRole('button', { name: 'Move section 1 (explanation) up' }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: 'Move section 2 (explanation) down' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('moves between slides with the arrow keys', async () => {
    const user = userEvent.setup()
    await setup()

    screen.getByRole('region', { name: 'Slide review' }).focus()
    await user.keyboard('{ArrowRight}')

    expect(await screen.findByAltText(/Fallback render of slide 2/)).toBeTruthy()
    expect(screen.getByText('Slide 2 body')).toBeTruthy()
  })

  it('does not hijack the arrow keys while a script is being edited', async () => {
    const user = userEvent.setup()
    await setup()

    const script = screen.getByLabelText('Script for section 1')
    script.focus()
    await user.keyboard('{ArrowRight}')

    // Still on slide 1, and the textarea kept focus.
    expect(screen.getByAltText(/Fallback render of slide 1/)).toBeTruthy()
    expect(document.activeElement).toBe(script)
  })
})
