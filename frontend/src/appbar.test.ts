import { describe, expect, it } from 'vitest'

/**
 * One app bar on every page.
 *
 * The navigation chips used to sit in each page's own header, and every page
 * solved the same bar slightly differently — the library centred its header in a
 * `max-w-7xl` column while the other pages ran full width, so clicking **Library**
 * visibly shifted the whole navigation. `PageHeader` is the single bar now; this
 * scan protects that, because jsdom has no layout engine and cannot measure the
 * jump itself. The check that counts is still a browser at a narrow and a wide
 * viewport (`frontend/README.md`, "Checking it").
 */
const SOURCES: Record<string, string> = {
  ...import.meta.glob('./**/*.tsx', { query: '?raw', import: 'default', eager: true }),
  ...import.meta.glob('./**/*.ts', { query: '?raw', import: 'default', eager: true }),
}

const scanned = Object.entries(SOURCES).filter(
  ([path]) => !path.includes('.test.') && !path.includes('/test/') && !path.endsWith('.d.ts'),
)

describe('shared app bar invariant', () => {
  it('has sources to scan', () => {
    expect(scanned.length).toBeGreaterThan(20)
  })

  it('mounts the shared navigation from one component only', () => {
    const mounts = scanned
      .filter(([, source]) => /<SiteNav\b/.test(source))
      .map(([path]) => path.replace('./', 'src/'))
      .sort()

    expect(mounts).toEqual(['src/components/PageHeader.tsx'])
  })

  it('gives every signed-in page the same header instead of growing its own', () => {
    const headers = scanned
      .filter(([, source]) => /<header\b/.test(source))
      .map(([path]) => path.replace('./', 'src/'))
      .sort()

    // `PageHeader` owns the bar. The sign-in page is the one public route: it has
    // no signed-in navigation entries to share, and its minimal header is
    // deliberately outside the app shell (`V0-023`).
    expect(headers).toEqual(['src/auth/LoginPage.tsx', 'src/components/PageHeader.tsx'])
  })
})
