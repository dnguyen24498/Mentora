import { describe, expect, it } from 'vitest'

/**
 * Every grid container declares its own columns.
 *
 * `display: grid` with no `grid-template-columns` gets one **implicit** track,
 * and an implicit track is `auto` — whose minimum is the content's *min-content*
 * width. So one long, unbreakable value (the deck
 * `updated_B_o_c_o_T_ng_k_t_C_ng_t_c_…`, a SHA-256, a class id) becomes the
 * minimum width of that grid, and the grid — and with it the whole page — grows
 * wider than the phone instead of the value ellipsising. That is exactly how the
 * library page came to be 666px wide inside a 390px viewport: `<main>` declared
 * columns only from `md` up, so below `md` it was a bare grid floored at the
 * filename's own width.
 *
 * Tailwind's `grid-cols-N` is `repeat(N, minmax(0, 1fr))`, whose floor is 0, so
 * declaring the columns at the base breakpoint is the fix. A declaration that
 * only exists behind a variant (`md:grid-cols-2`) does not count — that is the
 * bug, not the fix.
 *
 * This is a source scan rather than a rendered assertion because jsdom has no
 * layout engine, so a component test cannot measure the symptom. The real
 * verification is a browser at 320px; see "Checking it" in `frontend/README.md`.
 */
const BARE_GRID = /(?<![\w-])grid(?![\w-])/
/** A column/row template at the base breakpoint — no `variant:` prefix. */
const BASE_TEMPLATE = /(?:^|[\s"'`{])(?:grid-cols|grid-rows)-/

// Vite inlines the sources as text, so this needs no Node typings and stays
// inside the `src` tree the app already compiles.
const SOURCES: Record<string, string> = {
  ...import.meta.glob('./**/*.tsx', { query: '?raw', import: 'default', eager: true }),
  ...import.meta.glob('./**/*.ts', { query: '?raw', import: 'default', eager: true }),
}

const scanned = Object.entries(SOURCES).filter(
  ([path]) => !path.includes('.test.') && !path.includes('/test/') && !path.endsWith('.d.ts'),
)

describe('responsive layout invariants', () => {
  it('has sources to scan', () => {
    // Guard against the glob silently matching nothing.
    expect(scanned.length).toBeGreaterThan(20)
  })

  it('never relies on an implicit grid track', () => {
    const offenders: string[] = []
    let containers = 0

    for (const [path, source] of scanned) {
      const lines = source.split('\n')
      lines.forEach((line, index) => {
        if (!line.includes('className') || !BARE_GRID.test(line)) return
        containers += 1
        // The class string may be a template literal spanning a few lines.
        const window = lines.slice(index, index + 4).join('\n')
        if (!BASE_TEMPLATE.test(window)) {
          offenders.push(`${path.replace('./', 'src/')}:${index + 1}  ${line.trim()}`)
        }
      })
    }

    // Guard against the scan silently matching nothing.
    expect(containers).toBeGreaterThan(15)
    expect(offenders).toEqual([])
  })
})
