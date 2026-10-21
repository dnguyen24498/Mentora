"""A minimal local HTTP sidecar around an installed OmniVoice (prototype).

OmniVoice (https://github.com/k2-fsa/OmniVoice) is a PyTorch library: one
``model.generate(text=...)`` returns a whole 24 kHz waveform. It ships no HTTP
API, so this file is the smallest server that lets the Mentora backend reach it
without importing PyTorch into the backend:

* the model is loaded **once** (``mps`` on Apple Silicon, ``cuda`` or ``cpu``);
* ``POST /synthesize`` takes ``{"text": ..., "language": ...}`` and streams raw
  16-bit little-endian mono PCM back (``audio/L16; rate=24000``);
* ``GET /health`` reports the model, device, sample rate and voice mode.

Streaming to the classroom comes from Mentora's own chunking: the backend splits
each slide's script into sentence-sized chunks and calls this endpoint once per
chunk, so the first sentence plays while the next is generated.

**The voice is fixed for the whole server**, because OmniVoice's *auto voice*
picks a different random speaker on every call and a slide would change voice
mid-sentence. Choose one (environment variables):

* ``OMNIVOICE_PROMPT=/path/my_voice.pt`` — a saved ``VoiceClonePrompt``;
* ``OMNIVOICE_REF_AUDIO=/path/ref.wav`` (+ optional ``OMNIVOICE_REF_TEXT``) —
  clone from a 3–10 s clip (only use a voice you are authorized to clone);
* ``OMNIVOICE_INSTRUCT="female, american accent"`` — voice design (default).

Generation knobs: ``OMNIVOICE_NUM_STEP`` (default 16 — faster on an M1; the
upstream default is 32), ``OMNIVOICE_SPEED`` (default 1.0),
``OMNIVOICE_MODEL`` (default ``k2-fsa/OmniVoice``), ``OMNIVOICE_DEVICE``.

Run (inside the environment where ``pip install omnivoice`` worked)::

    python tools/omnivoice_server/server.py --host 127.0.0.1 --port 8765

This is a development prototype: ``DEC-TECH-007`` (TTS/OmniVoice) is ``OPEN``.
It has no authentication, so keep it bound to localhost.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SAMPLE_RATE = 24_000
MAX_TEXT_CHARACTERS = 2_000


def _pick_device(torch) -> str:
    requested = os.environ.get("OMNIVOICE_DEVICE", "").strip()
    if requested:
        return requested
    if torch.cuda.is_available():
        return "cuda:0"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class Engine:
    """The loaded model plus the one fixed voice; one generation at a time."""

    def __init__(self) -> None:
        import numpy as np
        import torch
        from omnivoice import OmniVoice

        self._np = np
        self.device = _pick_device(torch)
        # float16 is fastest on CUDA; MPS/CPU are more reliable in float32.
        dtype = torch.float16 if self.device.startswith("cuda") else torch.float32
        self.model_name = os.environ.get("OMNIVOICE_MODEL", "k2-fsa/OmniVoice")
        started = time.monotonic()
        self.model = OmniVoice.from_pretrained(
            self.model_name, device_map=self.device, dtype=dtype
        )
        self.load_seconds = round(time.monotonic() - started, 2)
        self.num_step = int(os.environ.get("OMNIVOICE_NUM_STEP", "16"))
        self.speed = float(os.environ.get("OMNIVOICE_SPEED", "1.0"))
        self.voice_kwargs, self.voice_mode = self._voice()
        self._lock = threading.Lock()

    def _voice(self) -> tuple[dict, str]:
        prompt_path = os.environ.get("OMNIVOICE_PROMPT", "").strip()
        if prompt_path:
            from omnivoice import VoiceClonePrompt

            return {"voice_clone_prompt": VoiceClonePrompt.load(prompt_path)}, "clone-prompt"
        ref_audio = os.environ.get("OMNIVOICE_REF_AUDIO", "").strip()
        if ref_audio:
            # Encode once so every chunk reuses the same voice cheaply.
            prompt = self.model.create_voice_clone_prompt(
                ref_audio=ref_audio,
                ref_text=os.environ.get("OMNIVOICE_REF_TEXT") or None,
            )
            return {"voice_clone_prompt": prompt}, "clone-reference"
        instruct = os.environ.get("OMNIVOICE_INSTRUCT", "female, american accent").strip()
        return {"instruct": instruct}, f"design:{instruct}"

    def synthesize(self, text: str) -> bytes:
        with self._lock:  # one GPU/MPS generation at a time
            audio = self.model.generate(
                text=text,
                num_step=self.num_step,
                speed=self.speed,
                **self.voice_kwargs,
            )
        wave = self._np.asarray(audio[0], dtype=self._np.float32).reshape(-1)
        wave = self._np.clip(wave, -1.0, 1.0)
        return (wave * 32767.0).astype("<i2").tobytes()

    def health(self) -> dict:
        return {
            "status": "ok",
            "model": self.model_name,
            "device": self.device,
            "sample_rate": SAMPLE_RATE,
            "bytes_per_sample": 2,
            "channels": 1,
            "voice": self.voice_mode,
            "num_step": self.num_step,
            "load_seconds": self.load_seconds,
        }


def build_handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # one line, never the text itself
            sys.stderr.write("[omnivoice] %s\n" % (fmt % args))

        def _json(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path.rstrip("/") == "/health":
                self._json(200, engine.health())
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path.rstrip("/") != "/synthesize":
                self._json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length) or b"{}")
                text = str(payload.get("text", "")).strip()
            except (ValueError, TypeError):
                self._json(400, {"error": "invalid JSON body"})
                return
            if not text or len(text) > MAX_TEXT_CHARACTERS:
                self._json(400, {"error": f"text must be 1..{MAX_TEXT_CHARACTERS} characters"})
                return
            started = time.monotonic()
            try:
                pcm = engine.synthesize(text)
            except Exception as exc:  # report, never crash the server
                self._json(500, {"error": f"generation failed: {exc}"})
                return
            elapsed = time.monotonic() - started
            audio_seconds = len(pcm) / 2 / SAMPLE_RATE
            self.send_response(200)
            self.send_header("Content-Type", f"audio/L16; rate={SAMPLE_RATE}; channels=1")
            self.send_header("Content-Length", str(len(pcm)))
            self.send_header("X-Sample-Rate", str(SAMPLE_RATE))
            self.send_header("X-Generation-Seconds", f"{elapsed:.3f}")
            self.send_header("X-RTF", f"{elapsed / audio_seconds:.3f}" if audio_seconds else "0")
            self.end_headers()
            # Write in ~100 ms frames so the client can start reading early.
            frame = SAMPLE_RATE // 10 * 2
            for start in range(0, len(pcm), frame):
                self.wfile.write(pcm[start:start + frame])

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Local OmniVoice HTTP sidecar for Mentora")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--warmup", default="Hello. The voice is ready.",
                        help="text generated once at start-up (empty to skip)")
    args = parser.parse_args()

    print("[omnivoice] loading model …", file=sys.stderr)
    engine = Engine()
    print(f"[omnivoice] ready on {engine.device} in {engine.load_seconds}s, voice={engine.voice_mode}",
          file=sys.stderr)
    if args.warmup:
        started = time.monotonic()
        engine.synthesize(args.warmup)
        print(f"[omnivoice] warm-up took {time.monotonic() - started:.2f}s", file=sys.stderr)
    server = ThreadingHTTPServer((args.host, args.port), build_handler(engine))
    print(f"[omnivoice] listening on http://{args.host}:{args.port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
