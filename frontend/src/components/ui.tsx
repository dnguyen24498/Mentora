import type { ReactNode } from 'react'

/**
 * Small shared presentational primitives for the admin and settings pages.
 *
 * They are deliberately plain — a card, a badge, a banner, a labelled field —
 * because those pages repeat the same few shapes several times. They add no
 * behaviour, so a page's logic stays in the page.
 */

/**
 * The tokens that make the same UI work on a phone and on the projector-sized
 * screen this app was first built for.
 *
 * The app was written for a large screen — a classroom display or a laptop in
 * the Teacher Studio — and everything below states the **touch** size first and
 * the original dense size from `lg` (≥1024px) up, because Tailwind is
 * mobile-first and the large-screen look is the one that must not move.
 *
 * `lg` is not an arbitrary choice: it is already this app's "big screen"
 * breakpoint (every two-column page switches at `lg`, the shared bar returns to
 * one row at `lg`). Below it we assume a finger, above it a mouse. That matters
 * for the one rule here that is a bug rather than a taste:
 *
 * * a form control is 16px below `lg`, because iOS Safari zooms the whole page
 *   when a focused control's text is smaller — 16px is the threshold, and a
 *   phone in landscape and a tablet are both below `lg`;
 * * a control is at least 44px tall below `lg` (the tap-target guidance);
 * * page and card padding is tighter on a phone, so a card is not mostly margin.
 *
 * They are plain strings so a page can compose them, the same way the codebase
 * already composed `INPUT_CLASS`.
 */

/** At least 44px of tap area on a touch screen; the compact height from `lg` up. */
export const TOUCH_TARGET = 'min-h-11 lg:min-h-0'

/** A page's main padding: narrow on a phone, roomier from `sm` up. */
export const PAGE_PADDING = 'px-4 py-4 sm:px-6 sm:py-6'

/** A card's padding. */
export const PANEL_PADDING = 'p-4 sm:p-5'

/** A form control: 16px on a touch screen (no iOS zoom), denser from `lg` up. */
export const INPUT_CLASS =
  'w-full rounded-xl border border-slate-300/85 bg-white px-3.5 py-2.5 text-base text-slate-800 shadow-2xs transition placeholder:text-slate-400 focus:border-indigo-600 focus:ring-2 focus:ring-indigo-500/20 focus:outline-none lg:text-sm'

/** The same control for a page header or a filter row: it fills a phone's row. */
export const INPUT_CHROME_CLASS =
  'min-w-0 flex-1 rounded-lg border border-slate-300/85 bg-white px-3 py-2 text-base text-slate-800 shadow-2xs transition focus:border-indigo-600 focus:ring-2 focus:ring-indigo-500/20 focus:outline-none lg:w-44 lg:flex-none lg:px-2.5 lg:py-1.5 lg:text-xs'

/** A page's or a form's main action. */
export const BUTTON_PRIMARY = `inline-flex items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-600 to-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-xs hover:from-indigo-500 hover:to-blue-500 hover:shadow active:scale-[0.99] transition-all disabled:opacity-40 disabled:pointer-events-none lg:py-2 ${TOUCH_TARGET}`

/** A secondary action beside the main one. */
export const BUTTON_SECONDARY = `inline-flex items-center justify-center gap-1.5 rounded-xl border border-slate-300/90 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-2xs hover:bg-slate-50 hover:border-slate-400/80 hover:text-slate-900 active:scale-[0.99] transition-all disabled:opacity-40 disabled:pointer-events-none lg:py-2 ${TOUCH_TARGET}`

/** An in-place action: a header action, a table row, a toolbar. */
export const BUTTON_SMALL = `inline-flex items-center justify-center gap-1 rounded-lg border border-slate-300/90 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-2xs hover:bg-slate-50 hover:text-slate-900 active:scale-[0.99] transition-all disabled:opacity-40 disabled:pointer-events-none lg:px-2.5 lg:py-1 lg:text-[11px] ${TOUCH_TARGET}`

/** A section tab (Admin/Settings): a chip that scrolls sideways on a phone. */
export const TAB_CLASS = `inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-3.5 py-2 text-sm font-medium transition-all duration-150 lg:px-3 lg:py-1.5 lg:text-xs ${TOUCH_TARGET}`

export type Tone = 'neutral' | 'good' | 'warn' | 'bad' | 'info'

const TONE_STYLE: Record<Tone, string> = {
  neutral: 'border border-slate-200/90 bg-slate-100 text-slate-700',
  good: 'border border-emerald-200/90 bg-emerald-50 text-emerald-800',
  warn: 'border border-amber-200/90 bg-amber-50 text-amber-800',
  bad: 'border border-rose-200/90 bg-rose-50 text-rose-800',
  info: 'border border-indigo-200/90 bg-indigo-50 text-indigo-800',
}

const TONE_DOT: Record<Tone, string> = {
  neutral: 'bg-slate-400',
  good: 'bg-emerald-500',
  warn: 'bg-amber-500',
  bad: 'bg-rose-500',
  info: 'bg-indigo-500',
}

/** A coloured status pill with subtle indicator dot. */
export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: Tone }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide ${TONE_STYLE[tone]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${TONE_DOT[tone]}`} aria-hidden="true" />
      {children}
    </span>
  )
}

/** A titled university academic card. */
export function Panel({
  title,
  actions,
  children,
  className = '',
}: {
  title?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={`space-y-3.5 self-start rounded-2xl border border-slate-200/85 bg-white p-4 sm:p-5 shadow-[0_1px_3px_rgba(0,0,0,0.03),0_4px_12px_rgba(0,0,0,0.02)] transition-shadow hover:shadow-[0_4px_16px_-2px_rgba(0,0,0,0.05)] ${className}`}
    >
      {(title || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1.5 border-b border-slate-100 pb-2.5">
          {title && (
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600">
              {title}
            </h2>
          )}
          {actions && <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

/** An inline message. `bad` is an alert, everything else a status. */
export function Banner({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  const style =
    tone === 'bad'
      ? 'border-rose-200 bg-rose-50/90 text-rose-800'
      : tone === 'warn'
        ? 'border-amber-200 bg-amber-50/90 text-amber-800'
        : tone === 'good'
          ? 'border-emerald-200 bg-emerald-50/90 text-emerald-800'
          : 'border-slate-200 bg-slate-50/90 text-slate-700'
  return (
    <p
      role={tone === 'bad' ? 'alert' : 'status'}
      className={`flex items-start gap-2 rounded-xl border px-3.5 py-2.5 text-sm shadow-2xs ${style}`}
    >
      <span className="min-w-0 flex-1">{children}</span>
    </p>
  )
}

/** A quiet "nothing here yet" line. */
export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="text-sm text-slate-400">{children}</p>
}

/** A labelled form control. */
export function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string
  htmlFor: string
  hint?: ReactNode
  children: ReactNode
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <div className="mt-1">{children}</div>
      {hint && <p className="mt-1 text-[11px] text-slate-400">{hint}</p>}
    </div>
  )
}

/** One `key: value` row for a definition list. Stacks on a phone, where a long
 * value would otherwise be crushed into a few characters beside its label. */
export function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:justify-between sm:gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="min-w-0 truncate font-mono text-xs sm:text-right">{children}</dd>
    </div>
  )
}

