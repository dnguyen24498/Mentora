# OmniVoice sidecar (local prototype)

Mentora can narrate slides with a locally installed
[OmniVoice](https://github.com/k2-fsa/OmniVoice). OmniVoice is a PyTorch library
with no HTTP API, so `server.py` is a tiny HTTP server that runs **in your
OmniVoice Python environment**. The Mentora backend calls it over HTTP using only
the standard library; PyTorch never enters the backend's environment.

> `DEC-TECH-007` (TTS/OmniVoice) is **OPEN**. This is an opt-in prototype
> (`omnivoice@0.1.0-prototype`), not the decided provider. The default is still the
> deterministic mock.

## How streaming works

```
slide script (pinned package)
  → split into sentence-sized chunks (≤160 chars, word-safe)       backend
  → one POST /synthesize per chunk  ──HTTP──▶  OmniVoice.generate() sidecar (mps)
  ◀── raw PCM 16-bit mono 24 kHz, read in ~100 ms frames
  → one WAV per chunk, streamed as NDJSON to the teacher's tab      backend
  → played in order; chunk 2 is being generated while chunk 1 plays browser
```

OmniVoice produces a whole waveform for each call, so the time to first audio
is the time to generate the **first sentence**, not the whole slide.

## 1. Run the sidecar on the Mac (M1)

```bash
# In the environment where `pip install omnivoice` worked (with Apple-Silicon PyTorch)
cd /path/to/mentora
python tools/omnivoice_server/server.py --host 127.0.0.1 --port 8765
```

The first run downloads `k2-fsa/OmniVoice` from Hugging Face. If that host is
slow to reach, set `HF_ENDPOINT=https://hf-mirror.com`. The server prints the
device (`mps`), the voice, and how long the warm-up took. Check it:

```bash
curl -s http://127.0.0.1:8765/health
curl -s -X POST http://127.0.0.1:8765/synthesize \
  -H 'Content-Type: application/json' -d '{"text":"Hello class."}' -o /tmp/t.pcm -D -
```

Do **not** use port 8001 (OmniVoice's own `omnivoice-demo` default): the Mentora
backend uses it.

### Choose one fixed voice

OmniVoice's *auto voice* picks a random speaker on every call, which would change
voice between sentences, so the sidecar always uses one voice:

| Variable | Effect |
| --- | --- |
| `OMNIVOICE_INSTRUCT="female, american accent"` | voice design (default) |
| `OMNIVOICE_REF_AUDIO=ref.wav` (+ `OMNIVOICE_REF_TEXT`) | clone a 3–10 s clip, encoded once (only a voice you are authorized to use) |
| `OMNIVOICE_PROMPT=my_voice.pt` | a saved `VoiceClonePrompt` |
| `OMNIVOICE_NUM_STEP=16` | diffusion steps (default 16 for speed on M1; upstream default 32 = higher quality) |
| `OMNIVOICE_SPEED=1.0` | speaking rate |
| `OMNIVOICE_DEVICE=mps` | override the device (auto: cuda → mps → cpu) |

## 2. Point the backend at it

```bash
export MENTORA_TTS_PROVIDER=omnivoice
export MENTORA_OMNIVOICE_URL=http://127.0.0.1:8765      # default
export MENTORA_OMNIVOICE_DEADLINE_SECONDS=60             # per sentence chunk
./run.sh
```

If the backend runs on a different machine from the sidecar, bind the sidecar to
the LAN (`--host 0.0.0.0`) and set `MENTORA_OMNIVOICE_URL=http://<mac-ip>:8765`.
The sidecar has no authentication, so only do this on a trusted network.

## 3. Use it

Start a class from **Classroom**; it opens with auto-play. The stage shows
`Voice: speaking · OmniVoice local prototype`, and each slide advances when its
narration ends. If the sidecar is down or too slow, that slide falls back to its
text and is paced by reading time, so the lesson never stalls.

## Limits

- One generation at a time (GPU lock); one teacher tab is the intended load.
- Only the teacher's tab plays audio; shared audio for remote students is V1-005 (SFU).
- Audio is base64 WAV inside the NDJSON stream, which is fine for one tab.
