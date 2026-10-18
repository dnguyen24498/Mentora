import { afterEach } from 'vitest'
import { act, cleanup } from '@testing-library/react'

// jsdom implements neither object URLs nor (usefully) fetch. A component test
// must never reach the network, and the object-URL cleanup path must not throw.
if (typeof URL.createObjectURL !== 'function') {
  URL.createObjectURL = () => 'blob:test'
}
if (typeof URL.revokeObjectURL !== 'function') {
  URL.revokeObjectURL = () => {}
}

globalThis.fetch = (() => {
  throw new Error('component tests must not call fetch')
}) as unknown as typeof fetch

// jsdom has no 2D canvas. The teaching canvas is built to degrade when
// `getContext` yields no context, so declare that here — otherwise jsdom logs a
// "Not implemented" error on every probe (a test-environment detail, not a bug).
if (typeof HTMLCanvasElement !== 'undefined') {
  HTMLCanvasElement.prototype.getContext = function getContext() {
    return null
  } as unknown as HTMLCanvasElement['getContext']
}

afterEach(async () => {
  // The slide render is loaded asynchronously; let it settle inside act() so
  // React does not report an "update not wrapped in act" warning.
  await act(async () => {})
  cleanup()
})

