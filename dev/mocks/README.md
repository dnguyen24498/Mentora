# Local-stack mocks

`dev/README.md`: *"Local stack MUST include durable database, Redis-compatible
cache, ordered-stream mock/emulator, object storage, search mock, mock identity,
mock STT/TTS/LLM/SFU, and contract validation."*

## `tts_mock.py` (V0-012)

The mock TTS for the local stack. It is **not** a second implementation: it drives
the same deterministic neutral-voice adapter the backend ships
(`app/providers/deterministic.py`) through the domain service
(`app/speech/service.py`), so the dev stack, the tests and the application all speak
through one code path and produce byte-identical audio.

Why it exists: `DEC-TECH-007` ("TTS/OmniVoice deployment and GPU capacity") is
`OPEN`, and `docs/adr/proposed/ADR-P007_TTS_OMNIVOICE.md` says *"until accepted,
provider-neutral interfaces and mocks are used."* This is that mock, made runnable.

```bash
# from the repo root; stdlib-only, no install needed
python3 dev/mocks/tts_mock.py --text "Hello class, welcome to the lesson." \
    --marker 0:start --marker 12:welcome --out /tmp/tts.wav
```

It prints the outcome the classroom would observe — status, characters, chunk
count, duration, realized markers — as JSON, and (with `--out`) writes the
utterance as a 16-bit mono WAV. Each streamed chunk is a headerless PCM frame;
concatenating them in order and writing the WAV header once reconstructs the audio,
which is exactly what `--out` does.

Nothing here is a decided provider: no network, no credentials, no GPU, no vendor
SDK.
