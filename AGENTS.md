# AGENTS.md

## What this repo is

Design + early implementation repo for the **AI Teacher Platform** — a real-time AI teaching/classroom system. Target V1 shape is a **modular monolith** (`frontend/`, `backend/`, `workers/`, `infra/`); split into microservices only when scaling demands it.

## Authoritative source of truth

- `docs/ARC_OVERVIEW.md` — the single architecture document. Read it before making design claims; it defines service boundaries, data flow, deployment profiles, and tenant model.

## Stack

- Frontend (not yet implemented): React + TypeScript + Tailwind, WebRTC (media/audio) + WebSocket (control events) + HTTPS REST (APIs).
- Backend: Python, FastAPI, asyncio, Pydantic. Code lives under `backend/app/`, packaged as `ai-teacher-backend`.
- Storage: PostgreSQL (durable/authoritative records), Redis (realtime session state), vector search (RAG course knowledge), object storage (files/assets).

## Commands (backend)

- Install: `cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`
- Test: `cd backend && env -u PYTHONPATH .venv/bin/python -m pytest -q`

## Environment gotcha (important)

This shell has ROS 2 installed and `PYTHONPATH=/opt/ros/jazzy/lib/python3.12/site-packages` is set globally, which breaks the venv's `pytest` (it loads ROS plugins and fails on `ModuleNotFoundError: No module named 'yaml'`). **Always prefix Python/pytest commands with `env -u PYTHONPATH`** when running against `backend/.venv`.

## Core product-logic boundaries (non-obvious)

- The **Teacher Orchestrator** is the central/canonical product logic. LLM, TTS (OmniVoice), search, and media providers are explicitly treated as *replaceable infrastructure* behind interfaces.
- Deterministic data (attendance, grades, completion, slide numbers, permissions) must come from services/DB, **never from LLM memory**.
- Backend sends semantic presentation events (e.g. `goto_slide`, `highlight`), not raw LLM-generated HTML.
- Every installation is scoped by `institution_id`; all authorization checks must enforce that tenant boundary.

## Implemented backend modules

- `backend/app/llm/` — `LLMRouter` (routes by keyword/explicit `tier` to `fast`/`teaching`/`reasoning` providers) + `LLMProvider` interface + `FakeLLMProvider` stub.
- `backend/app/voice/` — `VoiceService` (voice cloning + text chunking + streaming synthesis + `speak_deck`) + `VoiceProvider` interface + `FakeVoiceProvider` stub. Audio streams directly to callers, never via a message bus. `OmniVoiceProvider` wraps the official OmniVoice library.
  - OmniVoice is a **Python library**, not a REST API: `pip install omnivoice` (pulls in torch), `OmniVoice.from_pretrained("k2-fsa/OmniVoice")`, `model.generate(text=..., ref_audio=..., ref_text=...)` / `model.create_voice_clone_prompt(...)`. Audio returns as 24 kHz `np.ndarray`. The `omnivoice-demo` Gradio UI runs on port 8001 but is only a frontend. `OmniVoiceProvider` lazy-imports the library so the rest of the app/tests run without torch/GPU; install with `pip install -e ".[voice]"`. Not installed in this environment yet.
- `backend/app/presentation/` — `PresentationService` builds semantic `PresentationEvent`s (`goto_slide`, `highlight`, etc.); `presentation/parser.py` reads a file into a `SlideDeck` (real `MarkdownPresentationParser`, PDF/PPTX stubs).
- `backend/app/upload.py` — `UploadService` routes course-material uploads: documents → RAG ingestion (`ingest_document`), presentation file → `SlideDeck` (`read_presentation`).
- `backend/app/knowledge/` — RAG ingestion (`IngestionPipeline`: parse → clean → chunk → embed → index) + retrieval (`search`). `DocumentParser`/`EmbeddingProvider`/`VectorIndex` are replaceable interfaces; `TextDocumentParser`/`MarkdownDocumentParser` are real, PDF/PPTX/DOCX parsers are stubs, and `FakeEmbeddingProvider` + `InMemoryVectorIndex` back local dev/tests.

## Gotchas to preserve

- Keep realtime audio off the general API/message-bus hot path.
- LLM Router should route simple state checks to small/deterministic paths, not the largest model.
- External providers (LLM, TTS, search) are stubbed as `Fake*` classes behind interfaces; do not add real API keys/network calls without wiring them through the existing `*Provider` ABCs.
