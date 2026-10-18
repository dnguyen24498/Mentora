import type { ReactNode } from 'react'

/**
 * Small shared presentational primitives for the admin and settings pages.
 *
 * They are deliberately plain — a card, a badge, a banner, a labelled field —
 * because those pages repeat the same few shapes several times. They add no
 * behaviour, so a page's logic stays in the page.
 */

export type Tone = 'neutral' | 'good' | 'warn' | 'bad' | 'info'

const TONE_STYLE: Record<Tone, string> = {
  neutral: 'bg-slate-100 text-slate-600',
  good: 'bg-emerald-100 text-emerald-700',
  warn: 'bg-amber-100 text-amber-700',
  bad: 'bg-rose-100 text-rose-700',
  info: 'bg-indigo-100 text-indigo-700',
}

/** A coloured status pill. */
export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: Tone }) {
  return (
    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${TONE_STYLE[tone]}`}>
      {children}
    </span>
  )
}

/** A titled card. */
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
    <section className={`space-y-3 self-start rounded-xl border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
      {(title || actions) && (
        <div className="flex flex-wrap items-center gap-2">
          {title && (
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
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
      ? 'border-rose-200 bg-rose-50 text-rose-800'
      : tone === 'warn'
        ? 'border-amber-300 bg-amber-50 text-amber-800'
        : tone === 'good'
          ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
          : 'border-slate-200 bg-slate-50 text-slate-600'
  return (
    <p
      role={tone === 'bad' ? 'alert' : 'status'}
      className={`rounded-lg border px-3 py-2 text-sm ${style}`}
    >
      {children}
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

/** One `key: value` row for a definition list. */
export function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="shrink-0 text-slate-500">{label}</dt>
      <dd className="truncate text-right font-mono text-xs">{children}</dd>
    </div>
  )
}

export const INPUT_CLASS =
  'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none'
export const BUTTON_PRIMARY =
  'rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40'
export const BUTTON_SECONDARY =
  'rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40'
