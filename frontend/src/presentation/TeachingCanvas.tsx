import { useCallback, useEffect, useRef, useState, type PointerEvent, type ReactNode } from 'react'

/**
 * The Teaching Canvas (V0 frontend).
 *
 * The product's web classroom is a slide surface plus a *teaching canvas* — the
 * dynamic surface the teacher draws on. This is the client-local core of it: a
 * transparent annotation layer over whatever it wraps (the slide), with a
 * pen/highlighter/eraser, undo and clear.
 *
 * Scope, stated plainly: the strokes live in this browser session only. They are
 * **not** sent to the Classroom Actor and **not** seen by students, because the
 * ordered per-class event stream that would carry a teaching overlay is
 * `DEC-DATA-003` (technology `OPEN`) and its live path is V1-002 — the same
 * reason the classroom shell disables its live controls. Nothing here fakes a
 * stream; it is the surface, waiting for the transport.
 *
 * It degrades instead of throwing: a browser with no 2D canvas (jsdom, a
 * locked-down webview) shows the slide and says annotation is unavailable.
 */

export type AnnotationTool = 'pen' | 'highlighter' | 'eraser'

export interface AnnotationPoint {
  x: number
  y: number
}

/** One freehand stroke. `points` are in the surface's CSS pixels, so a stroke
 *  keeps its meaning when the bitmap is scaled for a high-density screen. */
export interface AnnotationStroke {
  tool: AnnotationTool
  color: string
  width: number
  points: AnnotationPoint[]
}

export interface TeachingCanvasProps {
  /** The annotations for the current slide (controlled by the page, per slide). */
  strokes: AnnotationStroke[]
  onStrokesChange: (strokes: AnnotationStroke[]) => void
  /** The annotated surface — the rendered slide. */
  children: ReactNode
}

const COLORS = [
  { value: '#dc2626', label: 'Red' },
  { value: '#2563eb', label: 'Blue' },
  { value: '#059669', label: 'Green' },
  { value: '#0f172a', label: 'Black' },
] as const

/** The default surface size when the element has not been measured yet. */
const FALLBACK_SIZE = { width: 1280, height: 720 }

/** The bitmap is this many device pixels per CSS pixel (a phone is 2–3). */
function deviceScale(): number {
  return typeof window === 'undefined' ? 1 : window.devicePixelRatio || 1
}

interface SurfaceSize {
  width: number
  height: number
  scale: number
}

function measureSize(surface: HTMLDivElement | null): SurfaceSize {
  const scale = deviceScale()
  return {
    width: Math.round((surface?.clientWidth || FALLBACK_SIZE.width) * scale),
    height: Math.round((surface?.clientHeight || FALLBACK_SIZE.height) * scale),
    scale,
  }
}

/**
 * Put the context in the surface's CSS pixels: drawing code then thinks in the
 * units a stroke's points and width are stored in (`AnnotationPoint`), and the
 * bitmap's extra device pixels are filled in for a crisp line on a phone.
 */
function setCssUnitTransform(ctx: CanvasRenderingContext2D, scale: number): void {
  ctx.setTransform(scale, 0, 0, scale, 0, 0)
}

function get2d(canvas: HTMLCanvasElement): CanvasRenderingContext2D | null {
  // jsdom (and some webviews) have no 2D context; that is a supported state.
  try {
    return canvas.getContext('2d')
  } catch {
    return null
  }
}

function strokeWidth(tool: AnnotationTool, penWidth: number): number {
  if (tool === 'highlighter') return penWidth * 6
  if (tool === 'eraser') return penWidth * 8
  return penWidth
}

function applyStyle(ctx: CanvasRenderingContext2D, stroke: AnnotationStroke): void {
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.lineWidth = stroke.width
  ctx.globalAlpha = stroke.tool === 'highlighter' ? 0.35 : 1
  ctx.strokeStyle = stroke.color
  ctx.fillStyle = stroke.color
  // The eraser removes pixels rather than painting the slide's colour, so it
  // works over a picture as well as over a flat background.
  ctx.globalCompositeOperation = stroke.tool === 'eraser' ? 'destination-out' : 'source-over'
}

