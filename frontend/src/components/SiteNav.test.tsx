import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import SiteNav from './SiteNav'
import { writeSelectedArtifact, writeSelectedClass } from '../institution'
import { ARTIFACT } from '../test/fixtures'

/**
 * The shared nav is the answer to "get from any page to any other page". The two
 * scoped pages (Studio/Learn need a deck, Classroom needs a class) are only
 * links once there is an id to link to; before that they say why they are not.
 */
describe('SiteNav', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('always links the library, and explains the pages that need a deck or class', () => {
    render(<SiteNav current="library" />)

    expect(screen.getByRole('link', { name: 'Library' }).getAttribute('href')).toBe('/')

    for (const label of ['Studio', 'Classroom', 'Learn']) {
      // Not a link yet: a nav entry that goes nowhere would be a trap.
      expect(screen.queryByRole('link', { name: label })).toBeNull()
      expect(screen.getByText(label).getAttribute('aria-disabled')).toBe('true')
    }
  })

  it('links every page from the remembered deck and class', () => {
    writeSelectedArtifact(ARTIFACT)
    writeSelectedClass('class-1')

    render(<SiteNav current="library" />)

    expect(screen.getByRole('link', { name: 'Studio' }).getAttribute('href')).toBe(
      `/studio/${ARTIFACT}`,
    )
    expect(screen.getByRole('link', { name: 'Classroom' }).getAttribute('href')).toBe(
      '/classroom/class-1',
    )
    expect(screen.getByRole('link', { name: 'Learn' }).getAttribute('href')).toBe(
      `/learn/${ARTIFACT}`,
    )
  })

  it('links the sectioned areas even with no deck or class', () => {
    render(<SiteNav current="library" />)

    expect(screen.getByRole('link', { name: 'Admin' }).getAttribute('href')).toBe('/admin')
    expect(screen.getByRole('link', { name: 'Settings' }).getAttribute('href')).toBe('/settings')
  })

  it('marks the sectioned areas as current where they are the page', () => {
    render(<SiteNav current="admin" />)
    expect(screen.getByRole('link', { name: 'Admin' }).getAttribute('aria-current')).toBe('page')
    expect(screen.getByRole('link', { name: 'Settings' }).getAttribute('aria-current')).toBeNull()
  })

  it('marks the current page and prefers the id the page itself holds', () => {
    writeSelectedArtifact('a-deck-opened-earlier')

    render(<SiteNav current="studio" artifactId={ARTIFACT} />)

    const studio = screen.getByRole('link', { name: 'Studio' })
    expect(studio.getAttribute('href')).toBe(`/studio/${ARTIFACT}`)
    expect(studio.getAttribute('aria-current')).toBe('page')
    expect(screen.getByRole('link', { name: 'Library' }).getAttribute('aria-current')).toBeNull()
  })
})
