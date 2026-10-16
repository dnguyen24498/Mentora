# Frontend

Upload UI for course materials (`.pptx`). React + TypeScript + Tailwind, built
with Vite.

## Ports

| Service | Port |
| --- | --- |
| Frontend (Vite dev server) | **8000** |
| Backend API | **8001** |

Vite proxies `/courses`, `/artifacts`, and `/health` to the backend
(`MENTORA_BACKEND_ORIGIN`, default `http://127.0.0.1:8001`), so the browser only
ever talks to `:8000` — no CORS.

## Run (two terminals)

```bash
# terminal 1: backend API on :8001
cd backend && env -u PYTHONPATH .venv/bin/uvicorn app.api.app:create_app --factory --port 8001

# terminal 2: frontend on :8000 (hot reload)
cd frontend && npm install && npm run dev
```

Open <http://localhost:8000>.

### Accessing through a hostname / tunnel

Vite blocks unknown `Host` headers. If you reach the dev server via a domain
(e.g. `dev.nguynx.uk`), add it to `server.allowedHosts` in `vite.config.ts` — or
set the comma-separated `MENTORA_ALLOWED_HOSTS` env var:

```bash
MENTORA_ALLOWED_HOSTS=dev.nguynx.uk,other.example ./run.sh
```

The default allows `dev.nguynx.uk`. API proxying is unaffected (it happens
server-side), so the API still works from any allowed host.

## Production-style build (optional)

`npm run build` emits `frontend/dist/`. If you don't want a separate frontend
server, the backend serves that build at `/` when it exists, giving a single
origin (point the browser at the backend port, e.g. `:8001`).

## What it does

- Takes an **Institution ID** (sent as the `X-Institution-Id` tenant header,
  persisted in `localStorage`).
- Lists the tenant's courses (`GET /courses`) and can create one (`POST /courses`).
- Lists the selected course's already-uploaded presentations
  (`GET /courses/{id}/materials`) with size, version and job status, and lets you
  **select one** to inspect it.
- Uploads or drag-and-drops a `.pptx` (`POST /courses/{id}/materials`).
- Selecting a file (or finishing an upload) shows its stored artifact metadata and
  runs structural extraction (`POST /artifacts/{id}/extract`), rendering the full
  content in the IR viewer (`src/components/ContentIrView.tsx`): every object per
  slide, all paragraphs, tables as tables, images with their media reference,
  group nesting, and slide notes.
- **Preview slides** (V0-007 preview slice, `src/components/ReviewPreview.tsx`)
  shows the teacher review view of the built Content Package: the rendered fallback
  for each slide, the extracted text, the speaker notes, the fidelity/warnings
  (including missing fonts) and the fallback **lesson order** with its safe
  markers. It reads the package already built for the file
  (`GET /artifacts/{id}/review-package`, no re-render); the first preview of a file
  builds it (`POST` the same path) and later previews are instant.

  Notes:
  - The slide SVG is fetched by the client and displayed from an object URL,
    because `<img src>` cannot send the `X-Institution-Id` header.
  - The screen is **read-only**: approving/rejecting, script edits and the
    publication transition are V0-008, so there is no approve action — and a
    document that fails the fidelity gate answers with `PUBLICATION_BLOCKED`
    instead of a review.
  - The render is a **structural placeholder**, not a native PowerPoint render;
    the UI says so (`DEC-TECH-005` is still `OPEN`).

Only `.pptx` (OOXML) is accepted; legacy `.ppt` is rejected by the backend with
`UNSUPPORTED_LEGACY_FORMAT`.
