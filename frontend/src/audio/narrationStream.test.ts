import { describe, expect, it } from 'vitest'
import { audioBlob, readNarrationEvents, type NarrationAudio } from './narrationStream'

function streamOf(parts: string[]): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const part of parts) controller.enqueue(encoder.encode(part))
      controller.close()
    },
  })
  return new Response(body)
}

describe('readNarrationEvents', () => {
  it('reassembles lines split across network chunks and skips malformed ones', async () => {
    const response = streamOf([
      '{"type":"narration.st',
      'arted","sequence":1}\nnot json\n{"type":"audio","seq',
      'uence":2}\n{"type":"narration.completed","sequence":3}',
    ])
    const types: string[] = []
    for await (const event of readNarrationEvents(response)) types.push(event.type)
    expect(types).toEqual(['narration.started', 'audio', 'narration.completed'])
  })

  it('decodes an audio segment to a typed blob', async () => {
    const blob = audioBlob({ data: btoa('RIFF'), content_type: 'audio/wav' } as NarrationAudio)
    expect(blob.type).toBe('audio/wav')
    expect(blob.size).toBe(4)
  })
})
