import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import TeachingCanvas from './TeachingCanvas'

/**
 * The teaching canvas on a phone.
 *
 * Two things matter on a handset that do not on a laptop: the strokes must be
 * drawn at the screen's own density (a phone reports a device pixel ratio of 2
 * or 3, and a bitmap sized to CSS pixels is visibly soft), and the surface must
 * survive a browser with no 2D context instead of throwing.
 *
 * jsdom has no layout, so the surface measures 0 and the canvas falls back to
 * its nominal 1280×720 — which is exactly what makes the device scale assertable.
 */

const FALLBACK_WIDTH = 1280
const FALLBACK_HEIGHT = 720

function stubDevicePixelRatio(value: number) {
  Object.defineProperty(window, 'devicePixelRatio', {
    value,
    configurable: true,
    writable: true,
  })
}

describe('TeachingCanvas', () => {
  const original = window.devicePixelRatio

  afterEach(() => {
    stubDevicePixelRatio(original)
  })

  it('draws the bitmap at the device scale so a phone gets a sharp line', () => {
    stubDevicePixelRatio(3)

    render(
      <TeachingCanvas strokes={[]} onStrokesChange={() => {}}>
        <div />
      </TeachingCanvas>,
    )

    const canvas = screen.getByTestId('teaching-canvas') as HTMLCanvasElement
    expect(canvas.width).toBe(FALLBACK_WIDTH * 3)
    expect(canvas.height).toBe(FALLBACK_HEIGHT * 3)
  })

  it('stays 1:1 where the device scale is 1', () => {
    stubDevicePixelRatio(1)

    render(
      <TeachingCanvas strokes={[]} onStrokesChange={() => {}}>
        <div />
      </TeachingCanvas>,
    )

    const canvas = screen.getByTestId('teaching-canvas') as HTMLCanvasElement
    expect(canvas.width).toBe(FALLBACK_WIDTH)
    expect(canvas.height).toBe(FALLBACK_HEIGHT)
  })

  it('still shows the surface where a 2D context is unavailable', () => {
    render(
      <TeachingCanvas strokes={[]} onStrokesChange={() => {}}>
        <p>the slide</p>
      </TeachingCanvas>,
    )

    expect(screen.getByText('the slide')).toBeTruthy()
    expect(screen.getByTestId('canvas-unavailable')).toBeTruthy()
    // Nothing can be drawn, so no tool claims to be usable.
    expect((screen.getByRole('button', { name: 'Draw' }) as HTMLButtonElement).disabled).toBe(true)
  })
})
