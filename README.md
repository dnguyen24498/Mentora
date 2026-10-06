# AI Teacher Platform

A real-time AI teaching/classroom system: an AI teacher that teaches from uploaded
course material, presents slides, answers student questions, and speaks with an
authorized per-teacher cloned voice.

> **Status:** early implementation (modular monolith). Architecture is specified in
> [`docs/ARC_OVERVIEW.md`](docs/ARC_OVERVIEW.md) — read it for service boundaries,
> data flow, and the tenant model.

## Repository layout

```
frontend/   React + TypeScript classroom (not implemented yet)
backend/    Python + FastAPI service (packaged as `ai-teacher-backend`)
workers/    background workers (not implemented yet)
infra/      docker / k8s / terraform (not implemented yet)
docs/       architecture spec
```

## Prerequisites

- Python 3.11+
- (optional, for real TTS) a CUDA GPU + torch — see [Voice / OmniVoice](#voice--omnivoice)

## Install

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

> **Note (ROS environments):** if `PYTHONPATH` points at ROS site-packages, prefix
> every Python/pytest command with `env -u PYTHONPATH`:
> ```bash
> env -u PYTHONPATH .venv/bin/pip install -e ".[dev]"
> ```

## Run tests

```bash
cd backend
env -u PYTHONPATH .venv/bin/python -m pytest -q
```

## Voice / OmniVoice

Real text-to-speech uses the official [OmniVoice](https://github.com/k2-fsa/OmniVoice)
library (`pip install omnivoice`, pulls in torch; GPU recommended). Install the
optional extra, then create a teacher voice and synthesize speech:

```bash
cd backend
.venv/bin/pip install -e ".[voice]"
```

```python
import asyncio
from app.voice import OmniVoiceProvider, VoiceCloneRequest, SynthesisRequest, VoiceService

async def main():
    provider = OmniVoiceProvider(device_map="cuda:0")  # or "cpu" without a GPU
    service = VoiceService(provider)

    # 1. clone a teacher's voice (3-10s reference audio)
    voice_id = await service.create_teacher_voice(
        VoiceCloneRequest(name="teacher_a", ref_audio=open("ref.wav", "rb").read(), ref_text="hello")
    )

    # 2. synthesize speech from text
    async for chunk in service.synthesize(SynthesisRequest(text="Welcome to class.", voice_profile_id=voice_id)):
        open("out.pcm", "wb").write(chunk.data)

asyncio.run(main())
```

Without the `[voice]` extra (no torch/GPU), the `FakeVoiceProvider` is used in tests
so everything else still runs.

## What's implemented vs. stubbed

| Module | Status |
|--------|--------|
| LLM router (`fast`/`teaching`/`reasoning`) | real routing logic; `FakeLLMProvider` |
| RAG ingestion (parse → clean → chunk → embed → index → search) | real for text/markdown; PDF/PPTX/DOCX parsers are stubs |
| Presentation events / slide deck | real markdown parser; PDF/PPTX stubs |
| Upload service (document → RAG, presentation → slides) | real |
| Voice service (clone + stream + speak deck) | real logic; real TTS needs `omnivoice` |
