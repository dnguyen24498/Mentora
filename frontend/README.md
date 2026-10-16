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

Only `.pptx` (OOXML) is accepted; legacy `.ppt` is rejected by the backend with
`UNSUPPORTED_LEGACY_FORMAT`.
