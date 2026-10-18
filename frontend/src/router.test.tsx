import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { classroomPath, Link, navigate, parseRoute, studioPath } from './router'

const ARTIFACT = '1e4c06bc-f29e-4ba4-9b39-b0b2cf5f4f1e'

describe('parseRoute', () => {
  it('maps the root to the material library', () => {
    expect(parseRoute('/')).toEqual({ name: 'library' })
    // A trailing slash is the same page.
    expect(parseRoute('/')).toEqual({ name: 'library' })
  })

  it('maps /studio/{artifactId} to the studio page', () => {
    expect(parseRoute(`/studio/${ARTIFACT}`)).toEqual({ name: 'studio', artifactId: ARTIFACT })
    // Trailing slash, query string and fragment are not part of the id.
    expect(parseRoute(`/studio/${ARTIFACT}/`)).toEqual({ name: 'studio', artifactId: ARTIFACT })
    expect(parseRoute(`/studio/${ARTIFACT}?tab=notes`)).toEqual({
      name: 'studio',
      artifactId: ARTIFACT,
    })
    expect(parseRoute(`/studio/${ARTIFACT}#top`)).toEqual({ name: 'studio', artifactId: ARTIFACT })
  })

  it('decodes an escaped artifact id', () => {
    expect(parseRoute('/studio/a%2Fb')).toEqual({ name: 'not-found', path: '/studio/a%2Fb' })
    expect(parseRoute('/studio/a%20b')).toEqual({ name: 'studio', artifactId: 'a b' })
  })

  it('falls back to not-found for anything else, including an empty studio id', () => {
    expect(parseRoute('/studio')).toEqual({ name: 'not-found', path: '/studio' })
    expect(parseRoute('/studio/')).toEqual({ name: 'not-found', path: '/studio' })
    expect(parseRoute('/studio/a/b')).toEqual({ name: 'not-found', path: '/studio/a/b' })
    expect(parseRoute('/classroom')).toEqual({ name: 'not-found', path: '/classroom' })
    expect(parseRoute('/nope')).toEqual({ name: 'not-found', path: '/nope' })
  })

  it('maps /classroom/{classId} to the classroom page', () => {
    expect(parseRoute('/classroom/class-1')).toEqual({ name: 'classroom', classId: 'class-1' })
    expect(parseRoute('/classroom/class-1/')).toEqual({ name: 'classroom', classId: 'class-1' })
    expect(parseRoute('/classroom/a/b')).toEqual({ name: 'not-found', path: '/classroom/a/b' })
  })
})

describe('studioPath', () => {
  it('builds the canonical studio URL and round-trips through parseRoute', () => {
    expect(studioPath(ARTIFACT)).toBe(`/studio/${ARTIFACT}`)
    expect(parseRoute(studioPath(ARTIFACT))).toEqual({ name: 'studio', artifactId: ARTIFACT })
  })
})

describe('classroomPath', () => {
  it('builds the canonical classroom URL and round-trips through parseRoute', () => {
    expect(classroomPath('class-1')).toBe('/classroom/class-1')
    expect(parseRoute(classroomPath('class-1'))).toEqual({ name: 'classroom', classId: 'class-1' })
  })
})

describe('navigate and Link', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/')
  })

  it('pushes a client-side location without a full page load', async () => {
    const user = userEvent.setup()
    render(<Link to={studioPath(ARTIFACT)}>Open Teacher Studio</Link>)

    await user.click(screen.getByRole('link', { name: 'Open Teacher Studio' }))

    expect(window.location.pathname).toBe(`/studio/${ARTIFACT}`)
    // The href is real, so the link works with no JS and in a new tab.
    expect(screen.getByRole('link', { name: 'Open Teacher Studio' }).getAttribute('href')).toBe(
      `/studio/${ARTIFACT}`,
    )
  })

  it('leaves a new-tab link to the browser', async () => {
    const user = userEvent.setup()
    render(
      <Link to={studioPath(ARTIFACT)} target="_blank" rel="noreferrer">
        Open in a new tab
      </Link>,
    )

    await user.click(screen.getByRole('link', { name: 'Open in a new tab' }))

    // The router did not take over: the location is untouched (jsdom does not
    // follow target=_blank, which is exactly what the real browser would do).
    expect(window.location.pathname).toBe('/')
  })

  it('does not push the same location twice', () => {
    navigate('/studio/x')
    const before = window.history.length
    navigate('/studio/x')
    expect(window.history.length).toBe(before)
  })
})