/** Draw one stroke as a polyline, or a dot when it has a single point. */
function paintStroke(ctx: CanvasRenderingContext2D, stroke: AnnotationStroke): void {
  const [first, ...rest] = stroke.points
  if (!first) return
  applyStyle(ctx, stroke)
  if (rest.length === 0) {
    ctx.beginPath()
    ctx.arc(first.x, first.y, stroke.width / 2, 0, Math.PI * 2)
    ctx.fill()
    return
  }
  ctx.beginPath()
  ctx.moveTo(first.x, first.y)
  for (const point of rest) ctx.lineTo(point.x, point.y)
  ctx.stroke()
}

/** Paint only the newest segment of the in-progress stroke (keeps drawing smooth). */
function paintSegment(ctx: CanvasRenderingContext2D, stroke: AnnotationStroke): void {
  const points = stroke.points
  if (points.length < 2) return
  applyStyle(ctx, stroke)
  const from = points[points.length - 2]
  const to = points[points.length - 1]
  ctx.beginPath()
  ctx.moveTo(from.x, from.y)
  ctx.lineTo(to.x, to.y)
  ctx.stroke()
}

export default function TeachingCanvas({ strokes, onStrokesChange, children }: TeachingCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const surfaceRef = useRef<HTMLDivElement>(null)
  const inProgress = useRef<AnnotationStroke | null>(null)

  const [drawing, setDrawing] = useState(false)
  const [tool, setTool] = useState<AnnotationTool>('pen')
  const [color, setColor] = useState<string>(COLORS[0].value)
  const [penWidth, setPenWidth] = useState(3)
  const [available, setAvailable] = useState(false)
  const [size, setSize] = useState<SurfaceSize>(() => measureSize(null))

  // Detect the 2D context and keep the bitmap the size of the visible surface
  // times the device scale, so a pointer maps straight onto canvas pixels and the
  // line is drawn at the screen's own resolution rather than upscaled.
  useEffect(() => {
    setAvailable(Boolean(canvasRef.current && get2d(canvasRef.current)))
    const surface = surfaceRef.current
    if (!surface) return
    const measure = () => setSize(measureSize(surface))
    measure()
    // A resize (a phone held the other way, a window dragged to another monitor)
    // changes the CSS size, and a zoom changes the device scale; both re-measure.
    window.addEventListener('resize', measure)
    if (typeof ResizeObserver === 'undefined') {
      return () => window.removeEventListener('resize', measure)
    }
    const observer = new ResizeObserver(measure)
    observer.observe(surface)
    return () => {
      window.removeEventListener('resize', measure)
      observer.disconnect()
    }
  }, [])

  // Repaint everything whenever the strokes, the tool or the size change.
  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas ? get2d(canvas) : null
    if (!canvas || !ctx) return
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.globalCompositeOperation = 'source-over'
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    setCssUnitTransform(ctx, size.scale)
    for (const stroke of strokes) paintStroke(ctx, stroke)
  }, [strokes, size, available])

  const toPoint = useCallback((event: PointerEvent<HTMLCanvasElement>): AnnotationPoint => {
    const canvas = event.currentTarget
    const rect = canvas.getBoundingClientRect()
    // The canvas covers the surface exactly, so this is the point in the
    // surface's CSS pixels — the units a stroke is stored in, and independent of
    // the bitmap's device scale (which only the paint transform knows about).
    return { x: event.clientX - rect.left, y: event.clientY - rect.top }
  }, [])

  const onPointerDown = useCallback(
    (event: PointerEvent<HTMLCanvasElement>) => {
      if (!drawing || !available) return
      const canvas = event.currentTarget
      const ctx = get2d(canvas)
      if (!ctx) return
      canvas.setPointerCapture?.(event.pointerId)
      inProgress.current = {
        tool,
        color,
        width: strokeWidth(tool, penWidth),
        points: [toPoint(event)],
      }
    },
    [available, color, drawing, penWidth, toPoint, tool],
  )

  const onPointerMove = useCallback(
    (event: PointerEvent<HTMLCanvasElement>) => {
      const stroke = inProgress.current
      if (!stroke) return
      const canvas = event.currentTarget
      const ctx = get2d(canvas)
      if (!ctx) return
      setCssUnitTransform(ctx, size.scale)
      stroke.points.push(toPoint(event))
      paintSegment(ctx, stroke)
    },
    [size.scale, toPoint],
  )

  const endStroke = useCallback(
    (event: PointerEvent<HTMLCanvasElement>) => {
      const stroke = inProgress.current
      inProgress.current = null
      if (!stroke) return
      const canvas = event.currentTarget
      const ctx = get2d(canvas)
      // A tap (one point) still leaves a mark.
      if (ctx && stroke.points.length === 1) {
        setCssUnitTransform(ctx, size.scale)
        paintStroke(ctx, stroke)
      }
      onStrokesChange([...strokes, stroke])
    },
    [onStrokesChange, size.scale, strokes],
  )

  const undo = useCallback(() => onStrokesChange(strokes.slice(0, -1)), [onStrokesChange, strokes])
  const clear = useCallback(() => onStrokesChange([]), [onStrokesChange])
  const hasStrokes = strokes.length > 0
  const toolsDisabled = !available || !drawing

  return (
    <div className="flex flex-col gap-2">
      <div
        role="toolbar"
        aria-label="Teaching canvas tools"
        className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-slate-200 bg-white px-3 py-2"
      >
        <button
          type="button"
          onClick={() => setDrawing((value) => !value)}
          aria-pressed={drawing}
          disabled={!available}
          className={`inline-flex min-h-11 items-center justify-center rounded-md px-3 py-2 text-sm font-semibold disabled:opacity-40 lg:min-h-0 lg:px-2.5 lg:py-1 lg:text-[11px] ${
            drawing ? 'bg-indigo-600 text-white' : 'border border-slate-300 text-slate-700 hover:bg-slate-50'
          }`}
        >
          {drawing ? 'Drawing on' : 'Draw'}
        </button>

        <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Tool">
          {(
            [
              ['pen', 'Pen'],
              ['highlighter', 'Highlighter'],
              ['eraser', 'Eraser'],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setTool(value)}
              aria-pressed={tool === value}
              disabled={toolsDisabled}
              className={`inline-flex min-h-11 items-center justify-center rounded-md px-3 py-2 text-sm font-medium disabled:opacity-40 lg:min-h-0 lg:px-2 lg:py-1 lg:text-[11px] ${
                tool === value
                  ? 'bg-slate-800 text-white'
                  : 'border border-slate-300 text-slate-700 hover:bg-slate-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Colour">
          {COLORS.map((swatch) => (
            <button
              key={swatch.value}
              type="button"
              onClick={() => setColor(swatch.value)}
              aria-label={`Colour ${swatch.label}`}
              title={swatch.label}
              aria-pressed={color === swatch.value}
              disabled={toolsDisabled}
              style={{ backgroundColor: swatch.value }}
              className={`h-9 w-9 rounded-full ring-offset-1 disabled:opacity-40 lg:h-5 lg:w-5 ${
                color === swatch.value ? 'ring-2 ring-slate-900' : ''
              }`}
            />
          ))}
        </div>

        <label className="flex items-center gap-2 text-[11px] font-medium text-slate-600">
          Width
          <input
            type="range"
            min={1}
            max={8}
            value={penWidth}
            onChange={(event) => setPenWidth(Number(event.target.value))}
            disabled={toolsDisabled}
            className="min-h-11 lg:min-h-0"
          />
        </label>

        <div className="ml-auto flex flex-wrap items-center gap-1">
          <button
            type="button"
            onClick={undo}
            disabled={!hasStrokes}
            className="inline-flex min-h-11 items-center justify-center rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40 lg:min-h-0 lg:px-2 lg:py-1 lg:text-[11px]"
          >
            Undo
          </button>
          <button
            type="button"
            onClick={clear}
            disabled={!hasStrokes}
            className="inline-flex min-h-11 items-center justify-center rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40 lg:min-h-0 lg:px-2 lg:py-1 lg:text-[11px]"
          >
            Clear
          </button>
        </div>
      </div>

      <div
        ref={surfaceRef}
        className="relative overflow-hidden rounded-xl border border-slate-200 bg-white"
      >
        {children}
        <canvas
          ref={canvasRef}
          data-testid="teaching-canvas"
          role="img"
          aria-label="Teaching canvas — annotations drawn over the slide"
          width={size.width}
          height={size.height}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endStroke}
          onPointerCancel={endStroke}
          className="absolute inset-0 h-full w-full"
          style={{
            pointerEvents: drawing && available ? 'auto' : 'none',
            touchAction: drawing ? 'none' : 'auto',
            cursor: drawing ? 'crosshair' : 'default',
          }}
        />
      </div>

      {!available && (
        <p data-testid="canvas-unavailable" role="status" className="text-[11px] text-slate-500">
          Annotation is unavailable in this browser (no 2D canvas). The slide is shown unannotated.
        </p>
      )}
    </div>
  )
}
