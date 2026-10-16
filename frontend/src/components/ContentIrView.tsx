import { useMemo, useState } from 'react'
import type { ContentIR, ShapeObject, SlideScene } from '../api/client'

const KIND_STYLE: Record<string, string> = {
  text: 'bg-sky-100 text-sky-700',
  shape: 'bg-slate-100 text-slate-600',
  picture: 'bg-emerald-100 text-emerald-700',
  table: 'bg-amber-100 text-amber-700',
  chart: 'bg-rose-100 text-rose-700',
  connector: 'bg-slate-100 text-slate-600',
  group: 'bg-violet-100 text-violet-700',
}

/** EMU -> cm, for human-readable bounds (914400 EMU = 1 inch = 2.54 cm). */
function cm(emu: number | null): string {
  return emu === null ? '?' : (emu / 360000).toFixed(1)
}

function boundsLabel(object: ShapeObject): string {
  const b = object.bounds
  if (!b || (b.width === null && b.height === null)) return ''
  return `${cm(b.width)}×${cm(b.height)} cm @ (${cm(b.x)}, ${cm(b.y)})`
}

function KindBadge({ kind }: { kind: string }) {
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
        KIND_STYLE[kind] ?? 'bg-slate-100 text-slate-600'
      }`}
    >
      {kind}
    </span>
  )
}

function TableView({ rows }: { rows: string[][] }) {
  return (
    <div className="mt-1.5 overflow-x-auto">
      <table className="border-collapse text-xs">
        <tbody>
          {rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, c) => (
                <td key={c} className="border border-slate-200 px-2 py-1 align-top text-slate-700">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ObjectRow({ object }: { object: ShapeObject }) {
  const label = boundsLabel(object)
  return (
    <li
      className="rounded-lg border border-slate-200 bg-white p-2"
      style={{ marginLeft: Math.min(object.depth, 6) * 16 }}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <KindBadge kind={object.kind} />
        <span className="text-xs font-medium text-slate-700">{object.name || '(unnamed)'}</span>
        {object.placeholder && (
          <span className="rounded bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-500">
            ph:{object.placeholder}
          </span>
        )}
        <span className="ml-auto font-mono text-[10px] text-slate-400" title={object.source_id}>
          {label}
        </span>
      </div>

      {object.media_ref && (
        <p className="mt-1 font-mono text-[11px] text-emerald-700">{object.media_ref}</p>
      )}

      {object.paragraphs.length > 0 && (
        <ul className="mt-1.5 space-y-0.5">
          {object.paragraphs.map((paragraph, index) => (
            <li
              key={index}
              className="whitespace-pre-wrap text-sm leading-snug text-slate-800"
              style={{ paddingLeft: paragraph.level * 14 }}
            >
              {paragraph.level > 0 && <span className="text-slate-300">· </span>}
              {paragraph.text}
            </li>
          ))}
        </ul>
      )}

      {object.table && <TableView rows={object.table} />}
    </li>
  )
}

function SlideCard({
  slide,
  open,
  onToggle,
}: {
  slide: SlideScene
  open: boolean
  onToggle: () => void
}) {
  const stats = useMemo(() => {
    const paragraphs = slide.objects.reduce((total, o) => total + o.paragraphs.length, 0)
    return {
      paragraphs,
      tables: slide.objects.filter((o) => o.table).length,
      pictures: slide.objects.filter((o) => o.kind === 'picture').length,
      groups: slide.objects.filter((o) => o.kind === 'group').length,
    }
  }, [slide])

  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-slate-50"
      >
        <span className={`text-slate-400 transition-transform ${open ? 'rotate-90' : ''}`}>▶</span>
        <span className="text-sm font-semibold text-slate-800">Slide {slide.order + 1}</span>
        <span className="text-[11px] text-slate-400">
          {slide.objects.length} objects · {stats.paragraphs} texts · {stats.tables} tables ·{' '}
          {stats.pictures} images{stats.groups > 0 ? ` · ${stats.groups} groups` : ''}
        </span>
        {slide.notes && (
          <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-medium text-indigo-600">
            notes
          </span>
        )}
        {slide.warnings.length > 0 && (
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
            {slide.warnings.length} warning(s)
          </span>
        )}
      </button>

      {open && (
        <div className="space-y-2 border-t border-slate-100 bg-slate-50/60 p-3">
          {slide.notes && (
            <p className="rounded-lg bg-indigo-50 p-2 text-sm whitespace-pre-line text-indigo-900">
              <span className="font-semibold">Notes: </span>
              {slide.notes}
            </p>
          )}
          {slide.warnings.map((warning, index) => (
            <p key={index} className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800">
              {warning}
            </p>
          ))}
          {slide.objects.length === 0 ? (
            <p className="text-xs text-slate-400">No objects on this slide.</p>
          ) : (
            <ul className="space-y-1.5">
              {slide.objects.map((object, index) => (
                <ObjectRow key={`${object.source_id}-${index}`} object={object} />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

export default function ContentIrView({ document }: { document: ContentIR }) {
  const [openSlides, setOpenSlides] = useState<Set<number>>(() => new Set([0]))
  const [showRaw, setShowRaw] = useState(false)

  const totals = useMemo(() => {
    const objects = document.slides.flatMap((s) => s.objects)
    return {
      objects: objects.length,
      paragraphs: objects.reduce((total, o) => total + o.paragraphs.length, 0),
      tables: objects.filter((o) => o.table).length,
      pictures: objects.filter((o) => o.kind === 'picture').length,
    }
  }, [document])

  function toggle(order: number) {
    setOpenSlides((previous) => {
      const next = new Set(previous)
      if (next.has(order)) next.delete(order)
      else next.add(order)
      return next
    })
  }

  function download() {
    const blob = new Blob([JSON.stringify(document, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = window.document.createElement('a')
    anchor.href = url
    anchor.download = `content-ir-${document.slides.length}slides.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-slate-200 bg-white p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Extracted content
          </span>
          <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">
            {document.schema_version}
          </span>
          <div className="ml-auto flex gap-1.5">
            <button
              type="button"
              onClick={() => setOpenSlides(new Set(document.slides.map((s) => s.order)))}
              className="rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
            >
              Expand all
            </button>
            <button
              type="button"
              onClick={() => setOpenSlides(new Set())}
              className="rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
            >
              Collapse all
            </button>
            <button
              type="button"
              onClick={() => setShowRaw((value) => !value)}
              className="rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
            >
              {showRaw ? 'Hide' : 'Show'} raw JSON
            </button>
            <button
              type="button"
              onClick={download}
              className="rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
            >
              Download JSON
            </button>
          </div>
        </div>
        <p className="mt-2 text-[11px] text-slate-500">
          {document.slide_count} slides · {totals.objects} objects · {totals.paragraphs} text
          paragraphs · {totals.tables} tables · {totals.pictures} images
        </p>
        {document.warnings.length > 0 && (
          <p className="mt-1 text-[11px] text-amber-700">{document.warnings.join('; ')}</p>
        )}
      </div>

      {showRaw && (
        <pre className="max-h-96 overflow-auto rounded-xl border border-slate-200 bg-slate-900 p-3 text-[11px] leading-tight text-slate-100">
          {JSON.stringify(document, null, 2)}
        </pre>
      )}

      <div className="space-y-2">
        {document.slides.map((slide) => (
          <SlideCard
            key={slide.scene_id}
            slide={slide}
            open={openSlides.has(slide.order)}
            onToggle={() => toggle(slide.order)}
          />
        ))}
      </div>
    </div>
  )
}
