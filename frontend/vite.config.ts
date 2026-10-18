import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Frontend dev server runs on :8000. API calls are proxied to the backend,
// which runs on :8001 (override with MENTORA_BACKEND_ORIGIN).
const BACKEND = process.env.MENTORA_BACKEND_ORIGIN ?? 'http://127.0.0.1:8001'

// Hostnames allowed to reach the dev server (comma-separated via
// MENTORA_ALLOWED_HOSTS). Needed when the dev server is exposed through a
// tunnel or reverse proxy (e.g. dev.nguynx.uk -> localhost:8000).
const ALLOWED_HOSTS = (process.env.MENTORA_ALLOWED_HOSTS ?? 'dev.nguynx.uk')
  .split(',')
  .map((host) => host.trim())
  .filter(Boolean)

interface ProxyResponse {
  headersSent?: boolean
  writeHead(status: number, headers: Record<string, string>): void
  end(body: string): void
}

interface ProxyServer {
  on(event: 'error', handler: (error: unknown, request: unknown, response: unknown) => void): void
}

/**
 * Proxy rule that turns "backend is not running" into a readable API error.
 *
 * Without this, http-proxy answers a refused connection with a bare
 * `500 Internal Server Error` and no body, which the UI can only show as
 * `500: Internal Server Error` — indistinguishable from a real server bug.
 */
function backendProxy() {
  return {
    target: BACKEND,
    configure(proxy: ProxyServer) {
      proxy.on('error', (_error, _request, response) => {
        const res = response as ProxyResponse | undefined
        if (!res || typeof res.writeHead !== 'function' || res.headersSent) return
        res.writeHead(503, { 'Content-Type': 'application/json' })
        res.end(
          JSON.stringify({
            error: {
              code: 'BACKEND_UNAVAILABLE',
              message:
                `Cannot reach the Mentora API at ${BACKEND}. ` +
                'The backend is not running — start the stack with ./run.sh',
            },
          }),
        )
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    port: 8000,
    strictPort: true,
    allowedHosts: ALLOWED_HOSTS,
    proxy: {
      '/courses': backendProxy(),
      '/artifacts': backendProxy(),
      // Classroom runtime (V0-009/V0-011): the Classroom page reads the
      // authoritative session snapshot from `/classes/{id}/snapshot`.
      '/classes': backendProxy(),
      '/health': backendProxy(),
      // Renderer capability/health (V0-005) and the API docs. Without these the
      // dev server answers with the SPA fallback (index.html), so the browser
      // would silently get HTML instead of the backend response.
      '/renderer': backendProxy(),
      '/docs': backendProxy(),
      '/openapi.json': backendProxy(),
    },
  },
})
