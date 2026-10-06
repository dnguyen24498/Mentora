# AGENTS.md

## What this repo is

Pre-implementation design repo for the **AI Teacher Platform** — a real-time AI teaching/classroom system. There is **no application code, no manifests, no tests, and no git history yet** (not currently a git repo). The only file is the architecture spec.

## Authoritative source of truth

- `docs/ARC_OVERVIEW.md` — the single architecture document. Read it before making design claims; it defines service boundaries, data flow, deployment profiles, and tenant model.

## Planned stack (from the spec, not yet implemented)

- Frontend: React + TypeScript + Tailwind, WebRTC (media/audio) + WebSocket (control events) + HTTPS REST (APIs).
- Backend: Python, FastAPI, asyncio, Pydantic.
- Storage: PostgreSQL (durable/authoritative records), Redis (realtime session state), vector search (RAG course knowledge), object storage (files/assets).
- Target V1 shape: a **modular monolith** (`frontend/`, `backend/`, `workers/`, `infra/`); split into microservices only when scaling demands it.

## Core product-logic boundaries (non-obvious)

- The **Teacher Orchestrator** is the central/canonical product logic. LLM, TTS (OmniVoice), search, and media providers are explicitly treated as *replaceable infrastructure* behind interfaces.
- Deterministic data (attendance, grades, completion, slide numbers, permissions) must come from services/DB, **never from LLM memory**.
- Backend sends semantic presentation events (e.g. `goto_slide`, `highlight`), not raw LLM-generated HTML.
- Every installation is scoped by `institution_id`; all authorization checks must enforce that tenant boundary.

## Gotchas to preserve when code exists

- Keep realtime audio off the general API/message-bus hot path.
- LLM Router should route simple state checks to small/deterministic paths, not the largest model.
