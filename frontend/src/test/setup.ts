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

afterEach(async () => {
  // The slide render is loaded asynchronously; let it settle inside act() so
  // React does not report an "update not wrapped in act" warning.
  await act(async () => {})
  cleanup()
})

