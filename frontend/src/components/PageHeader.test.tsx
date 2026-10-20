import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PageHeader from './PageHeader'
import { ARTIFACT } from '../test/fixtures'
import { clearSession, writeSession } from '../auth/session'

/**
 * The shared app bar.
 *
 * jsdom has no layout, so a test cannot prove that a phone gets a stacked bar —
 * that is Tailwind's job. What it can pin is the contract the five pages rely on:
 * one `h1` per page, the shared nav marked current, the tenant field bound to the
 * page's own state (never a private copy), and the page's own action and section
 * tabs slotting into the bar.
 *
 * The bar embeds the shared nav, whose entries are chosen by capability, so these
 * tests sign a teacher in (V0-023): no session is no capabilities.
 */
describe('PageHeader', () => {
  beforeEach(() => {
    localStorage.clear()
    clearSession()
    writeSession({
      token: 'tok-1',
      principal: {
        authenticated: true,
        institution_id: 'university-001',
        role: 'teacher',
        scopes: [
          'account:read',
          'class:read',
          'class:write',
          'content:read',
          'content:write',
          'enrollment:write',
          'publication:write',
          'review:write',
          'scene:read',
        ],
        account_id: 'account-teacher',
        email: 'teacher@school.example',
        display_name: 'Tess Teacher',
        session_id: 'session-1',
      },
      authenticator: {
        id: 'local-credentials@1.0.0',
        name: 'local-credentials',
        version: '1.0.0',
        kind: 'DEVELOPMENT_MOCK',
      },
      notice: 'mock',
      expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
    })
  })

  it('renders the page name, its qualifier and a current nav entry', () => {
    render(
      <PageHeader
        nav="studio"
        title="Teacher Studio"
        subtitle="deck.pptx"
        meta={ARTIFACT}
        artifactId={ARTIFACT}
        institution="university-001"
        onInstitutionChange={() => {}}
      />,
    )

    expect(screen.getByRole('heading', { level: 1, name: 'Teacher Studio' })).toBeTruthy()
    expect(screen.getByText('deck.pptx')).toBeTruthy()
    expect(screen.getByText(ARTIFACT)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Studio' }).getAttribute('aria-current')).toBe('page')
  })

  it('reports a tenant change to the page instead of holding its own', () => {
    const onInstitutionChange = vi.fn()
    render(
      <PageHeader
        nav="settings"
        title="Settings"
        institution="university-001"
        onInstitutionChange={onInstitutionChange}
      />,
    )

    const field = screen.getByLabelText('Institution')
    expect((field as HTMLInputElement).value).toBe('university-001')

    fireEvent.change(field, { target: { value: 'college-9' } })

    expect(onInstitutionChange).toHaveBeenCalledWith('college-9')
  })

  it('gives a page its own header action and second row', () => {
    render(
      <PageHeader
        nav="admin"
        title="Admin"
        institution="university-001"
        onInstitutionChange={() => {}}
        actions={<button type="button">Rebuild package</button>}
      >
        <nav aria-label="Admin sections">
          <a href="/admin/classes" aria-current="page">
            Classes
          </a>
        </nav>
      </PageHeader>,
    )

    expect(screen.getByRole('button', { name: 'Rebuild package' })).toBeTruthy()
    expect(screen.getByRole('navigation', { name: 'Admin sections' })).toBeTruthy()
  })
})
